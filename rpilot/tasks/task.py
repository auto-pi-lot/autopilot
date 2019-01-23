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
# from rpilot.core.networking import Net_Node
from rpilot.core import hardware
from rpilot import prefs

if hasattr(prefs, "AUDIOSERVER"):
    if prefs.AUDIOSERVER == 'pyo':
        pass
    elif prefs.AUDIOSERVER == 'jack':
        pass


class Task(object):
    # dictionary of Params needed to define task,
    # these should correspond to argument names for the task
    PARAMS = odict()

    # Task Definition
    HARDWARE = {} # Hardware needed to run the task
    STAGE_NAMES = [] # list of names of stage methods
    PLOT = {} # dictionary of plotting params
    TrialData = None # tables.IsDescription class to make data table

    # Task management
    stage_block = None # a threading.Event used by the pilot to manage stage transitions
    punish_block = None # holds the next stage while punishment is happening
    punish_stim = False
    running = None # Event used to exit the run thread
    stages = None # Some generator that continuously returns the next stage of the trial
    triggers = {}
    stim_manager = None

    trial_counter = None # will be init'd by the subtask because will use the current trial

    # Hardware
    pins = {} # dict to store references to hardware
    pin_id = {} # pin numbers back to pin lettering

    logger = None



    def __init__(self):
        self.punish_block = threading.Event()
        self.punish_block.set()
        self.running = threading.Event()

        # try to get logger
        self.logger = logging.getLogger('main')




    def init_hardware(self):
        # We use the HARDWARE dict that specifies what we need to run the task
        # alongside the PINS subdict in the prefs structure to tell us how they're plugged in to the pi
        self.pins = {}
        self.pin_id = {} # Reverse dict to identify pokes
        pin_numbers = prefs.PINS

        # We first iterate through the types of hardware we need
        for type, values in self.HARDWARE.items():
            self.pins[type] = {}
            # then iterate through each pin and handler of this type
            for pin, handler in values.items():
                try:
                    hw = handler(pin_numbers[type][pin])

                    # if a pin is a trigger pin (event-based input), give it the trigger handler
                    if hw.trigger:
                        hw.assign_cb(self.handle_trigger)

                    # add to forward and backwards pin dicts
                    self.pins[type][pin] = hw
                    back_pins = pin_numbers[type][pin]
                    if isinstance(back_pins, int) or isinstance(back_pins, basestring):
                        self.pin_id[back_pins] = pin
                    elif isinstance(back_pins, list):
                        for p in back_pins:
                            self.pin_id[p] = pin

                except:
                    self.logger.exception("Pin could not be instantiated - Type: {}, Pin: {}".format(type, pin))


    def set_reward(self, duration, port=None):
        """
        Args:
            duration:
            port:
        """
        if not port:
            for k, port in self.pins['PORTS'].items():
                port.duration = float(duration)/1000.
        else:
            try:
                self.pins['PORTS'][port].duration = float(duration)/1000.
            except KeyError:
                Exception('No port found named {}'.format(port))

    def init_sound(self):
        pass

    def handle_trigger(self, pin, level, tick):
        """
        Args:
            pin:
            level:
            tick:
        """
        # All triggers call this function with the pin number, level (high, low), and ticks since booting pigpio
        # Triggers will be functions unless they are "TIMEUP", at which point we
        # register a timeout and restart the trial

        # We get fed pins as numbers usually, convert to board number and then back to letters
        if isinstance(pin, int):
            pin = hardware.BCM_TO_BOARD[pin]
            pin = self.pin_id[pin]

        if pin not in self.triggers.keys():
            # No trigger assigned, get out without waiting
            return

        if pin == 'TIMEUP':
            # TODO: Handle timers, reset trial
            # TODO: Handle bailing, for example by replacing the cycle with a single function that returns the 'bail' flag
            return

        # if we're being punished, don't recognize the trigger
        if not self.punish_block.is_set():
            return

        # Call the trigger
        try:
            self.triggers[pin]()
        except TypeError:
            # Multiple triggers, call them all
            for trig in self.triggers[pin]:
                trig()
        except KeyError:
            # If we don't have a trigger, that's fine, eg. L and R before requesting
            return

        # clear triggers
        self.triggers = {}

        # Set the stage block so the pilot calls the next stage
        self.stage_block.set()

    def punish(self):
        # TODO: If we're not in the last stage (eg. we were timed out after stim presentation), reset stages
        self.punish_block.clear()

        if self.punish_stim:
            self.stim_manager.play_punishment()

        # self.set_leds()
        self.flash_leds()
        threading.Timer(self.punish_dur / 1000., self.punish_block.set).start()

    def set_leds(self, color_dict=None):
        """
        Args:
            color_dict:
        """
        # We are passed a dict of ['pin']:[R, G, B] to set multiple colors
        # All others are turned off
        if not color_dict:
            color_dict = {}
        for k, v in self.pins['LEDS'].items():
            if k in color_dict.keys():
                v.set_color(color_dict[k])
            else:
                v.set_color([0,0,0])

    def end(self):
        for k, v in self.pins.items():
            for pin, obj in v.items():
                obj.release()









