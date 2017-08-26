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
#from taskontrol.settings import rpisettings as rpiset

# Sound list at bottom of file

class Tone:
    '''
    The Humble Sine Wave
    '''
    PARAMS = ['frequency','duration','amplitude']
    def __init__(self, frequency, duration, amplitude=0.3, phase=0, **kwargs):

        sin = pyo.Sine(float(frequency),mul=float(amplitude))
        self.table = TableWrap(sin, float(duration))

    def play(self):
        print('play method called')
        sys.stdout.flush()
        self.table.out()

    def set_trigger(self, trig_fn):
        # TODO: Put this in metaclass
        # Using table triggers...
        self.trigger = pyo.TrigFunc(self.table['trig'], trig_fn)

class Noise:
    '''
    White Noise straight up
    '''
    PARAMS = ['duration','amplitude']
    def __init__(self, duration, amplitude=0.3, **kwargs):
        noiser = pyo.Noise(mul=float(amplitude))
        self.table = TableWrap(noiser,float(duration))

    def play(self):
        self.table.out()

    def set_trigger(self, trig_fn):
        # Using table triggers...
        self.trigger = pyo.TrigFunc(self.table['trig'], trig_fn)

class File:
    PARAMS = ['file', 'duration']

    def __init__(self):
        pass

    def play(self):
        # test
        pass

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
    'File':File
}