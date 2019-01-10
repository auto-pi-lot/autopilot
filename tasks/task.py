# Base class for tasks

#!/usr/bin/python2.7

'''
Template handler set for a 2afc paradigm.
Want a bundled set of functions so the RPilot can make the task from relatively few params.
Also want it to contain details about how you should draw 2afcs in general in the terminal
Remember: have to put class name in __init__ file to import directly.
Stage functions should each return three dicts: data, triggers, and timers
    -data: (field:value) all the relevant data for the stage, as named in the DATA_LIST
    -triggers: (input:action) what to do if the relevant input is triggered
    -timers: (type:{params}) like {'too_early':{'sound':too_early_sound}}
'''
from collections import OrderedDict as odict
import threading

import prefs
if prefs.AUDIOSERVER == 'pyo':
    pass
elif prefs.AUDIOSERVER == 'jack':
    pass


class Task(object):
    # dictionary of Params needed to define task,
    # these should correspond to argument names for the task
    PARAMS = odict()

    HARDWARE = {} # Hardware needed to run the task
    STAGE_NAMES = [] # list of names of stage methods
    PLOT = {} # dictionary of plotting params
    TrialData = None # tables.IsDescription class to make data table

    stage_block = None # a threading.Event used by the pilot to manage stage transitions
    punish_block = None # holds the next stage while punishment is happening

    trial_counter = None # will be init'd by the subtask because will use the current trial

    pins = {} # dict to store references to hardware
    pin_id = {} # pin numbers back to pin lettering

    def __init__(self):
        self.punish_block = threading.Event()
        self.punish_block.set()

    def init_hardware(self):
        pass

    def init_sound(self):
        pass








