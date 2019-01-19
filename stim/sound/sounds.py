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
from time import sleep
from scipy.io import wavfile
from scipy.signal import resample
import numpy as np
import threading

import prefs

# switch behavior based on audio server type
#try:
server_type = prefs.AUDIOSERVER
#except:
#    # TODO: The 'attribute don't exist' type - i think NameError?
#    server_type = None



if prefs.AUDIOSERVER == "pyo":
    import pyo

    class Pyo_Sound(object):
        """

        """
        # Metaclass for pyo sound objects
        PARAMS    = None # list of strings of parameters to be defined
        type      = None # string human readable name of sound
        duration  = None # duration in ms
        amplitude = None
        table     = None
        trigger   = None
        server_type = 'pyo'

        def __init__(self):
            pass


        def play(self):
            """

            """
            self.table.out()

        def table_wrap(self, audio, duration=None):
            '''
            Records a PyoAudio generator into a sound table, returns a tableread object which can play the audio with .out()
            '''

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

            :param trig_fn:
            """
            # Using table triggers, call trig_fn when table finishes playing
            self.trigger = pyo.TrigFunc(self.table['trig'], trig_fn)


elif prefs.AUDIOSERVER == "jack":
    import jackclient

    class Jack_Sound(object):
        # base class for jack audio sounds
        PARAMS = None  # list of strings of parameters to be defined
        type = None  # string human readable name of sound
        duration = None  # duration in ms
        amplitude = None
        table = None  # numpy array of samples
        chunks = None  # table split into a list of chunks
        trigger = None
        nsamples = None
        server_type = 'jack'


        def __init__(self):

            self.fs = jackclient.FS
            self.blocksize = jackclient.BLOCKSIZE
            self.server = jackclient.SERVER
            self.q = jackclient.QUEUE
            self.q_lock = jackclient.Q_LOCK
            self.play_evt = jackclient.PLAY
            self.stop_evt = jackclient.STOP

            self.buffered = False

        def chunk(self):
            # break sound into chunks

            sound = self.table.astype(np.float32)
            sound_list = [sound[i:i+self.blocksize] for i in range(0, sound.shape[0], self.blocksize)]
            if sound_list[-1].shape[0] < self.blocksize:
                sound_list[-1] = np.pad(sound_list[-1],
                                        (0, self.blocksize-sound_list[-1].shape[0]),
                                        'constant')
            self.chunks = sound_list

        def set_trigger(self, trig_fn):
            if callable(trig_fn):
                self.trigger = trig_fn
            else:
                Exception('trigger must be callable')

        def wait_trigger(self):
            # wait for our duration plus a second at most.
            self.stop_evt.wait((self.duration+1000)/1000.)
            # if the sound actually stopped...
            if self.stop_evt.is_set():
                self.trigger()



        def get_nsamples(self):
            # given our fs and duration, how many samples do we need?
            self.nsamples = np.ceil((self.duration/1000.)*self.fs).astype(np.int)

        def buffer(self):
            if not self.chunks:
                self.chunk()

            with self.q_lock:
                for frame in self.chunks:
                    self.q.put_nowait(frame)
                # The jack server looks for a None object to clear the play flag
                self.q.put_nowait(None)
                self.buffered = True

        def play(self):
            if not self.buffered:
                self.buffer()

            self.play_evt.set()
            self.stop_evt.clear()
            self.buffered = False

            if callable(self.trigger):
                threading.Thread(target=self.wait_trigger).start()


else:
    # just importing to query parameters, not play sounds.
    pass


print(prefs.AUDIOSERVER)
import sys
sys.stdout.flush()


####################
if prefs.AUDIOSERVER == "pyo":
    BASE_CLASS = Pyo_Sound
elif prefs.AUDIOSERVER == "jack":
    BASE_CLASS = Jack_Sound
else:
    # just importing to query parameters, not play sounds.
    BASE_CLASS = object


class Tone(BASE_CLASS):
    '''
    The Humble Sine Wave
    '''
    PARAMS = ['frequency','duration','amplitude']
    type = 'Tone'

    def __init__(self, frequency, duration, amplitude=0.01, phase=0, **kwargs):
        super(Tone, self).__init__()

        self.frequency = float(frequency)
        self.duration = float(duration)
        self.amplitude = float(amplitude)

        self.init_sound()

    def init_sound(self):
        if self.server_type == 'pyo':
            sin = pyo.Sine(self.frequency, mul=self.amplitude)
            self.table = self.table_wrap(sin)
        elif self.server_type == 'jack':
            self.get_nsamples()
            t = np.arange(self.nsamples)
            self.table = (self.amplitude*np.sin(2*np.pi*self.frequency*t/self.fs)).astype(np.float32)
            #self.table = np.column_stack((self.table, self.table))
            self.chunk()

class Noise(BASE_CLASS):
    '''
    White Noise straight up
    '''
    PARAMS = ['duration','amplitude']
    type='Noise'
    def __init__(self, duration, amplitude=0.01, **kwargs):
        super(Noise, self).__init__()

        self.duration = float(duration)
        self.amplitude = float(amplitude)

        self.init_sound()

    def init_sound(self):
        """

        """
        if self.server_type == 'pyo':
            noiser = pyo.Noise(mul=self.amplitude)
            self.table = self.table_wrap(noiser)
        elif self.server_type == 'jack':
            self.get_nsamples()
            self.table = self.amplitude * np.random.rand(self.nsamples)
            self.chunk()

class File(BASE_CLASS):
    """

    """
    PARAMS = ['path', 'amplitude']
    type='File'

    def __init__(self, path, amplitude=0.01, **kwargs):
        super(File, self).__init__()

        if os.path.exists(path):
            self.path = path
        elif os.path.exists(os.path.join(prefs.SOUNDDIR, path)):
            self.path = os.path.join(prefs.SOUNDDIR, path)
        else:
            Exception('Could not find {} in current directory or sound directory'.format(path))

        self.amplitude = float(amplitude)

        self.init_sound()

    def init_sound(self):
        """

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
            self.duration = float(audio.shape[0]) / fs
            # resample to match our audio server's sampling rate
            if fs != self.fs:
                new_samples = self.duration*self.fs
                audio = resample(audio, new_samples)

            self.table = audio


class Speech(File):
    """

    """
    type='Speech'
    PARAMS = ['path', 'amplitude', 'speaker', 'consonant', 'vowel', 'token']
    def __init__(self, path, speaker, consonant, vowel, token, amplitude=0.05, **kwargs):
        super(Speech, self).__init__(path, amplitude, **kwargs)

        self.speaker = speaker
        self.consonant = consonant
        self.vowel = vowel
        self.token = token

        # sound is init'd in the superclass







#######################
# Has to be at bottom so fnxns already defined when assigned.
SOUND_LIST = {
    'Tone':Tone,
    'Noise':Noise,
    'File':File,
    'Speech':Speech,
    'speech':Speech
}

# These parameters are strings not numbers... jonny should do this better
STRING_PARAMS = ['path', 'speaker', 'consonant', 'vowel', 'type']


def int_to_float(audio):
    """

    :param audio:
    :return:
    """
    if audio.dtype == 'int16':
        audio = audio.astype(np.float32)
        audio = audio / (float(2 ** 16) / 2)
    elif audio.dtype == 'int32':
        audio = audio.astype(np.float32)
        audio = audio / (float(2 ** 32) / 2)

    return audio












