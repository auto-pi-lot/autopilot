#!/usr/bin/python2.7

'''
classes to build sounds from parameters
use the SOUND_SWITCH to allow listing of sound types in the GUI & flexible coding from other modules
then you can call sounds like sounds.SWITCH['tone'](freq=1000, etc.)

Each function should return a pyo soundTable object that can be played with its .out() method.
Notes on creating functions:
    -You must include **kwargs in the methods statement or otherwise handle the 'type' key fed to the function
'''

import pyo
from time import sleep
from taskontrol.settings import rpisettings as rpiset



def Tone(frequency,duration,amplitude=0.3,phase=0,**kwargs):
    '''
    The Humble Sine Wave
    '''
    sin = pyo.Sine(frequency,mul=amplitude)
    tableout = TableWrap(sin,duration)
    return tableout

def Noise(duration,amplitude,**kwargs):
    '''
    White Noise straight up
    '''
    noiser = pyo.Noise(mul=amplitude)
    tableout = TableWrap(noiser,duration)
    return tableout


def Wav_file(path,duration):
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
SWITCH = {
    'tone':Tone,
    'noise':Noise
}