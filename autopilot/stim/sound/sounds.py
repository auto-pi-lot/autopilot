"""This module defines classes to generate different sounds.

These classes are currently implemented:
* Tone : a sinuosoidal pure tone
* Noise : a burst of white noise
* File : read from a file
* Speech
* Gap

The behavior of this module depends on `prefs.get('AUDIOSERVER')`.
* If this is 'jack', or True:
    Then import jack, define Jack_Sound, and all sounds inherit from that.
* If this is 'pyo':
    Then import pyo, define PyoSound, and all sounds inherit from that.
* If this is 'docs':
    Then import both jack and pyo, define both Jack_Sound and PyoSound,
    and all sounds inherit from `object`.
* Otherwise:
    Then do not import jack or pyo, or define either Jack_Sound or PyoSound,
    and all sounds inherit from `object`.

TODO:
    Implement sound level and filter calibration
"""

# Re: The organization of this module
# We balance a few things:
# 1) using two sound servers with very different approaches to
# delivering sounds, and
# 2) having a similar API so other modules can query sound properties
# while still being agnostic to the sound server.
# 3) not have our classes split into a ton of Pyo_Tone, Jack_Tone
# copies so they have their parameters and behavior drift apart
#
# So, We have base classes, but they can't encapsulate all the
# behavior for making sounds, so use an init_audio() method that
# creates sound conditional on the type of audio server.


import os
import sys
from time import sleep
from scipy.io import wavfile
from scipy.signal import resample
import numpy as np
import threading
from itertools import cycle
from queue import Empty, Full

from autopilot import prefs
from autopilot.core.loggers import init_logger
from autopilot.stim import Stim


## First, switch the behavior based on the pref AUDIOSERVER
# Get the pref
server_type = prefs.get('AUDIOSERVER')

# True is a synonym for 'jack', the default server
if server_type == True:
    server_type = 'jack'

# Force lower-case if string
try:
    server_type = server_type.lower()
except AttributeError:
    pass

# From now on, server_type should be 'jack', 'pyo', 'docs', or None
if server_type not in ['jack', 'pyo', 'docs']:
    server_type = None

# if we're testing, set server_type to jack
if 'pytest' in sys.modules:
    server_type = 'jack'


## Import the required modules
if server_type in ['jack', 'docs']:
    # This will warn if the jack library is not found
    from autopilot.stim.sound import jackclient

elif server_type in ['pyo', 'docs']:
    # Using these import guards for compatibility, but I think we should
    # actually error here
    try:
        import pyo
    except ImportError:
        pass


## Define Pyo_Sound if needed
if server_type in ("pyo", "docs"):
    class Pyo_Sound(object):
        """
        Metaclass for pyo sound objects.

        Note:
            Use of pyo is generally discouraged due to dropout issues and
            the general opacity of the module. As such this object is
            intentionally left undocumented.

        """
        def __init__(self):
            self.PARAMS = None  # list of strings of parameters to be defined
            self.type = None  # string human readable name of sound
            self.duration = None  # duration in ms
            self.amplitude = None
            self.table = None
            self.trigger = None
            self.server_type = 'pyo'

        def play(self):
            self.table.out()

        def table_wrap(self, audio, duration=None):
            """Records a PyoAudio generator into a sound table, returns a
            tableread object which can play the audio with .out()

            Args:
                audio:
                duration:
            """

            if not duration:
                duration = self.duration

            # Duration is in ms, so divide by 1000
            # See https://groups.google.com/forum/#!topic/pyo-discuss/N-pan7wPF-o
            # TODO: Get chnls to be responsive to NCHANNELS in prefs. hardcoded for now
            tab = pyo.NewTable(length=(float(duration) / 1000),
                               chnls=prefs.get('NCHANNELS'))  # Prefs should always be declared in the global namespace
            tabrec = pyo.TableRec(audio, table=tab, fadetime=0.005).play()
            sleep((float(duration) / 1000))
            self.table = pyo.TableRead(tab, freq=tab.getRate(), loop=0)

        def set_trigger(self, trig_fn):
            """
            Args:
                trig_fn:
            """
            # Using table triggers, call trig_fn when table finishes playing
            self.trigger = pyo.TrigFunc(self.table['trig'], trig_fn)


## Define Jack_Sound if needed
if server_type in ("jack", "docs"):
    class Jack_Sound(object):
        """
        Base class for sounds that use the :class:`~.jackclient.JackClient` audio
        server.

        Attributes:
            PARAMS (list): List of strings of parameters that need to be defined for this sound
            type (str): Human readable name of sound type
            duration (float): Duration of sound in ms
            amplitude (float): Amplitude of sound as proportion of 1 (eg 0.5 is half amplitude)
            table (:class:`numpy.ndarray`): A Numpy array of samples
            chunks (list): :attr:`~.Jack_Sound.table` split up into chunks of :data:`~.jackclient.BLOCKSIZE`
            trigger (callable): A function that is called when the sound completes
            nsamples (int): Number of samples in the sound
            padded (bool): Whether the sound had to be padded with zeros when split into chunks (ie. sound duration was not a multiple of BLOCKSIZE).
            fs (int): sampling rate of client from :data:`.jackclient.FS`
            blocksize (int): blocksize of client from :data:`.jackclient.BLOCKSIZE`
            server (:class:`~.jackclient.Jack_Client`): Current Jack Client
            q (:class:`multiprocessing.Queue`): Audio Buffer queue from :data:`.jackclient.QUEUE`
            q_lock (:class:`multiprocessing.Lock`): Audio Buffer lock from :data:`.jackclient.Q_LOCK`
            play_evt (:class:`multiprocessing.Event`): play event from :data:`.jackclient.PLAY`
            stop_evt (:class:`multiprocessing.Event`): stop event from :data:`.jackclient.STOP`
            buffered (bool): has this sound been dumped into the :attr:`~.Jack_Sound.q` ?
            buffered_continuous (bool): Has the sound been dumped into the :attr:`~.Jack_Sound.continuous_q`?

        """

        PARAMS = []
        """
        list:  list of strings of parameters to be defined
        """

        type = None
        """
        str: string human readable name of sound
        """

        server_type = 'jack'
        """
        str: type of server, always 'jack' for `Jack_Sound` s.
        """

        def __init__(self):
            """Initialize a new Jack_Sound
            
            This sets sound-specific parameters to None, set jack-specific
            parameters to their equivalents in jackclient, initializes
            some other flags and a logger.
            """
            # These sound-specific parameters will be set by the derived
            # objects.
            self.duration = None  # duration in ms
            self.amplitude = None
            self.table = None  # numpy array of samples
            self.chunks = None  # table split into a list of chunks
            self.trigger = None
            self.nsamples = None
            self.padded = False # whether or not the sound was padded with zeros when chunked
            self.continuous = False

            # These jack-specific parameters are copied from jackclient
            self.fs = jackclient.FS
            self.blocksize = jackclient.BLOCKSIZE
            self.server = jackclient.SERVER
            self.q = jackclient.QUEUE
            self.q_lock = jackclient.Q_LOCK
            self.play_evt = jackclient.PLAY
            self.stop_evt = jackclient.STOP
            self.continuous_flag = jackclient.CONTINUOUS
            self.continuous_q = jackclient.CONTINUOUS_QUEUE
            self.continuous_loop = jackclient.CONTINUOUS_LOOP

            # Initalize these flags
            self.initialized = False
            self.buffered = False
            self.buffered_continuous = False

            # Initialize a logger
            self.logger = init_logger(self)

        def chunk(self, pad=True):
            """
            Split our `table` up into a list of :attr:`.Jack_Sound.blocksize` chunks.

            Args:
                pad (bool): If the sound is not evenly divisible into chunks, 
                pad with zeros (True, default), otherwise jackclient will pad 
                with its continuous sound
            """
            # Convert the table to float32 (if it isn't already)
            sound = self.table.astype(np.float32)

            # Determine how much longer it would have to be, if it were
            # padded to a length that is a multiple of self.blocksize
            oldlen = len(sound)
            newlen = int(
                np.ceil(float(oldlen) / self.blocksize) * self.blocksize)

            
            ## Only pad if necessary AND requested
            if pad and newlen > oldlen:
                # Pad differently depending on mono or stereo
                if sound.ndim == 1:
                    # Pad with 1d array of zeros
                    to_concat = np.zeros((newlen - oldlen,), np.float32)

                    # Pad
                    sound = np.concatenate([sound, to_concat])

                elif sound.ndim == 2:
                    # Each column is a channel
                    n_channels = sound.shape[1]
                    
                    # Raise error if more than two-channel sound
                    # This would actually be fine for this function, but this 
                    # almost surely indicates somebody has transposed something
                    if n_channels > 2:
                        raise ValueError("only 1- or 2-channel sound supported")
                    
                    # Pad with 2d array of zeros
                    to_concat = np.zeros(
                        (newlen - oldlen, sound.shape[1]), np.float32)

                    # Pad
                    sound = np.concatenate([sound, to_concat])
                
                else:
                    raise ValueError("sound must be 1d or 2d")
                
                # Flag as padded
                self.padded = True
            
            else:
                # Flag as not padded
                self.padded = False
            
            
            ## Reshape into chunks, each of length `self.blocksize`
            if sound.ndim == 1:
                self.chunks = list(
                    sound.reshape(-1, self.blocksize))
            
            elif sound.ndim == 2:
                self.chunks = list(
                    sound.reshape(-1, self.blocksize, sound.shape[1]))

        def set_trigger(self, trig_fn):
            """
            Set a trigger function to be called when the :attr:`~.Jack_Sound.stop_evt` is set.

            Args:
                trig_fn (callable): Some callable
            """
            if callable(trig_fn):
                self.trigger = trig_fn
            else:
                Exception('trigger must be callable')

        def wait_trigger(self):
            """
            Wait for the stop_evt trigger to be set for at least a second after
            the sound should have ended.

            Call the trigger when the event is set.
            """
            # wait for our duration plus a second at most.
            self.stop_evt.wait((self.duration+1000)/1000.)
            # if the sound actually stopped...
            if self.stop_evt.is_set():
                self.trigger()

        def get_nsamples(self):
            """
            given our fs and duration, how many samples do we need?

            literally::

                np.ceil((self.duration/1000.)*self.fs).astype(np.int)

            """
            self.nsamples = np.ceil((self.duration/1000.)*self.fs).astype(np.int)

        def quantize_duration(self, ceiling=True):
            """
            Extend or shorten a sound so that it is a multiple of :data:`.jackclient.BLOCKSIZE`

            Args:
                ceiling (bool): If true, extend duration, otherwise decrease duration.
            """

            # get remainder of samples
            self.get_nsamples()
            remainder = self.nsamples % self.blocksize

            if remainder == 0:
                return

            # get target number of samples
            # get target n blocks and multiply by blocksize
            if ceiling:
                target_samples = np.ceil(float(self.nsamples)/self.blocksize)*self.blocksize
            else:
                target_samples = np.floor(float(self.nsamples)/self.blocksize)*self.blocksize

            # get new duration
            self.duration = (target_samples/self.fs)*1000.

            # refresh nsamples
            self.get_nsamples()

        def buffer(self):
            """
            Dump chunks into the sound queue.
            
            After the last chunk, a `None` is put into the queue. This
            tells the jack server that the sound is over and that it should
            clear the play flag.
            """

            if hasattr(self, 'path'):
                self.logger.debug('BUFFERING SOUND {}'.format(self.path))

            if not self.initialized and not self.table:
                try:
                    self.init_sound()
                    self.initialized = True
                except:
                    pass
                    #TODO: Log this, better error handling here

            if not self.chunks:
                self.chunk()

            with self.q_lock:
                # empty queue
                # FIXME: Testing whether this is where we get held up on the 'fail after sound play' bug
                # n_gets = 0
                while not self.q.empty():
                    try:
                        _ = self.q.get_nowait()
                    except Empty:
                        # normal, get until it's empty
                        break
                    # n_gets += 1
                    # if n_gets > 100000:
                    #     break
                for frame in self.chunks:
                    self.q.put_nowait(frame)
                # The jack server looks for a None object to clear the play flag
                self.q.put_nowait(None)
                self.buffered = True

        def buffer_continuous(self):
            """
            Dump chunks into the continuous sound queue for looping.

            Continuous shoulds should always have full frames -
            ie. the number of samples in a sound should be a multiple of :data:`.jackclient.BLOCKSIZE`.

            This method will call :meth:`.quantize_duration` to force duration such that the sound has full frames.

            An exception will be raised if the sound has been padded.
            """

            # FIXME: Initialized should be more flexible,
            # for now just deleting whatever init happened because
            # continuous sounds are in development
            self.table = None
            self.initialized = False

            if not self.initialized and not self.table:
                self.quantize_duration()
                self.init_sound()
                self.initialized = True

            if not self.chunks:
                self.chunk()

            # continous sounds should not have any padding - see docstring
            if self.padded:
                raise Exception("Continuous sounds cannot have padded chunks - sounds need to have n_samples % blocksize == 0")

            # empty queue
            while not self.continuous_q.empty():
                try:
                    _ = self.continuous_q.get_nowait()
                except Empty:
                    # normal, get until it's empty
                    break

            # put all the chunks into the queue, rather than one at a time
            # to avoid partial receipt
            self.continuous_q.put(self.chunks.copy())

            self.buffered_continuous = True

        def play(self):
            """
            Play ourselves.

            If we're not buffered, be buffered.

            Otherwise, set the play event and clear the stop event.

            If we have a trigger, set a Thread to wait on it.
            """
            if not self.buffered:
                self.buffer()

            if hasattr(self, 'path'):
                self.logger.debug('PLAYING SOUND {}'.format(self.path))

            self.play_evt.set()
            self.stop_evt.clear()
            self.buffered = False

            if callable(self.trigger):
                threading.Thread(target=self.wait_trigger).start()

        def play_continuous(self, loop=True):
            """
            Play the sound continuously.

            Sound will be paused if another sound has its 'play' method called.

            Currently - only looping is implemented: the full sound is loaded by the jack client and repeated indefinitely.

            In the future, sound generation methods will be refactored as python generators so sounds can be continuously generated and played.

            Args:
                loop (bool): whether the sound will be stored by the jack client and looped (True), or whether the sound will be continuously streamed (False, not implemented)

            Returns:

            todo::

                merge into single play method that changes behavior if continuous or not

            """

            if not loop:
                raise NotImplementedError('Continuous, unlooped streaming has not been implemented yet!')

            if not self.buffered_continuous:
                self.buffer_continuous()

            if loop:
                self.continuous_loop.set()
            else:
                self.continuous_loop.clear()

            # tell the sound server that it has a continuous sound now
            self.continuous_flag.set()
            self.continuous = True

            # after the sound server start playing, it will clear the queue, unbuffering us
            self.buffered_continuous = False

        def stop_continuous(self):
            """
            Stop playing a continuous sound

            Should be merged into a general stop method
            """
            if not self.continuous:
                self.logger.warning("stop_continuous called but not a continuous sound!")
                return

            self.continuous_flag.clear()
            self.continuous_loop.clear()

        def end(self):
            """
            Release any resources held by this sound

            """

            if self.play_evt.is_set():
                self.play_evt.clear()

            if not self.stop_evt.is_set():
                self.stop_evt.set()

            if self.continuous:
                while not self.continuous_q.empty():
                    try:
                        _ = self.continuous_q.get_nowait()
                    except Empty:
                        # normal, get until it's empty
                        break
                self.buffered_continuous = False
                self.continuous_flag.clear()

            self.table = None
            self.initialized = False

        def __del__(self):
            self.end()


## Now define BASE_CLASS to be Pyo_Sound, Jack_Sound, or object
if server_type == "pyo":
    BASE_CLASS = Pyo_Sound
elif server_type == "jack":
    BASE_CLASS = Jack_Sound
else:
    # just importing to query parameters, not play sounds.
    BASE_CLASS = Stim


## The rest of the module defines actual sounds, which inherit from BASE_CLASS
class Tone(BASE_CLASS):
    """The Humble Sine Wave"""

    PARAMS = ['frequency','duration','amplitude']
    type = 'Tone'

    def __init__(self, frequency, duration, amplitude=0.01, **kwargs):
        """
        Args:
            frequency (float): frequency of sin in Hz
            duration (float): duration of the sin in ms
            amplitude (float): amplitude of the sound as a proportion of 1.
            **kwargs: extraneous parameters that might come along with instantiating us
        """
        super(Tone, self).__init__()

        self.frequency = float(frequency)
        self.duration = float(duration)
        self.amplitude = float(amplitude)

        self.init_sound()

    def init_sound(self):
        """
        Create a sine wave table using pyo or numpy, depending on the server type.
        """

        if self.server_type == 'pyo':
            sin = pyo.Sine(self.frequency, mul=self.amplitude)
            self.table = self.table_wrap(sin)
        elif self.server_type == 'jack':
            self.get_nsamples()
            t = np.arange(self.nsamples)
            self.table = (self.amplitude*np.sin(2*np.pi*self.frequency*t/self.fs)).astype(np.float32)
            #self.table = np.column_stack((self.table, self.table))
            self.chunk()

        self.initialized = True

class Noise(BASE_CLASS):
    """Generates a white noise burst with specified parameters
    
    The `type` attribute is always "Noise".
    """
    # These are the parameters of the sound, I think this is used to generate
    # sounds automatically for a protocol
    PARAMS = ['duration','amplitude', 'channel']
    
    # The type of the sound
    type='Noise'
    
    def __init__(self, duration, amplitude=0.01, channel=None, **kwargs):
        """Initialize a new white noise burst with specified parameters.
        
        The sound itself is stored as the attribute `self.table`. This can
        be 1-dimensional or 2-dimensional, depending on `channel`. If it is
        2-dimensional, then each channel is a column.
        
        Args:
            duration (float): duration of the noise
            amplitude (float): amplitude of the sound as a proportion of 1.
            channel (int or None): which channel should be used
                If 0, play noise from the first channel
                If 1, play noise from the second channel
                If None, send the same information to all channels ("mono")
            **kwargs: extraneous parameters that might come along with instantiating us
        """
        # This calls the base class, which sets server-specific parameters
        # like samplign rate
        super(Noise, self).__init__()
        
        # Set the parameters specific to Noise
        self.duration = float(duration)
        self.amplitude = float(amplitude)
        try:
            self.channel = int(channel)
        except TypeError:
            self.channel = channel
        
        # Currently only mono or stereo sound is supported
        if self.channel not in [None, 0, 1]:
            raise ValueError(
                "audio channel must be 0, 1, or None, not {}".format(
                self.channel))

        # Initialize the sound itself
        self.init_sound()

    def init_sound(self):
        """Defines `self.table`, the waveform that is played. 
        
        The way this is generated depends on `self.server_type`, because
        parameters like the sampling rate cannot be known otherwise.
        
        The sound is generated and then it is "chunked" (zero-padded and
        divided into chunks). Finally `self.initialized` is set True.
        """
        # Depends on the server_type
        if server_type == 'pyo':
            noiser = pyo.Noise(mul=self.amplitude)
            self.table = self.table_wrap(noiser)
        
        elif server_type == 'jack':
            # This calculates the number of samples, using the specified 
            # duration and the sampling rate from the server, and stores it
            # as `self.nsamples`.
            self.get_nsamples()
            
            # Generate the table by sampling from a uniform distribution
            # The shape of the table depends on `self.channel`
            if self.channel is None:
                # The table will be 1-dimensional for mono sound
                self.table = np.random.uniform(-1, 1, self.nsamples)
            else:
                # The table will be 2-dimensional for stereo sound
                # Each channel is a column
                # Only the specified channel contains data and the other is zero
                data = np.random.uniform(-1, 1, self.nsamples)
                self.table = np.zeros((self.nsamples, 2))
                assert self.channel in [0, 1]
                self.table[:, self.channel] = data
            
            # Scale by the amplitude
            self.table = self.table * self.amplitude
            
            # Convert to float32
            self.table = self.table.astype(np.float32)
            
            # Chunk the sound 
            self.chunk()

        # Flag as initialized
        self.initialized = True

class File(BASE_CLASS):
    """
    A .wav file.

    TODO:
        Generalize this to other audio types if needed.
    """

    PARAMS = ['path', 'amplitude']
    type='File'

    def __init__(self, path, amplitude=0.01, **kwargs):
        """
        Args:
            path (str): Path to a .wav file relative to the `prefs.get('SOUNDDIR')`
            amplitude (float): amplitude of the sound as a proportion of 1.
            **kwargs: extraneous parameters that might come along with instantiating us
        """
        super(File, self).__init__()

        if os.path.exists(path):
            self.path = path
        elif os.path.exists(os.path.join(prefs.get('SOUNDDIR'), path)):
            self.path = os.path.join(prefs.get('SOUNDDIR'), path)
        else:
            Exception('Could not find {} in current directory or sound directory'.format(path))

        self.amplitude = float(amplitude)

        # because files can be v memory intensive, we only load the sound once we're called to buffer them
        # store our initialization status
        self.initialized = False

        #self.init_sound()

    def init_sound(self):
        """
        Load the wavfile with :mod:`scipy.io.wavfile` ,
        converting int to float as needed.

        Create a sound table, resampling sound if needed.
        """

        fs, audio = wavfile.read(self.path)
        if audio.dtype in ['int16', 'int32']:
            audio = int_to_float(audio)

        # load file to sound table
        if self.server_type == 'pyo':
            self.dtable = pyo.DataTable(size=audio.shape[0], chnls=prefs.get('NCHANNELS'), init=audio.tolist())

            # get server to determine sampling rate modification and duration
            server_fs = self.dtable.getServer().getSamplingRate()
            self.duration = float(self.dtable.getSize()) / float(fs)
            self.table = pyo.TableRead(table=self.dtable, freq=float(fs) / server_fs,
                                       loop=False, mul=self.amplitude)

        elif self.server_type == 'jack':
            # attenuate amplitude
            audio = audio*self.amplitude
            self.duration = float(audio.shape[0]) / fs
            # resample to match our audio server's sampling rate
            if fs != self.fs:
                new_samples = self.duration*self.fs
                audio = resample(audio, new_samples)

            self.table = audio

        self.initialized = True

class Gap(BASE_CLASS):
    """
    A silent sound that does not pad its final chunk -- used for creating precise silent
    gaps in a continuous noise.

    """

    type = "Gap"
    PARAMS = ['duration']

    def __init__(self, duration, **kwargs):
        """
        Args:
            duration (float): duration of gap in ms

        Attributes:
            gap_zero (bool): True if duration is zero, effectively do nothing on play.
        """
        super(Gap, self).__init__()

        self.duration = float(duration)
        self.gap_zero = False

        if self.duration == 0:
            self.gap_zero = True
            self.get_nsamples()
            self.chunks = []
            self.table = np.ndarray((0,),dtype=np.float32)
            self.initialized = True
        else:

            self.init_sound()

    def init_sound(self):
        """
        Create and chunk an array of zeros according to :attr:`.Gap.duration`
        """
        if self.server_type == "pyo":
            raise NotImplementedError("This sound has not been implemented for pyo sound server -- pyo is deprecated, and kept as a skeleton in the case interested programmers want to revive its use")

        # get the number of samples for the sound given our self.duration
        self.get_nsamples()
        self.table = np.zeros((self.nsamples,), dtype=np.float32)

        # chunk without padding -- jackclient will pad with ongoing continuous noise (or silence if none)
        self.chunk(pad=False)

        self.initialized = True

    def chunk(self, pad=False):
        """
        If gap is not duration == 0, call parent ``chunk``.
        Args:
            pad (bool): unused, passed to parent ``chunk``
        """
        if not self.gap_zero:
            super(Gap, self).chunk(pad)
        else:
            self.padded=False


    def buffer(self):
        if not self.gap_zero:
            super(Gap, self).buffer()
        else:
            self.buffered = True

    def play(self):
        if not self.gap_zero:
            super(Gap, self).play()
        else:
            if callable(self.trigger):
                threading.Thread(target=self.wait_trigger).start()


# These parameters are strings not numbers... jonny should do this better
STRING_PARAMS = ['path', 'type']
"""
These parameters should be given string columns rather than float columns.

Bother Jonny to do this better bc it's really bad.
"""


## Helper function
def int_to_float(audio):
    """
    Convert 16 or 32 bit integer audio to 32 bit float.

    Args:
        audio (:class:`numpy.ndarray`): a numpy array of audio

    Returns:
        :class:`numpy.ndarray`: Audio that has been rescaled and converted to a 32 bit float.
    """
    if audio.dtype == 'int16':
        audio = audio.astype(np.float32)
        audio = audio / (float(2 ** 16) / 2)
    elif audio.dtype == 'int32':
        audio = audio.astype(np.float32)
        audio = audio / (float(2 ** 32) / 2)

    return audio
