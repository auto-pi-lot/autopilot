"""
Base classes for sound objects, depending on the selected audio backend. Use the ``'AUDIOSERVER'`` pref to select, or else
use the :func:`.default_sound_class` function.
"""
import typing
import sys
from warnings import warn
from queue import Empty
from abc import abstractmethod
import threading
from time import sleep
from itertools import cycle

import numpy as np

from autopilot import prefs
from autopilot import dehydrate
from autopilot.utils.loggers import init_logger
from autopilot.utils.requires import Requirements, Python_Package
from autopilot.stim.stim import Stim
from autopilot.utils.decorators import Introspect

Backends = {
    'pyo': Python_Package('pyo'),
    'jack': Requirements([
        Python_Package(
            'jack',
            package_name='JACK-Client') # TODO: Add jack system
        # System_Library(
        #   'jackd2',
        #   bin_name = 'jackd',
        #   install_script = autopilot.setup.SCRIPTS['jackd_source'],
        #   ...
        # )
    ]),
    'dummy': True,
    'docs': True
}



class Sound(Stim):
    """
    Dummy metaclass for sound base-classes. Allows Sounds to be used without a backend to,
    eg. synthesize waveforms and the like.

    Placeholder pending a full refactoring of class structure
    """
    PARAMS = []
    type = None
    server_type = 'dummy'

    @Introspect()
    def __init__(self,
        fs: int = None,
        duration: float = None,
        **kwargs
    ):
        if fs is None:
            raise ValueError('Dummy classes must be passed an explicit fs (sampling rate) argument, as it cannot be inferred from the server (since there is none)')
        self.fs = fs
        self.duration = duration
        self.logger = init_logger(self)

        self.table = None # type: typing.Optional[np.ndarray]
        self.initialized = False

    def get_nsamples(self):
        """
        given our fs and duration, how many samples do we need?

        literally::

            np.ceil((self.duration/1000.)*self.fs).astype(int)

        """
        self.nsamples = np.ceil((self.duration / 1000.) * self.fs).astype(int)


## Import the required modules
if Backends['jack'].met or 'pytest' in sys.modules:
    # This will warn if the jack library is not found
    from autopilot.stim.sound import jackclient

if Backends['pyo'].met:
    import pyo

class Pyo_Sound(Stim):
    """
    Metaclass for pyo sound objects.

    Note:
        Use of pyo is generally discouraged due to dropout issues and
        the general opacity of the module. As such this object is
        intentionally left undocumented.

    """

    @Introspect()
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

class Jack_Sound(Stim):
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

    @Introspect()
    def __init__(self,
                 jack_client: typing.Optional['autopilot.stim.sound.jackclient.JackClient'] = None,
                 **kwargs):
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
        self.padded = False  # whether or not the sound was padded with zeros when chunked
        self.continuous = False

        # Initialize a logger
        self.logger = init_logger(self)

        if jack_client is not None:
            self.logger.debug('Getting jack_client objects from passed jackclient')
            self.server = jack_client
            self.continuous_flag = self.server.continuous
            for attr in ('fs', 'blocksize', 'q', 'q_lock', 'play_evt', 'stop_evt',
                         'continuous_q', 'continuous_loop'):
                setattr(self, attr, getattr(jack_client, attr))

        else:
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

    @abstractmethod
    def init_sound(self):
        """
        Abstract method to initialize sound. Should set the :attr:`.table` attribute

        .. todo::

            ideally should standardize by returning an array, but pyo objects don't return arrays necessarily...
        """

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
            sound_list = [sound[i:i + self.blocksize] for i in range(0, sound.shape[0], self.blocksize)]

        elif sound.ndim == 2:
            sound_list = [sound[i:i + self.blocksize, :] for i in range(0, sound.shape[0], self.blocksize)]

        else:
            raise NotImplementedError(f"sounds with more than 2 dimensions arent supported, got ndim {sound.ndim}")

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
        self.stop_evt.wait((self.duration + 1000) / 1000.)
        # if the sound actually stopped...
        if self.stop_evt.is_set():
            self.trigger()

    def get_nsamples(self):
        """
        given our fs and duration, how many samples do we need?

        literally::

            np.ceil((self.duration/1000.)*self.fs).astype(int)

        """
        self.nsamples = np.ceil((self.duration / 1000.) * self.fs).astype(int)

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
            target_samples = np.ceil(float(self.nsamples) / self.blocksize) * self.blocksize
        else:
            target_samples = np.floor(float(self.nsamples) / self.blocksize) * self.blocksize

        # get new duration
        self.duration = (target_samples / self.fs) * 1000.

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
                # TODO: Log this, better error handling here

        if not self.chunks:
            self.chunk()

        with self.q_lock:
            # empty queue
            # FIXME: Testing whether this is where we get held up on the 'fail after sound play' bug
            # n_gets = 0
            # while not self.q.empty():
            #     try:
            #         _ = self.q.get_nowait()
            #     except Empty:
            #         # normal, get until it's empty
            #         break
                # n_gets += 1
                # if n_gets > 100000:
                #     break
            # for frame in self.chunks:
            self.q.put_nowait([*self.chunks, None])
            # The jack server looks for a None object to clear the play flag
            # self.q.put_nowait(None)
            self.buffered = True

    def _init_continuous(self):
        """
        Create a duration quantized table for playing continuously
        """
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
            raise Exception(
                "Continuous sounds cannot have padded chunks - sounds need to have n_samples % blocksize == 0")

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
        # self._init_continuous()

        # Give a dehydrated version of ourself
        while not self.continuous_q.empty():
            try:
                _ = self.continuous_q.get_nowait()
            except Empty:
                # normal, get until it's empty
                break

        # put all the chunks into the queue, rather than one at a time
        # to avoid partial receipt
        self.continuous_q.put(dehydrate(self))

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

        self.logger.debug('played!')

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

    def iter_continuous(self) -> typing.Generator:
        """
        Continuously yield frames of audio. If this method is not overridden,
        just wraps :attr:`.table` in a :class:`itertools.cycle` object and
        returns from it.

        Returns:
            np.ndarray: A single frame of audio
        """
        self._init_continuous()
        iterator = cycle(self.chunks)
        yield from iterator



    def stop_continuous(self):
        """
        Stop playing a continuous sound

        Should be merged into a general stop method
        """
        if not self.continuous:
            self.logger.warning("stop_continuous called but not a continuous sound!")
            return
        self.logger.debug('stop_continuous sound called')
        self.continuous_flag.clear()
        self.continuous_loop.clear()

    def end(self):
        """
        Release any resources held by this sound

        """
        self.logger.debug('end_sound called')

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



def get_sound_class(server_type: typing.Optional[str] = None) -> typing.Union[typing.Type[Sound],typing.Type[Jack_Sound],typing.Type[Pyo_Sound]]:
    """
    Get the default sound class as defined by ``'AUDIOSERVER'``

    This function is also a convenience class for testing whether a particular audio backend is available


    Returns:

    """

    ## First, switch the behavior based on the pref AUDIOSERVER
    # Get the pref
    if server_type is None:
        server_type = prefs.get('AUDIOSERVER')


    # True is a synonym for 'jack', the default server
    if server_type == True:
        server_type = 'jack'
    elif server_type is None:
        server_type = 'dummy'

    # Force lower-case if string
    try:
        server_type = server_type.lower()
    except AttributeError:
        pass

    # From now on, server_type should be 'jack', 'pyo', 'docs', or None
    if server_type not in Backends.keys():
        if server_type is not False:
            warn(f'Requested server type {server_type}, but it doesnt exist. Using dummy')
        server_type = 'dummy'

    # if we're testing, set server_type to jack
    if 'pytest' in sys.modules:
        server_type = 'jack'
        return Jack_Sound

    # check if requirements are met, if so, return the object. Otherwise return dummy.
    if server_type == 'jack' and Backends['jack'].met:
        return Jack_Sound
    elif server_type == 'pyo' and Backends['pyo'].met:
        return Pyo_Sound
    elif server_type == 'dummy':
        return Sound
    else:
        warn(f'requested server_type {server_type} but its requirements arent met. Using dummy')
        return Sound


