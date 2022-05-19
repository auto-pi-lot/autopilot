"""
Client that dumps samples directly to the jack client with the :mod:`jack` package.

.. note::

    The latest version of raspiOS (bullseye) causes a lot of problems with the Jack audio that we have not figured out a workaround for.
    If you intend to use sound, we recommend sticking with Buster for now (available from their `legacy downloads <https://www.raspberrypi.com/software/operating-systems/#raspberry-pi-os-legacy>`_ section).

"""
import typing
import multiprocessing as mp
import queue as queue
import numpy as np
from copy import copy
from queue import Empty
import time
from threading import Thread
from collections import deque
import gc
if typing.TYPE_CHECKING:
    pass


# importing configures environment variables necessary for importing jack-client module below
import autopilot
from autopilot.utils.loggers import init_logger

try:
    import jack
except (OSError, ModuleNotFoundError):
    print('jack library not found! sounds unavailable')

from autopilot import prefs

# allows us to access the audio server and some sound attributes
SERVER = None
"""
:class:`.JackClient`: After initializing, JackClient will register itself with this variable.
"""

FS = None
"""
int: Sampling rate of the active server
"""

BLOCKSIZE = None
"""
int: Blocksize, or the amount of samples processed by jack per each :meth:`.JackClient.process` call.
"""

QUEUE = None
"""
:class:`multiprocessing.Queue`: Queue to be loaded with frames of BLOCKSIZE audio.
"""

PLAY = None
"""
:class:`multiprocessing.Event`: Event used to trigger loading samples from `QUEUE`, ie. playing.
"""

STOP = None
"""
:class:`multiprocessing.Event`: Event that is triggered on the end of buffered audio.

Note:
    NOT an event used to stop audio.
"""

Q_LOCK = None
"""
:class:`multiprocessing.Lock`: Lock that enforces a single writer to the `QUEUE` at a time.
"""

CONTINUOUS = None
"""
:class:`multiprocessing.Event`: Event that (when set) signals the sound server should play some sound continuously rather than remain silent by default (eg. play a background sound).

"""

CONTINUOUS_QUEUE = None
"""
:class:`multiprocessing.Queue`: Queue that 
"""

CONTINUOUS_LOOP = None
"""
:class:`multiprocessing.Event`: Event flag that is set when frames dropped into the CONTINUOUS_QUEUE should be looped (eg. in the case of stationary background noise),
otherwise they are played and then discarded (ie. the sound is continuously generating and submitting samples)
"""

class JackClient(mp.Process):
    """
    Client that dumps frames of audio directly into a running jackd client.

    See the :meth:`.process` method to see how the client works in detail, but
    as a narrative overview:

    * The client interacts with a running jackd daemon, typically launched with :func:`.external.start_jackd`
      The jackd process is configured with the ``JACKDSTRING`` pref, which by default is built from other parameters
      like the ``FS`` sampling rate et al.
    * :class:`multiprocessing.Event` objects are used to synchronize state within the client,
      eg. the play event signals that the client should begin to pull frames from the sound queue
    * :class:`multiprocessing.Queue` objects are used to send samples to the client,
      specifically chunks samples with length ``BLOCKSIZE``
    * The general pattern of using both together is to load a queue with chunks of samples and then set the
      play event.
    * Jackd will call the ``process`` method repeatedly, within which this class will check the state
      of the event flags and pull from the appropriate queues to load the samples into jackd's audio buffer

    When first initialized, sets module level variables above, which are the public
    hooks to use the client. Within autopilot, the module-level variables are used, but
    if using the jackclient or sound system outside of a typical autopilot context, you can
    instantiate a JackClient and then pass it to sounds as ``jack_client``.

    Args:
        name (str): name of client, default "jack_client"
        outchannels (list): Optionally manually pass outchannels rather than getting
            from prefs. A list of integers corresponding to output channels to initialize.
            if ``None`` (default), get ``'OUTCHANNELS'`` from prefs
        play_q_size (int): Number of frames that can be buffered (with :meth:`~.sound.base.Jack_Sound.buffer` ) at a time
        disable_gc (bool): If ``True``, turn off garbage collection in the jack client process (experimental)

    Attributes:
        q (:class:`~.multiprocessing.Queue`): Queue that stores buffered frames of audio
        q_lock (:class:`~.multiprocessing.Lock`): Lock that manages access to the Queue
        play_evt (:class:`multiprocessing.Event`): Event used to trigger loading samples from `QUEUE`, ie. playing.
        stop_evt (:class:`multiprocessing.Event`): Event that is triggered on the end of buffered audio.
        quit_evt (:class:`multiprocessing.Event`): Event that causes the process to be terminated.
        client (:class:`jack.Client`): Client to interface with jackd
        blocksize (int): The blocksize - ie. samples processed per :meth:`.JackClient.process` call.
        fs (int): Sampling rate of client
        zero_arr (:class:`numpy.ndarray`): cached array of zeroes used to fill jackd pipe when not processing audio.
        continuous_cycle (:class:`itertools.cycle`): cycle of frames used for continuous sounds
        mono_output (bool): ``True`` or ``False`` depending on if the number of output channels is 1 or >1, respectively.
            detected and set in :meth:`.JackClient.boot_server` , initialized to ``True`` (which is hopefully harmless)
    """
    def __init__(self,
                 name='jack_client',
                 outchannels: typing.Optional[list] = None,
                 debug_timing:bool=False,
                 play_q_size:int=2048,
                 disable_gc=False):
        """
        Args:
            name:
        """
        super(JackClient, self).__init__()

        # TODO: If global client variable is set, just return that one.

        self.name = name
        if outchannels is None:
            self.outchannels = prefs.get('OUTCHANNELS')
        else:
            self.outchannels = outchannels

        #self.pipe = pipe
        self.q = mp.Queue()
        self.q_lock = mp.Lock()
        self._play_q = deque(maxlen=play_q_size)

        self.play_evt = mp.Event()
        self.stop_evt = mp.Event()
        self.quit_evt = mp.Event()
        self.play_started = mp.Event()
        """set after the first frame of a sound is buffered, used to keep track internally when sounds are started and stopped."""

        # we make a client that dies now so we can stash the fs and etc.
        self.client = jack.Client(self.name)
        self.blocksize = self.client.blocksize
        self.fs = self.client.samplerate
        self.zero_arr = np.zeros((self.blocksize,1),dtype='float32')

        # a few objects that control continuous/background sound.
        # see descriptions in module variables
        self.continuous = mp.Event()
        self.continuous_q = mp.Queue()
        self.continuous_loop = mp.Event()
        self.continuous_cycle = None
        self.continuous.clear()
        self.continuous_loop.clear()
        self._continuous_sound = None # type: typing.Optional['Jack_Sound']
        self._continuous_dehydrated = None

        # store the frames of the continuous sound and cycle through them if set in continous mode
        self.continuous_cycle = None

        # Something calls process() before boot_server(), so this has to
        # be initialized
        self.mono_output = True

        self._disable_gc = disable_gc

        # store a reference to us and our values in the module
        globals()['SERVER'] = self
        globals()['FS'] = copy(self.fs)
        globals()['BLOCKSIZE'] = copy(self.blocksize)
        globals()['QUEUE'] = self.q
        globals()['Q_LOCK'] = self.q_lock
        globals()['PLAY'] = self.play_evt
        globals()['STOP'] = self.stop_evt
        globals()['CONTINUOUS'] = self.continuous
        globals()['CONTINUOUS_QUEUE'] = self.continuous_q
        globals()['CONTINUOUS_LOOP'] = self.continuous_loop

        self.logger = init_logger(self)

        if self.fs != prefs.get('FS'):
            self.logger.warning(
                f"Sampling rate was set to {prefs.get('FS')} in prefs, but the jack audio daemon is running at {self.fs}. \
                Check that jackd was not already running, and is being correctly started by autopilot (see autopilot.external)")

        self.debug_timing = debug_timing
        self.querythread = None
        self.wait_until = None
        self.alsa_nperiods = prefs.get('ALSA_NPERIODS')
        if self.alsa_nperiods is None:
            self.alsa_nperiods = 1

    def boot_server(self):
        """
        Called by :meth:`.JackClient.run` to boot the server upon starting the process.

        Activates the client and connects it to the physical speaker outputs
        as determined by `prefs.get('OUTCHANNELS')`.

        This is the interpretation of OUTCHANNELS:
        * empty string
            'mono' audio: the same sound is always played to all channels. 
            Connect a single virtual outport to every physical channel.
            If multi-channel sound is provided, raise an error.
        * a single int (example: J)
            This is equivalent to [J].
            The first virtual outport will be connected to physical channel J.
            Note this is NOT the same as 'mono', because only one speaker
            plays, instead of all speakers.
        * a list (example: [I, J])
            The first virtual outport will be connected to physical channel I.
            The second virtual outport will be connected to physical channel J.
            And so on.    
            If 1-dimensional sound is provided, play the same to all speakers
            (like mono mode).
            If multi-channel sound is provided and the number of channels
            is different form the length of this list, raise an error.        

        :class:`jack.Client` s can't be kept alive, so this must be called just before
        processing sample starts.
        """
        ## Parse OUTCHANNELS into listified_outchannels and set `self.mono_output`
        
        # This generates `listified_outchannels`, which is always a list
        # It also sets `self.mono_output` if outchannels is None
        if self.outchannels == '':
            # Mono mode
            listified_outchannels = []
            self.mono_output = True
        elif not isinstance(self.outchannels, list):
            # Must be a single integer-like thing
            listified_outchannels = [int(self.outchannels)]
            self.mono_output = False
        else:
            # Already a list
            listified_outchannels = self.outchannels
            self.mono_output = False
        
        ## Initalize self.client
        # Initalize a new Client and store some its properties
        # I believe this is how downstream code knows the sample rate
        self.client = jack.Client(self.name)
        self.blocksize = self.client.blocksize
        self.fs = self.client.samplerate
        
        # This is used for writing silence
        self.zero_arr = np.zeros((self.blocksize,1),dtype='float32')

        # Set the process callback to `self.process`
        # This gets called on every chunk of audio data
        self.client.set_process_callback(self.process)

        # Register virtual outports
        # This is something we can write data into
        if self.mono_output:
            # One single outport
            self.client.outports.register('out_0')
        else:
            # One outport per provided outchannel
            for n in range(len(listified_outchannels)):
                self.client.outports.register('out_{}'.format(n))

        # Activate the client
        self.client.activate()
        self.logger.debug('client activated')


        ## Hook up the outports (data sinks) to physical ports
        # Get the actual physical ports that can play sound
        target_ports = self.client.get_ports(
            is_physical=True, is_input=True, is_audio=True)

        # Depends on whether we're in mono mode
        if self.mono_output:
            ## Mono mode
            # Hook up one outport to all channels
            for target_port in target_ports:
                self.client.outports[0].connect(target_port)
        
        else:
            ## Not mono mode
            # Error check
            if len(listified_outchannels) > len(target_ports):
                raise ValueError(
                    "cannot connect {} ports, only {} available".format(
                    len(listified_outchannels),
                    len(target_ports),))
            
            # Hook up one outport to each channel
            for n in range(len(listified_outchannels)):
                # This is the channel number the user provided in OUTCHANNELS
                index_of_physical_channel = listified_outchannels[n]
                
                # This is the corresponding physical channel
                # I think this will always be the same as index_of_physical_channel
                physical_channel = target_ports[index_of_physical_channel]
                
                # Connect virtual outport to physical channel
                self.client.outports[n].connect(physical_channel)

    def run(self):
        """
        Start the process, boot the server, start processing frames and wait for the end.
        """
        self.logger = init_logger(self)
        self.boot_server()
        self.logger.debug('server booted')

        if self._disable_gc:
            gc.disable()
            self.logger.info('GC Disabled!')

        if self.debug_timing:
            self.querythread = Thread(target=self._query_timebase)
            self.querythread.start()

        # we are just holding the process open, so wait to quit
        try:
            self.quit_evt.clear()
            self.quit_evt.wait()
        except KeyboardInterrupt:
            # just want to kill the process, so just continue from here
            self.quit_evt.set()

    def quit(self):
        """
        Set the :attr:`.JackClient.quit_evt`
        """
        self.quit_evt.set()

    def process(self, frames):
        """
        Process a frame of audio.

        If the :attr:`.JackClient.play_evt` is not set, fill port buffers with zeroes.

        Otherwise, pull frames of audio from the :attr:`.JackClient.q` until it's empty.

        When it's empty, set the :attr:`.JackClient.stop_evt` and clear the :attr:`.JackClient.play_evt` .

        Args:
            frames: number of frames (samples) to be processed. unused. passed by jack client
        """
        if self.debug_timing:
            state, pos = self.client.transport_query()
            self.logger.debug(f'inproc - frame_time: {self.client.frame_time}, last_frame_time: {self.client.last_frame_time}, usecs: {pos["usecs"]}, frames: {self.client.frames_since_cycle_start}')

        ## Switch on whether the play event is set
        if not self.play_evt.is_set():
            # A play event has not been set
            # Play only if we are in continuous mode, otherwise write zeros
            
            ## Switch on whether we are in continuous mode
            if self.continuous.is_set():
                # We are in continuous mode, keep playing
                # check if the continuous sound has changed, even if we already have one
                try:
                    to_cycle = self.continuous_q.get_nowait()
                    if self._continuous_dehydrated is None or self._continuous_dehydrated != to_cycle:
                        self._continuous_dehydrated = to_cycle
                        self._continuous_sound = autopilot.hydrate(self._continuous_dehydrated)
                        self.continuous_cycle = self._continuous_sound
                        self.logger.debug(f'got new continuous sound: {self._continuous_dehydrated}')
                    elif self._continuous_dehydrated == to_cycle:
                        self.logger.debug(f'received a new continuous sound, but was identical to old sound. not rehydrating')

                    self.continuous_cycle = self._continuous_sound.iter_continuous()

                except Empty:
                    if self.continuous_cycle is None:
                        self.logger.exception('told to play continuous sound but nothing in queue, will try again next loop around')
                        self.write_to_outports(self.zero_arr.T)
                        return

                # Get the data to play
                data = next(self.continuous_cycle).T
                
                # Write
                self.write_to_outports(data)

            else:
                # We are not in continuous mode, play silence
                # clear continuous sound after it's done
                if self.continuous_cycle is not None:
                    self.logger.debug('continuous flag cleared')
                    self.continuous_cycle = None

                # Play zeros
                data = self.zero_arr.T
                
                # Write
                self.write_to_outports(data)

        else:
            # A play event has been set
            # Play a sound

            # Try to get data
            try:
                data = self._play_q.popleft()
                if self.debug_timing:
                    self.logger.debug('Got new audio samples')
            except IndexError:
                data = None
                self.logger.warning('Queue Empty')

            ## Switch on whether data is available
            if data is None:
                # fill with continuous noise
                if self.continuous.is_set():
                    try:
                        data = next(self.continuous_cycle)
                    except Exception as e:
                        self.logger.exception(f'Continuous mode was set but got exception with continuous queue:\n{e}')
                        data = self.zero_arr

                else:
                    # Play zeros
                    data = np.zeros(self.blocksize, dtype='float32')

                # Write data
                self.write_to_outports(data)


                # sound is over
                self.play_evt.clear()
                # end time is just the start of the next frame??
                self.wait_until = self.client.last_frame_time+(self.blocksize*self.alsa_nperiods)
                # Thread(target=self._wait_for_end, args=(self.client.last_frame_time+self.blocksize,)).start()
                if self.debug_timing:
                    self.logger.debug(f'Sound has ended, requesting end event at {self.wait_until}')

                if self._disable_gc:
                    gc.collect()

            else:
                ## There is data available
                if data.shape[0] < self.blocksize:
                    data = self._pad_continuous(data)
                    # sound is over!
                    self.wait_until = self.client.last_frame_time + (self.blocksize*self.alsa_nperiods) + data.shape[0]
                    if self.debug_timing:
                        self.logger.debug(
                            f'Sound has ended, size {data.shape[0]}, requesting end event at {self.wait_until}')
                    self.play_evt.clear()

                # Write
                self.write_to_outports(data)


            # start timer if we haven't yet
            if self.querythread is None:
                self.querythread = Thread(target=self._wait_for_end)
                self.querythread.start()

        # try to get samples every loop, store and wait for the play event to be set
        try:
            self._play_q.extend(self.q.get_nowait())
        except queue.Empty:
            # fine, no samples have been given to us
            pass

    
    def write_to_outports(self, data):
        """Write the sound in `data` to the outport(s).
        
        If self.mono_output:
            If data is 1-dimensional:
                Write that data to the single outport, which goes to all
                speakers.
            Otherwise, raise an error.
        
        If not self.mono_output:
            If data is 1-dimensional:
                Write that data to every outport
            If data is 2-dimensional:
                Write one column to each outport, raising an error if there
                is a different number of columns than outports.
        """
        data = data.squeeze()

        ## Write the output to each outport
        if self.mono_output:
            ## Mono mode - Write the same data to all channels
            if data.ndim == 1:
                # Write data to one outport, which is hooked up to all channels
                buff = self.client.outports[0].get_array()
                buff[:] = data
            
            else:
                # Stereo data provided, this is an error
                raise ValueError(
                    "pref OUTCHANNELS indicates mono mode, but "
                    "data has shape {}".format(data.shape))
            
        else:
            ## Multi-channel mode - Write a column to each channel
            if data.ndim == 1:
                ## 1-dimensional sound provided
                # Write the same data to each channel
                for outport in self.client.outports:
                    buff = outport.get_array()
                    buff[:] = data
                
            elif data.ndim == 2:
                ## Multi-channel sound provided
                # Error check
                if data.shape[1] != len(self.client.outports):
                    raise ValueError(
                        "data has {} channels "
                        "but only {} outports in pref OUTCHANNELS".format(
                        data.shape[1], len(self.client.outports)))
                
                # Write one column to each channel
                for n_outport, outport in enumerate(self.client.outports):
                    buff = outport.get_array()
                    buff[:] = data[:, n_outport]
                
            else:
                ## What would a 3d sound even mean?
                raise ValueError(
                    "data must be 1 or 2d, not {}".format(data.shape))

    def _pad_continuous(self, data:np.ndarray) -> np.ndarray:
        """
        When playing a sound in :meth:`.process`, if we're given a sound that is less than the blocksize,
        pad it with either silence or the continuous sound

        Returns:

        """
        # if sound was not padded, fill remaining with continuous sound or silence
        n_from_end = self.blocksize - data.shape[0]
        if self.continuous.is_set():
            try:
                cont_data = next(self.continuous_cycle)
                data = np.concatenate((data, cont_data[-n_from_end:]),
                                      axis=0)
            except Exception as e:
                self.logger.exception(f'Continuous mode was set but got exception with continuous queue:\n{e}')
                pad_with = [(0, n_from_end)]
                pad_with.extend([(0, 0) for i in range(len(data.ndim-1))])
                data = np.pad(data, pad_with, 'constant')
        else:
            pad_with = [(0, n_from_end)]
            pad_with.extend([(0, 0) for i in range(len(data.ndim - 1))])
            data = np.pad(data, pad_with, 'constant')

        return data

    def _wait_for_end(self):
        """
        Thread that waits for a time (returned by :attr:`jack.Client.frame_time`) passed as ``end_time``
        and then sets :attr:`.JackClient.stop_evt`

        Args:
            end_time (int): the ``frame_time`` at which to set the event
        """
        try:
            while self.wait_until is None or self.client.frame_time < self.wait_until:
                time.sleep(0.000001)
        finally:
            if self.debug_timing:
                self.logger.debug(f'stop event set at f{self.client.frame_time}, requested {self.wait_until}')
            self.stop_evt.set()
            self.querythread = None
            self.wait_until = None

    def _query_timebase(self):
        while not self.quit_evt.is_set():
            state, pos = self.client.transport_query()
            self.logger.debug(
                f'query thread - frame_time: {self.client.frame_time}, last_frame_time: {self.client.last_frame_time}, usecs: {pos["usecs"]}, frames: {self.client.frames_since_cycle_start}')
            time.sleep(0.00001)



