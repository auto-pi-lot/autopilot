"""
Go/no-go task, demo for NCB
"""



import datetime
import itertools
import tables
import threading

from rpilot.core import hardware
from rpilot.tasks import Task
from rpilot.stim.visual.visuals import Grating_Continuous
from collections import OrderedDict as odict
from rpilot.core.networking import Net_Node

from rpilot import prefs

# This declaration allows Mouse to identify which class in this file contains the task class. Could also be done with __init__ but yno I didnt for no reason.
# TODO: Move this to __init__
TASK = 'Nafc'

class GoNoGo(Task):
    STAGE_NAMES = ["request", "discrim", "reinforcement"]

    # Class attributes

    # List of needed params, returned data and data format.
    # Params are [name]={'tag': Human Readable Tag, 'type': 'int', 'float', 'check', etc.}
    PARAMS = odict()
    PARAMS['reward'] = {'tag': 'Reward Duration (ms)',
                        'type': 'int'}
    PARAMS['timeout']        = {'tag':'Delay Timeout (ms)',
                                'type':'int'}
    PARAMS['stim'] = {'tag':  'Visuals',
                      'type': 'visuals'}

    # Set plot params, which data should be plotted, its default shape, etc.
    PLOT = {
        'data': {
            'x': 'shaded',
            'target': 'point',
            'response': 'segment'
        },
        'continuous': True
    }

    # PyTables Data descriptor
    # for numpy data types see http://docs.scipy.org/doc/numpy/reference/arrays.dtypes.html#arrays-dtypes-constructing
    class TrialData(tables.IsDescription):
        # This class allows the Mouse object to make a data table with the correct data types. You must update it for any new data you'd like to store
        trial_num = tables.Int32Col()
        target = tables.StringCol(1)
        response = tables.StringCol(1)
        correct  = tables.Int32Col()
        RQ_timestamp = tables.StringCol(26)
        DC_timestamp = tables.StringCol(26)

    HARDWARE = {
        'POKES': {
            'C': hardware.Beambreak,
        },
        'LEDS': {
            'C': hardware.LED_RGB,
        },
        'PORTS': {
            'C': hardware.Solenoid,
        }
    }

    CHILDREN = {
        'WHEEL': {
            'task_type': "Wheel Child",
        }
    }

    def __init__(self, stim=None, reward = 50, timeout = 1000,):
        super(GoNoGo, self).__init__()

        self.reward = reward
        self.timeout = timeout

        # hardcoding stimulus for testing
        self.stim = Grating_Continuous(angle=0, freq=(4,0), rate=1)

        self.stages = itertools.cycle([self.request, self.discrim, self.reinforce])


    def request(self):
        # wait for the mouse to hold the wheel still
        pass

    def discrim(self):
        pass

    def reinforcement(self):
        pass
