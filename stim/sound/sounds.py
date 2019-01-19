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
    from pyoserver import Pyo_Sound as BASE_CLASS


elif prefs.AUDIOSERVER == "jack":
    from jackclient import Jack_Sound as BASE_CLASS


else:
    # just importing to query parameters, not play sounds.
    pass


print(prefs.AUDIOSERVER)
import sys
sys.stdout.flush()


####################



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












