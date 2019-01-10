


from __future__ import division
from __future__ import print_function

import multiprocessing as mp
import Queue as queue
import jack
import numpy as np
from copy import copy
from threading import Thread
from itertools import cycle

import prefs


# allows us to access the audio server and some sound attributes
SERVER = None
FS = None
BLOCKSIZE = None
QUEUE = None
PLAY = None
Q_LOCK = None


class JackClient(mp.Process):
    def __init__(self, name='jack_client'):
        super(JackClient, self).__init__()

        self.name = name
        #self.pipe = pipe
        self.q = mp.Queue()
        self.q_lock = mp.Lock()

        self.play_evt = mp.Event()
        self.quit_evt = mp.Event()

        # we make a client that dies now so we can stash the fs and etc.
        self.client = jack.Client(self.name)
        self.blocksize = self.client.blocksize
        self.fs = self.client.samplerate
        self.zero_arr = np.zeros((self.blocksize,1),dtype='float32')

        # store a reference to us and our values in the module
        globals()['SERVER'] = self
        globals()['FS'] = copy(self.fs)
        globals()['BLOCKSIZE'] = copy(self.blocksize)
        globals()['QUEUE'] = self.q
        globals()['Q_LOCK'] = self.q_lock
        globals()['PLAY'] = self.play_evt

    def boot_server(self):
        self.client = jack.Client(self.name)
        self.blocksize = self.client.blocksize
        self.fs = self.client.samplerate
        self.zero_arr = np.zeros((self.blocksize,1),dtype='float32')

        self.client.set_process_callback(self.process)

        self.client.outports.register('out_0')

        self.client.activate()
        target_ports = self.client.get_ports(is_physical=True, is_input=True, is_audio=True)
        self.client.outports[0].connect(target_ports[0])
        if prefs.NCHANNELS ==2 :
            self.client.outports[0].connect(target_ports[1])

    def run(self):
        self.boot_server()

        # we are just holding the process open, so wait to quit
        try:
            self.quit_evt.clear()
            self.quit_evt.wait()
        except KeyboardInterrupt:
            # just want to kill the process, so just continue from here
            pass


    def close(self):
        # TODO: shut down server but also reset module level variables
        pass


    def add_sound(self, sound):
        # break into chunks
        sound = sound.astype(np.float32)
        sound_list = [sound[i:i+self.blocksize] for i in range(0, sound.shape[0], self.blocksize)]
        if sound_list[-1].shape[0] < self.blocksize:
            sound_list[-1] = np.pad(sound_list[-1],
                                    (0, self.blocksize-sound_list[-1].shape[0]),
                                    'constant')
        self.sounds.append(sound_list)

    def quit(self):
        self.quit_evt.set()



    def buffer(self, sound_num):
        sound = self.sounds[sound_num]
        for frame in sound:
            self.q.put_nowait(frame)
        self.q.put_nowait(None)
        # put all the frames into the queue

    def process(self, frames):
        if not self.play_evt.is_set():
            for channel, port in zip(self.zero_arr.T, self.client.outports):
                port.get_array()[:] = channel
        else:

            try:
                data = self.q.get_nowait()
            except queue.Empty:
                data = None
                Warning('Queue Empty')
            if data is None:
                self.play_evt.clear()
            else:
                for channel, port in zip(cycle(data.T), self.client.outports):
                    port.get_array()[:] = channel




if __name__ == "__main__":
    cmd = mp.Queue()

    client = JackClient(cmd)

    duration = 1.0
    freq = 400
    sin_1 = (np.sin(2*np.pi*np.arange(44100.0*duration)*freq/44100.0)).astype(np.float32)
    sin_1 = sin_1*0.2
    sin_1 = np.column_stack((sin_1, sin_1))


    freq = 800
    sin_2 = (np.sin(2*np.pi*np.arange(44100.0*duration)*freq/44100.0)).astype(np.float32)
    sin_2 = sin_2*0.2
    sin_2 = np.column_stack((sin_2, sin_2))

    sin_delay = np.zeros((int(44100*0.1),2),dtype=np.float32)
    sin_delay = np.row_stack((sin_delay, sin_2,))

    client.add_sound(sin_1)
    client.add_sound(sin_2)
    client.add_sound(sin_delay)

    client.start()








