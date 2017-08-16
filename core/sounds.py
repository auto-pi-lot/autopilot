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
from time import sleep
#from taskontrol.settings import rpisettings as rpiset

# Sound list at bottom of file

class Tone:
    '''
    The Humble Sine Wave
    '''
    PARAMS = ['frequency','duration','amplitude']
    def __init__(self, frequency, duration, amplitude=0.3, phase=0, **kwargs):

        sin = pyo.Sine(frequency,mul=amplitude)
        self.table = TableWrap(sin, duration)

    def play(self):
        self.table.out()

class Noise:
    '''
    White Noise straight up
    '''
    PARAMS = ['duration','amplitude']
    def __init__(self, duration, amplitude, **kwargs):
        noiser = pyo.Noise(mul=amplitude)
        self.table = TableWrap(noiser,duration)

    def play(self):
        self.table.out()

class File:
    PARAMS = ['file', 'duration']

    def __init__(self):
        pass

    def play(self):
        pass

def TableWrap(audio,duration):
    '''
    Records a PyoAudio generator into a sound table, returns a tableread object which can play the audio with .out()
    '''
    # Duration is in ms, so divide by 1000
    audio.play()
    tab = pyo.NewTable(length=(float(duration)/1000),chnls=rpiset.NUM_CHANNELS)
    tabrec = pyo.TableRec(audio,table=tab,fadetime=0.01)
    tabrec.play()
    sleep((float(duration)/1000))
    tabread = pyo.TableRead(tab,loop=0)
    return tabread

# Has to be at bottom so fnxns already defined when assigned.
SOUND_LIST = {
    'Tone':Tone,
    'Noise':Noise,
    'File':File
}