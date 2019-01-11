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
import logging
from core.networking import Net_Node

import prefs
if hasattr(prefs, "AUDIOSERVER"):
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
    running = None # Event used to exit the run thread

    trial_counter = None # will be init'd by the subtask because will use the current trial

    pins = {} # dict to store references to hardware
    pin_id = {} # pin numbers back to pin lettering

    logger = None



    def __init__(self):
        self.punish_block = threading.Event()
        self.punish_block.set()
        self.running = threading.Event()

        self.prefs = prefs

        # try to get logger
        self.logger = logging.getLogger('main')




    def init_hardware(self):
        # We use the HARDWARE dict that specifies what we need to run the task
        # alongside the PINS subdict in the prefs structure to tell us how they're plugged in to the pi
        self.pins = {}
        self.pin_id = {} # Reverse dict to identify pokes
        pin_numbers = self.prefs['PINS']

        # We first iterate through the types of hardware we need
        for type, values in self.HARDWARE.items():
            self.pins[type] = {}
            # then iterate through each pin and handler of this type
            for pin, handler in values.items():
                try:
                    hw = handler(pins=pin_numbers[type][pin])

                    # if a pin is a trigger pin (event-based input), give it the trigger handler
                    if hw.trigger:
                        hw.assign_cb(self.handle_trigger)

                    # add to forward and backwards pin dicts
                    self.pins[type][pin] = hw
                    self.pin_id[pin_numbers[type][pin]] = pin
                except:
                    self.logger.exception("Pin could not be instantiated - Type: {}, Pin: {}".format(type, pin))


    def set_reward(self, duration):
        for k, port in self.pins['PORTS'].items():
            port.duration = float(duration)/1000.

    def init_sound(self):
        pass

    def handle_trigger(self):
        pass








