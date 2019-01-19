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
    """

    :param debug:
    :return:
    """
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
