# Base class for tasks

#!/usr/bin/python2.7
from collections import OrderedDict as odict
import threading
import logging
import tables
# from autopilot.core.networking import Net_Node
from autopilot.hardware import BCM_TO_BOARD
from autopilot import prefs

if hasattr(prefs, "AUDIOSERVER"):
    if prefs.AUDIOSERVER == 'pyo':
        pass
    elif prefs.AUDIOSERVER == 'jack':
        pass


class Task(object):
    """
    Generic Task metaclass

    Attributes:
        PARAMS (:class:`collections.OrderedDict`): Params to define task, like::

            PARAMS = odict()
            PARAMS['reward']         = {'tag':'Reward Duration (ms)',
                                        'type':'int'}
            PARAMS['req_reward']     = {'tag':'Request Rewards',
                                        'type':'bool'}

        HARDWARE (dict): dict for necessary hardware, like::

            HARDWARE = {
                'POKES':{
                    'L': hardware.Beambreak, ...
                },
                'PORTS':{
                    'L': hardware.Solenoid, ...
                }
            }

        PLOT (dict): Dict of plotting parameters, like::

                PLOT = {
                    'data': {
                        'target'   : 'point',
                        'response' : 'segment',
                        'correct'  : 'rollmean'
                    },
                    'chance_bar'  : True, # Draw a red bar at 50%
                    'roll_window' : 50 # number of trials to roll window over
                }

        Trial_Data (:class:`tables.IsDescription`): Data table description, like::

            class TrialData(tables.IsDescription):
                trial_num = tables.Int32Col()
                target = tables.StringCol(1)
                response = tables.StringCol(1)
                correct = tables.Int32Col()
                correction = tables.Int32Col()
                RQ_timestamp = tables.StringCol(26)
                DC_timestamp = tables.StringCol(26)
                bailed = tables.Int32Col()

        STAGE_NAMES (list): List of stage method names
        stage_block (:class:`threading.Event`): Signal when task stages complete.
        punish_stim (bool): Do a punishment stimulus
        stages (iterator): Some generator or iterator that continuously returns the next stage method of a trial
        triggers (dict): Some mapping of some pin to callback methods
        pins (dict): Dict to store references to hardware
        pin_id (dict): Reverse dictionary, pin numbers back to pin letters.
        punish_block (:class:`threading.Event`): Event to mark when punishment is occuring
        logger (:class:`logging.Logger`): gets the 'main' logger for now.



    """
    # dictionary of Params needed to define task,
    # these should correspond to argument names for the task
    PARAMS = odict()

    # Task Definition
    HARDWARE = {} # Hardware needed to run the task
    STAGE_NAMES = [] # list of names of stage methods
    PLOT = {} # dictionary of plotting params
    class TrialData(tables.IsDescription):
        trial_num = tables.Int32Col()
        session = tables.Int32Col()



    def __init__(self, *args, **kwargs):

        # Task management
        self.stage_block = None  # a threading.Event used by the pilot to manage stage transitions
        self.punish_stim = False
        #self.running = None  # Event used to exit the run thread
        self.stages = None  # Some generator that continuously returns the next stage of the trial
        self.triggers = {}
        self.stim_manager = None

        self.trial_counter = None  # will be init'd by the subtask because will use the current trial

        # Hardware
        self.hardware = {}  # dict to store references to hardware
        self.pin_id = {}  # pin numbers back to pin lettering

        self.punish_block = threading.Event()
        self.punish_block.set()
        #self.running = threading.Event()

        # try to get logger
        self.logger = logging.getLogger('main')




    def init_hardware(self):
        """
        Use the HARDWARE dict that specifies what we need to run the task
        alongside the HARDWARE subdict in :mod:`prefs` to tell us how
        they're plugged in to the pi

        Instantiate the hardware, assign it :meth:`.Task.handle_trigger`
        as a callback if it is a trigger.
        """
        # We use the HARDWARE dict that specifies what we need to run the task
        # alongside the HARDWARE subdict in the prefs structure to tell us how they're plugged in to the pi
        self.hardware = {}
        self.pin_id = {} # Reverse dict to identify pokes
        pin_numbers = prefs.HARDWARE

        # We first iterate through the types of hardware we need
        for type, values in self.HARDWARE.items():
            self.hardware[type] = {}
            # then iterate through each pin and handler of this type
            for pin, handler in values.items():
                try:
                    hw_args = pin_numbers[type][pin]
                    if isinstance(hw_args, dict):
                        if 'name' not in hw_args.keys():
                            hw_args['name'] = "{}_{}".format(type, pin)
                        hw = handler(**hw_args)
                    else:
                        hw_name = "{}_{}".format(type, pin)
                        hw = handler(hw_args, name=hw_name)

                    # if a pin is a trigger pin (event-based input), give it the trigger handler
                    if hw.trigger:
                        hw.assign_cb(self.handle_trigger)

                    # add to forward and backwards pin dicts
                    self.hardware[type][pin] = hw
                    if isinstance(hw_args, int) or isinstance(hw_args, str):
                        self.pin_id[hw_args] = pin
                    elif isinstance(hw_args, list):
                        for p in hw_args:
                            self.pin_id[p] = pin
                    elif isinstance(hw_args, dict):
                        if 'pin' in hw_args.keys():
                            self.pin_id[hw_args['pin']] = pin 

                except:
                    self.logger.exception("Pin could not be instantiated - Type: {}, Pin: {}".format(type, pin))


    def set_reward(self, vol=None, duration=None, port=None):
        """
        Set the reward value for each of the 'PORTS'.

        Args:
            vol(float, int): Volume of reward in uL
            duration (float): Duration to open port in ms
            port (None, Port_ID): If `None`, set everything in 'PORTS', otherwise
                only set `port`
        """
        if not vol and not duration:
            Exception("Need to have duration or volume!!")
        if vol and duration:
            Warning('given both volume and duration, using volume.')

        if not port:
            for k, port in self.hardware['PORTS'].items():
                if vol:
                    try:
                        port.dur_from_vol(vol)
                    except AttributeError:
                        Warning('No calibration found, using duration = 20ms instead')
                        port.duration = 0.02
                else:
                    port.duration = float(duration)/1000.
        else:
            try:
                if vol:
                    try:
                        self.hardware['PORTS'][port].dur_from_vol(vol)
                    except AttributeError:
                        Warning('No calibration found, using duration = 20ms instead')
                        port.duration = 0.02

                else:
                    self.hardware['PORTS'][port].duration = float(duration) / 1000.
            except KeyError:
                Exception('No port found named {}'.format(port))

    # def init_sound(self):
    #     pass

    def handle_trigger(self, pin, level=None, tick=None):
        """
        All GPIO triggers call this function with the pin number, level (high, low),
        and ticks since booting pigpio.

        Calls any trigger assigned to the pin in `self.triggers` ,
        unless during punishment (returns).

        Args:
            pin (int): BCM Pin number
            level (bool): True, False high/low
            tick (int): ticks since booting pigpio
        """
        # All triggers call this function with the pin number, level (high, low), and ticks since booting pigpio

        # We get fed hardware as BCM numbers, convert to board number and then back to letters
        if isinstance(pin, int):
            pin = BCM_TO_BOARD[pin]
            pin = self.pin_id[pin]

        if pin not in self.triggers.keys():
            self.logger.debug(f"No trigger found for {pin}")
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


    def set_leds(self, color_dict=None):
        """
        Set the color of all LEDs at once.

        Args:
            color_dict (dict): If None, turn LEDs off, otherwise like:

                {'pin': [R,G,B],
                'pin2: [R,G,B]}


        """
        # We are passed a dict of ['pin']:[R, G, B] to set multiple colors
        # All others are turned off
        if not color_dict:
            color_dict = {}
        for k, v in self.hardware['LEDS'].items():
            if k in color_dict.keys():
                v.set(color_dict[k])
            else:
                v.set([0,0,0])

    def flash_leds(self):
        """
        flash lights for punish_dir
        """
        for k, v in self.hardware['LEDS'].items():
            v.flash(self.punish_dur)

    def end(self):
        """
        Release all hardware objects
        """
        for k, v in self.hardware.items():
            for pin, obj in v.items():
                obj.release()

        if hasattr(self, 'stim_manager'):
            if self.stim_manager is not None:
                self.stim_manager.end()









