from collections import OrderedDict as odict
import tables
import os
import json
import itertools
import random
import datetime
import prefs

from core import hardware

TASK = 'Free_water'

class Free_Water:
    # Randomly light up one of the ports, then dispense water when the mouse pokes
    # TODO: Any reason to have any number of active ports?
    # Two stages - waiting for response, and reporting the response afterwards
    STAGE_NAMES = ["water", "response"]

    # Params
    PARAMS = odict()
    PARAMS['reward'] = {'tag':'Reward Duration (ms)',
                        'type':'int'}
    PARAMS['allow_repeat'] = {'tag':'Allow Repeated Ports?',
                              'type':'check'}

    # Returned Data
    DATA = {
        'trial_num': {'type':'i32'},
        'target': {'type':'S1', 'plot':'target'},
        'timestamp': {'type':'S26'}, # only one timestamp, since next trial instant
    }

    # TODO: This should be generated from DATA above. Perhaps parsimoniously by using tables types rather than string descriptors
    class TrialData(tables.IsDescription):
        trial_num = tables.Int32Col()
        target    = tables.StringCol(1)
        timestamp = tables.StringCol(26)

    HARDWARE = {
        'POKES':{
            'L': hardware.Beambreak,
            'C': hardware.Beambreak,
            'R': hardware.Beambreak
        },
        'LEDS':{
            # TODO: use LEDs, RGB vs. white LED option in init
            'L': hardware.LED_RGB,
            'C': hardware.LED_RGB,
            'R': hardware.LED_RGB
        },
        'PORTS':{
            'L': hardware.Solenoid,
            'C': hardware.Solenoid,
            'R': hardware.Solenoid
        }
    }

    # Plot parameters
    PLOT = {
        'data': {
            'target': 'point'
        }
    }

    def __init__(self, stage_block=None, current_trial=0,
                 reward=50, allow_repeat=False, **kwargs):

        if not stage_block:
            raise Warning('No stage_block Event() was passed, youll need to handle stage progression on your own')
        else:
            self.stage_block = stage_block

        # Fixed parameters
        self.reward = int(reward)
        self.allow_repeat = bool(allow_repeat)

        # Variable parameters
        self.target = random.choice(['L', 'C', 'R'])
        self.current_stage = None
        self.trial_counter = itertools.count(int(current_trial))
        self.triggers = {}
        self.first_trial = True

        # Stage list to iterate
        stage_list = [self.water, self.response]
        self.num_stages = len(stage_list)
        self.stages = itertools.cycle(stage_list)

        # Init hardware
        self.pins = {}
        self.pin_id = {} # Inverse pin dictionary
        self.init_hardware()

    def water(self, *args, **kwargs):
        self.stage_block.clear()

        # If this is the first trial, release water in all three ports
        #if self.first_trial:
        #    self.first_trial = False
        #    self.pins['PORTS']['L'].open()
        #    self.pins['PORTS']['C'].open()
        #    self.pins['PORTS']['R'].open()

        # Choose random port
        if self.allow_repeat:
            self.target = random.choice(['L', 'C', 'R'])
        else:
            other_ports = [t for t in ['L', 'C', 'R'] if t is not self.target]
            self.target = random.choice(other_ports)

        print(self.pins['PORTS'])
        self.triggers[self.target] = self.pins['PORTS'][self.target].open
        self.set_leds({self.target: [0, 255, 0]})

        data = {
            'target': self.target,
            'timestamp': datetime.datetime.now().isoformat(),
            'trial_num' : self.trial_counter.next()
        }
        return data


    def response(self):
        # we just have to tell the Terminal that this trial has ended

        # mebs also turn the light off rl quick
        self.set_leds()

        return {'TRIAL_END':True}

    def handle_trigger(self, pin, level, tick):
        # All triggers call this function with the pin number, level (high, low), and ticks since booting pigpio
        # Triggers will be functions unless they are "TIMEUP", at which point we
        # register a timeout and restart the trial

        # We get fed pins as numbers usually, convert to board number and then back to letters
        if isinstance(pin, int):
            pin = hardware.BCM_TO_BOARD[pin]
            pin = self.pin_id[pin]

        if not pin in self.triggers.keys():
            # No trigger assigned, get out without waiting
            return

        # stash last pin
        self.last_pin = pin

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

    def init_hardware(self):
        # We use the HARDWARE dict that specifies what we need to run the task
        # alongside the PINS subdict in the prefs structure to tell us how they're plugged in to the pi
        self.pins = {}
        self.pin_id = {} # Reverse dict to identify pokes
        pin_numbers = prefs.PINS

        # We first iterate through the types of hardware we need
        for type, values in self.HARDWARE.items():
            self.pins[type] = {}
            # Then switch depending on the type
            # First IR beambreak nosepokes
            if type == 'POKES':
                for pin, handler in values.items():
                    try:
                        self.pin_id[pin_numbers[type][pin]] = pin
                        # Instantiate poke class, assign callback, and make reverse dict
                        self.pins[type][pin] = handler(pin_numbers[type][pin])
                        self.pins[type][pin].assign_cb(self.handle_trigger)
                    except:
                        # TODO: More informative exception
                        Exception('Something went wrong instantiating pins, tell jonny to handle this better!')

            # Then LEDs
            elif type == 'LEDS':
                print('reached LEDs')
                for pin, handler in values.items():
                    try:
                        self.pins[type][pin] = handler(pins=pin_numbers[type][pin])
                    except:
                        Exception("Something wrong instantiating LEDs")

            elif type == 'PORTS':
                for pin, handler in values.items():
                    try:
                        self.pins[type][pin] = handler(pin_numbers[type][pin], duration=self.reward)
                    except:
                        Exception('Something wrong instantiating solenoids')
            else:
                Exception('HARDWARE dict misspecified in class definition')

    def set_leds(self, color_dict=None):
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
                if k == "LEDS":
                    obj.set_color([0,0,0])
                obj.release()


