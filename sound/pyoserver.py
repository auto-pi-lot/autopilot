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
import sys
from time import sleep
import json
from scipy.io import wavfile
import numpy as np

import prefs

import pyo

def pyo_server(debug=False):
    # Jackd should already be running from the launch script created by setup_pilot, we we just
    pyo_server = pyo.Server(audio='jack', nchnls=int(prefs.NCHANNELS),
                            duplex=0, buffersize=4096, sr=192000, ichnls=0)

    # Deactivate MIDI because we don't use it and it's expensive
    pyo_server.deactivateMidi()

    # We have to set pyo to not automatically try to connect to inputs when there aren't any
    pyo_server.setJackAuto(False, True)

    # debug
    if debug:
        pyo_server.setVerbosity(8)

    # Then boot and start
    pyo_server.boot()
    pyo_server.start()

    return pyo_server