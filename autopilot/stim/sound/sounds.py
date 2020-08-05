"""
Classes to play sounds.

Each sound inherits a base type depending on `prefs.AUDIOSERVER`

* `prefs.AUDIOSERVER == 'jack'` : :class:`.Jack_Sound`
* `prefs.AUDIOSERVER == 'pyo'` : :class:`.Pyo_Sound`

To avoid unnecessary dependencies, `Jack_Sound` is not defined if AUDIOSERVER is `'pyo'`
and vice versa.

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

# TODO: Be a whole lot more robust about handling different numbers of channels

import os
import sys
from time import sleep
from scipy.io import wavfile
from scipy.signal import resample
import numpy as np
import threading
import logging
from itertools import cycle
if sys.version_info >= (3,0):
    from queue import Empty, Full
else:
    from Queue import Empty, Full


from autopilot import prefs

# switch behavior based on audio server type
try:
    server_type = prefs.AUDIOSERVER.lower()
except:
#    # TODO: The 'attribute don't exist' type - i think NameError?
    server_type = None



if server_type in ("pyo", "docs"):
    try:
        import pyo
    except ImportError:
        pass

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
                               chnls=prefs.NCHANNELS)  # Prefs should always be declared in the global namespace
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


if server_type in ("jack", "docs", True):
    from autopilot.stim.sound import jackclient

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
            self.duration = None  # duration in ms
            self.amplitude = None
            self.table = None  # numpy array of samples
            self.chunks = None  # table split into a list of chunks
            self.trigger = None
            self.nsamples = None
            self.padded = False # whether or not the sound was padded with zeros when chunked
            self.continuous = False


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
            self.quitting = threading.Event()

            self.initialized = False
            self.buffered = False
            self.buffered_continuous = False

            # FIXME: debugging sound file playback by logging which sounds loaded before crash
            self.logger = logging.getLogger('main')


        def chunk(self, pad=True):
            """
            Split our `table` up into a list of :attr:`.Jack_Sound.blocksize` chunks.

            Args:
                pad (bool): If the sound is not evenly divisible into chunks, pad with zeros (True, default), otherwise jackclient will pad with its continuous sound
            """
            # break sound into chunks

            sound = self.table.astype(np.float32)
            sound_list = [sound[i:i+self.blocksize] for i in range(0, sound.shape[0], self.blocksize)]

            if (sound_list[-1].shape[0] < self.blocksize) and pad:
                sound_list[-1] = np.pad(sound_list[-1],
                                        (0, self.blocksize-sound_list[-1].shape[0]),
                                        'constant')
                self.padded = True
            else:
                self.padded = False

            self.chunks = sound_list

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
            """

            if hasattr(self, 'path'):
                self.logger.info('BUFFERING SOUND {}'.format(self.path))

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



            Returns:

            """

            # FIXME: Initialized should be more flexible,
            # for now just deleting whatever init happened because
            # continuous sounds are in development
            self.table = None
            self.initialized = False

            if not self.initialized and not self.table:
                # try:
                self.quantize_duration()
                self.init_sound()
                self.initialized = True
                # except:
                #     pass
                    #TODO: Log this, better error handling here

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

            # load frames into continuous queue
            for frame in self.chunks:
                self.continuous_q.put_nowait(frame)
            # The jack server looks for a None object to clear the play flag
            # self.continuous_q.put_nowait(None)
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
                self.logger.info('PLAYING SOUND {}'.format(self.path))

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

            # FIXME: Initialized should be more flexible,
            # for now just deleting whatever init happened because
            # continuous sounds are in development
            self.table = None
            self.initialized = False

            self.quantize_duration()
            self.init_sound()
            self.initialized = True
            self.chunk()

            # if not self.buffered_continuous:
            #     self.buffer_continuous()
            self.continuous_cycle = cycle(self.chunks)

            # start the buffering thread
            self.cont_thread = threading.Thread(target=self._buffer_continuous)
            self.cont_thread.setDaemon(True)
            self.cont_thread.start()

            if loop:
                self.continuous_loop.set()
            else:
                self.continuous_loop.clear()


            # tell the sound server that it has a continuous sound now
            self.continuous_flag.set()
            self.continuous = True

        def _buffer_continuous(self):

            # empty queue
            while not self.continuous_q.empty():
                try:
                    _ = self.continuous_q.get_nowait()
                except Empty:
                    # normal, get until it's empty
                    break

            # want to be able to quit if queue remains full for, say, 20 periods
            #wait_time = (self.blocksize/float(self.fs))*20

            while not self.quitting.is_set():
                try:
                    #self.continuous_q.put(self.continuous_cycle.next(), timeout=wait_time)
                    self.continuous_q.put_nowait(self.continuous_cycle.next())
                except Full:
                    pass
            # for chunk in self.chunks:
            #     self.continuous_q.put_nowait(chunk)






        def stop_continuous(self):
            """
            Stop playing a continuous sound

            Should be merged into a general stop method
            """
            if not self.continuous:
                Warning("Not a continous sound!")
                return

            self.quitting.set()
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




else:
    # just importing to query parameters, not play sounds.
    pass





####################
if server_type == "pyo":
    BASE_CLASS = Pyo_Sound
elif server_type == "jack":
    BASE_CLASS = Jack_Sound
else:
    # just importing to query parameters, not play sounds.
    BASE_CLASS = object


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
    """White Noise"""

    PARAMS = ['duration','amplitude']
    type='Noise'
    def __init__(self, duration, amplitude=0.01, **kwargs):
        """
        Args:
            duration (float): duration of the noise
            amplitude (float): amplitude of the sound as a proportion of 1.
            **kwargs: extraneous parameters that might come along with instantiating us
        """
        super(Noise, self).__init__()

        self.duration = float(duration)
        self.amplitude = float(amplitude)

        self.init_sound()

    def init_sound(self):
        """
        Create a table of Noise using pyo or numpy, depending on the server_type
        """

        if self.server_type == 'pyo':
            noiser = pyo.Noise(mul=self.amplitude)
            self.table = self.table_wrap(noiser)
        elif self.server_type == 'jack':
            self.get_nsamples()
            # rand generates from 0 to 1, so subtract 0.5, double to get -1 to 1,
            # then multiply by amplitude.
            self.table = (self.amplitude * np.random.uniform(-1,1,self.nsamples)).astype(np.float32)
            self.chunk()

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
            path (str): Path to a .wav file relative to the `prefs.SOUNDDIR`
            amplitude (float): amplitude of the sound as a proportion of 1.
            **kwargs: extraneous parameters that might come along with instantiating us
        """
        super(File, self).__init__()

        if os.path.exists(path):
            self.path = path
        elif os.path.exists(os.path.join(prefs.SOUNDDIR, path)):
            self.path = os.path.join(prefs.SOUNDDIR, path)
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
            self.dtable = pyo.DataTable(size=audio.shape[0], chnls=prefs.NCHANNELS, init=audio.tolist())

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


class Speech(File):
    """
    Speech subclass of File sound.

    Example of custom sound class - PARAMS are changed, but nothing else.
    """

    type='Speech'
    PARAMS = ['path', 'amplitude', 'speaker', 'consonant', 'vowel', 'token']
    def __init__(self, path, speaker, consonant, vowel, token, amplitude=0.05, **kwargs):
        """
        Args:
            speaker (str): Which Speaker recorded this speech token?
            consonant (str): Which consonant is in this speech token?
            vowel (str): Which vowel is in this speech token?
            token (int): Which token is this for a given combination of speaker, consonant, and vowel
        """
        super(Speech, self).__init__(path, amplitude, **kwargs)

        self.speaker = speaker
        self.consonant = consonant
        self.vowel = vowel
        self.token = token

        # sound is init'd in the superclass

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













#######################
# Has to be at bottom so fnxns already defined when assigned.
SOUND_LIST = {
    'Tone':Tone,
    'Noise':Noise,
    'File':File,
    'Speech':Speech,
    'speech':Speech,
    'Gap': Gap
}
"""
Sounds must be added to this SOUND_LIST so they can be indexed by the string keys used elsewhere. 
"""

# These parameters are strings not numbers... jonny should do this better
STRING_PARAMS = ['path', 'speaker', 'consonant', 'vowel', 'type']
"""
These parameters should be given string columns rather than float columns.

Bother Jonny to do this better.

v0.3 will be all about doing parameters better.
"""


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












