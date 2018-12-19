#!/usr/bin/python2.7

'''
classes to build sounds from parameters
use the SOUND_SWITCH to allow listing of sound types in the GUI & flexible coding from other modules
then you can call sounds like sounds.SWITCH['tone'](freq=1000, etc.)

Each function should return a pyo soundTable object that can be played with its .out() method.
Notes on creating functions:
    -You must include **kwargs in the methods statement or otherwise handle the 'type' key fed to the function
'''

# TODO: make it so terminal doesn't have to import pyo just to access sound info
import pyo
import sys
from time import sleep
import json
from scipy.io import wavfile
import numpy as np
import tables
#from taskontrol.settings import rpisettings as rpiset

# Sound list at bottom of file
class Sound(object):
    # Metaclass for sound objects

    # All sounds should be cast to tables with an .out() method (eg. TableRead, Osc)
    table = None

    trigger = None

    def __init__(self):
        pass

    def play(self):
        self.table.out()

    def table_wrap(self, audio, duration):
        '''
        Records a PyoAudio generator into a sound table, returns a tableread object which can play the audio with .out()
        '''
        # Duration is in ms, so divide by 1000
        # See https://groups.google.com/forum/#!topic/pyo-discuss/N-pan7wPF-o
        # TODO: Get chnls to be responsive to NCHANNELS in prefs. hardcoded for now
        tab = pyo.NewTable(length=(float(duration) / 1000),
                           chnls=1)  # Prefs should always be declared in the global namespace
        tabrec = pyo.TableRec(audio, table=tab, fadetime=0.01).play()
        sleep((float(duration) / 1000))
        tabread = pyo.TableRead(tab, freq=tab.getRate(), loop=0)
        return tabread

    def set_trigger(self, trig_fn):
        # Using table triggers, call trig_fn when table finishes playing
        self.trigger = pyo.TrigFunc(self.table['trig'], trig_fn)




class Tone:
    '''
    The Humble Sine Wave
    '''
    PARAMS = ['frequency','duration','amplitude']
    type = 'Tone'
    def __init__(self, frequency, duration, amplitude=0.01, phase=0, **kwargs):
        # super(Tone, self).__init__()

        self.frequency = float(frequency)
        self.duration = float(duration)
        self.amplitude = float(amplitude)


        sin = pyo.Sine(self.frequency, mul=self.amplitude)
        self.table = TableWrap(sin, self.duration)




    def set_trigger(self, trig_fn):
        # TODO: Put this in metaclass
        # Using table triggers...
        self.trigger = pyo.TrigFunc(self.table['trig'], trig_fn)

    def play(self):
        self.table.out()


class Noise:
    '''
    White Noise straight up
    '''
    PARAMS = ['duration','amplitude']
    type='Noise'
    def __init__(self, duration, amplitude=0.01, **kwargs):
        #super(Noise, self).__init__()

        self.duration = float(duration)
        self.amplitude = float(amplitude)

        noiser = pyo.Noise(mul=float(amplitude))
        self.table = TableWrap(noiser,float(duration))

    def play(self):
        self.table.out()

    def set_trigger(self, trig_fn):
        # Using table triggers...
        self.trigger = pyo.TrigFunc(self.table['trig'], trig_fn)

class Gap:
    PARAMS = ['duration', 'amplitude']
    type='Gap'
    def __init__(self, duration, amplitude=0.01, out_chan=1, **kwargs):
        # gap in noise
        self.duration = float(duration)/1000
        self.amplitude = float(amplitude)
        self.fad = pyo.Fader(fadein=0.0001, fadeout=0.0001,
                             dur=self.duration, mul=1.0)
        self.out_chan = out_chan

        # fader is 0 when not playing, then goes to its mul when played.
        # so we multiply the amplitude of the noise generator by 1-fad
        self.noiser = pyo.Noise(mul=float(amplitude)*(1.0-self.fad))

        # start it
        self.noiser.out(self.out_chan)



    def play(self):
        self.fad.play()

    def apply_faders(self):
        pass

    def set_trigger(self, trig_fn):
        # Using table triggers...
        self.trigger = pyo.TrigFunc(self.fad['trig'], trig_fn)

    def stop(self):
        self.noiser.stop()

class File(object):
    PARAMS = ['path', 'amplitude']
    type='File'

    def __init__(self, path, amplitude=0.01, **kwargs):
        #super(File, self).__init__()

        self.path = path
        self.amplitude = float(amplitude)

        self.load_file()

    def load_file(self):
        # load file to sound table
        print(self.path)
        sys.stdout.flush()
        self.snd_table = pyo.SndTable(self.path, chnl=2)
        self.table = pyo.TableRead(self.snd_table, freq=self.snd_table.getRate(),
                                   loop=False, mul=self.amplitude)

    def set_trigger(self, trig_fn):
        # Using table triggers...
        self.trigger = pyo.TrigFunc(self.table['trig'], trig_fn)



    def play(self):
        self.table.out()

class Speech:
    type='Speech'
    PARAMS = ['path', 'amplitude', 'speaker', 'consonant', 'vowel', 'token']
    def __init__(self, path, speaker, consonant, vowel, token, amplitude=0.05, **kwargs):
        self.path = path
        self.amplitude = float(amplitude)

        self.speaker = speaker
        self.consonant = consonant
        self.vowel = vowel
        self.token = token

        self.load_file()

    def load_file(self):
        # load file to sound table
        #
        fs, audio = wavfile.read(self.path)
        if audio.dtype in ['int16', 'int32']:
            audio = int_to_float(audio)

        self.dtable = pyo.DataTable(size=audio.shape[0], chnls=2, init=audio.tolist())

        # get server to determine sampling rate modification
        server_fs = self.dtable.getServer().getSamplingRate()

        self.table = pyo.TableRead(table=self.dtable, freq=float(fs)/server_fs,
                                   loop=False, mul=self.amplitude)


    def set_trigger(self, trig_fn):
        # Using table triggers...
        self.trigger = pyo.TrigFunc(self.table['trig'], trig_fn)



    def play(self):
        self.table.reset()
        self.table.out()





def TableWrap(audio,duration):
    '''
    Records a PyoAudio generator into a sound table, returns a tableread object which can play the audio with .out()
    '''
    # Duration is in ms, so divide by 1000
    # See https://groups.google.com/forum/#!topic/pyo-discuss/N-pan7wPF-o
    #TODO: Get chnls to be responsive to NCHANNELS in prefs. hardcoded for now
    #audio.play()
    tab = pyo.NewTable(length=(float(duration)/1000),chnls=2) # Prefs should always be declared in the global namespace
    tabrec = pyo.TableRec(audio,table=tab,fadetime=0.01).play()
    sleep((float(duration)/1000))
    tabread = pyo.TableRead(tab,freq=tab.getRate(), loop=0)
    #audio.stop()
    #tabrec.stop()
    return tabread


# Has to be at bottom so fnxns already defined when assigned.
SOUND_LIST = {
    'Tone':Tone,
    'Noise':Noise,
    'File':File,
    'Speech':Speech,
    'speech':Speech,
    'Gap':Gap
}

STRING_PARAMS = ['path', 'speaker', 'consonant', 'vowel', 'type']

def int_to_float(audio):
    if audio.dtype == 'int16':
        audio = audio.astype(np.float16)
        audio = audio / (float(2 ** 16) / 2)
    elif audio.dtype == 'int32':
        audio = audio.astype(np.float16)
        audio = audio / (float(2 ** 32) / 2)

    return audio
