from __future__ import division
from __future__ import print_function

import multiprocessing as mp
import jack
import Queue as queue
import numpy as np
from threading import Thread

class JackClient(mp.Process):
    def __init__(self, pipe, name='jack_client'):
        super(JackClient, self).__init__()

        self.name = name
        self.pipe = pipe
        self.q = mp.Queue()
        self.sounds = []


        self.play_evt = mp.Event()
        self.quit_evt = mp.Event()

        self.client = jack.Client(self.name)
        self.blocksize = self.client.blocksize
        self.fs = self.client.samplerate
        self.zero_arr = np.zeros((self.blocksize,1),dtype='float32')

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
        self.client.outports[0].connect(target_ports[1])

    def run(self):
        buffered = False
        sound_num = 0
        self.boot_server()

        while not self.quit_evt.is_set():
        # try:
            command = self.pipe.get()
            # except queue.Empty:
            #     continue
            print(command)

            if command.startswith('BUFFER'):
                sound_num = int(command.split('_')[1])
                self.buffer(sound_num)
                buffered = True
            elif command == 'PLAY':
                if buffered == False:
                    self.buffer(sound_num)
                self.play_evt.set()
                buffered = False


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
                for channel, port in zip(data.T, self.client.outports):
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








