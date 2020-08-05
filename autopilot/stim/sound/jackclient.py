"""
Client that dumps samples directly to the jack client with the :mod:`jack` package.
"""




import multiprocessing as mp
import queue as queue
import numpy as np
from copy import copy
from threading import Thread
from itertools import cycle
from queue import Empty
import sys

# importing configures environment variables necessary for importing jack-client module below
from autopilot import external

try:
    import jack
except OSError as e:
    print('jack library not found! sounds unavailable')
    # print(e)
    # install_jack = input('Try to install jackd? (y/n): ')
    # if install_jack == "y":
    #     from autopilot.setup.setup_autopilot import run_script
    #     run_script('jackd')
    #     import jack
    # else:
    #     raise e


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

    When first initialized, sets module level variables above.

    Attributes:
        name (str): name of client, default "jack_client"
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
    """
    def __init__(self, name='jack_client'):
        """
        Args:
            name:
        """
        super(JackClient, self).__init__()

        # TODO: If global client variable is set, just return that one.

        self.name = name
        #self.pipe = pipe
        self.q = mp.Queue()
        self.q_lock = mp.Lock()

        self.play_evt = mp.Event()
        self.stop_evt = mp.Event()
        self.quit_evt = mp.Event()

        # we make a client that dies now so we can stash the fs and etc.
        self.client = jack.Client(self.name)
        self.blocksize = self.client.blocksize
        self.fs = self.client.samplerate
        self.zero_arr = np.zeros((self.blocksize,1),dtype='float32')

        # a few objects that control continuous/background sound.
        # see descriptions in module variables
        self.continuous = mp.Event()
        self.continuous_q = mp.Queue(maxsize=1024)
        self.continuous_loop = mp.Event()
        self.continuous.clear()
        self.continuous_loop.clear()
        self.continuous_started = False

        # store the frames of the continuous sound and cycle through them if set in continous mode
        self.continuous_cycle = None


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

    def boot_server(self):
        """
        Called by :meth:`.JackClient.run` to boot the server upon starting the process.

        Activates the client and connects it to the number of outports
        determined by `prefs.NCHANNELS`

        :class:`jack.Client` s can't be kept alive, so this must be called just before
        processing sample starts.
        """

        self.client = jack.Client(self.name)
        self.blocksize = self.client.blocksize
        self.fs = self.client.samplerate
        self.zero_arr = np.zeros((self.blocksize,1),dtype='float32')

        self.client.set_process_callback(self.process)

        self.client.outports.register('out_0')

        self.client.activate()
        target_ports = self.client.get_ports(is_physical=True, is_input=True, is_audio=True)

        if hasattr(prefs, 'OUTCHANNELS'):
            if isinstance(prefs.OUTCHANNELS, list):
                for outchan in prefs.OUTCHANNELS:

                    self.client.outports[0].connect(target_ports[int(outchan)])
            elif isinstance(prefs.OUTCHANNELS, int):
                self.client.outports[0].connect(target_ports[prefs.OUTCHANNELS])
            elif isinstance(prefs.OUTCHANNELS, str):
                try:
                    self.client.outports[0].connect(target_ports[int(prefs.OUTCHANNELS)])
                except TypeError:
                    Exception('Could not coerce prefs.OUTCHANNELS to an integer or list of ints. Connecting to port 0. got {}'.format(prefs.OUTCHANNELS))
                    self.client.outports[0].connect(target_ports[0])
        else:
            self.client.outports[0].connect(target_ports[0])
            if prefs.NCHANNELS == 2:
                # TODO: Limited, obvs. want to handle arbitrary output arrangements.
                self.client.outports[0].connect(target_ports[1])

    def run(self):
        """
        Start the process, boot the server, start processing frames and wait for the end.
        """

        self.boot_server()

        # we are just holding the process open, so wait to quit
        try:
            self.quit_evt.clear()
            self.quit_evt.wait()
        except KeyboardInterrupt:
            # just want to kill the process, so just continue from here
            pass


    # def close(self):
    #     # TODO: shut down server but also reset module level variables
    #     pass

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

        Warning:
            Handling multiple outputs is a little screwy right now. v0.2 effectively only supports one channel output.

        Args:
            frames: number of frames (samples) to be processed. unused. passed by jack client
        """
        if not self.play_evt.is_set():
            # if we are in continuous mode...
            if self.continuous.is_set():

                try:
                    data = self.continuous_q.get_nowait()

                except Empty:
                    # TODO: Logging for sound client
                    Warning('Continuous queue was empty!')
                    #self.continuous.clear()
                    data = self.zero_arr

                self.client.outports[0].get_array()[:] = data.T

                # if not self.continuous_started:
                #     # if we are just entering continuous mode, get the continuous sound and prepare to play it
                #     continuous_frames = []
                #     while not self.continuous_q.empty():
                #         try:
                #             continuous_frames.append(self.continuous_q.get_nowait())
                #         except Empty:
                #             break
                #     self.continuous_cycle = cycle(continuous_frames)
                #     self.continuous_started = True
                #
                # # FIXME: Multichannel sound....
                # self.client.outports[0].get_array()[:] = self.continuous_cycle.next().T

            else:
                for channel, port in zip(self.zero_arr.T, self.client.outports):
                    port.get_array()[:] = channel
        else:

            try:
                data = self.q.get_nowait()
            except queue.Empty:
                data = None
                Warning('Queue Empty')
            if data is None:
                # fill with continuous noise
                if self.continuous.is_set():
                    #self.client.outports[0].get_array()[:] = self.continuous_cycle.next().T
                    try:
                        data = self.continuous_q.get_nowait()
                    except Empty:
                        # TODO: Logging for sound client
                        Warning('Continuous queue was empty!')
                        # self.continuous.clear()
                        data = self.zero_arr
                        #self.continuous.clear()

                    self.client.outports[0].get_array()[:] = data.T


                else:
                    for channel, port in zip(self.zero_arr.T, self.client.outports):
                        port.get_array()[:] = channel
                # sound is over
                self.play_evt.clear()
                self.stop_evt.set()
            else:
                if data.shape[0] < self.blocksize:
                    # if sound was not padded, fill remaining with continuous sound or silence
                    n_from_end = self.blocksize - data.shape[0]
                    if self.continuous.is_set():
                        # data = np.concatenate((data, self.continuous_cycle.next()[-n_from_end:]),
                        #                       axis=0)
                        cont_data = self.continuous_q.get_nowait()
                        data = np.concatenate((data, cont_data[-n_from_end:]),
                                              axis=0)
                    else:
                        data = np.pad(data, (0, n_from_end), 'constant')
                #TODO: Fix the multi-output situation so it doesn't get all grumbly.
                # use cycle so if sound is single channel it gets copied to all outports

                self.client.outports[0].get_array()[:] = data.T
                #for channel, port in zip(cycle(data.T), self.client.outports):
                #    port.get_array()[:] = channel




