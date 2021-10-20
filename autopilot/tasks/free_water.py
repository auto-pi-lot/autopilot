from collections import OrderedDict as odict
import tables
import itertools
import random
import datetime

import autopilot.hardware.gpio

from autopilot.tasks.task import Task

TASK = 'Free_water'

class Free_Water(Task):
    """
    Randomly light up one of the ports, then dispense water when the subject pokes there

    Two stages:

    * waiting for response, and
    * reporting the response afterwards

    Attributes:
        target ('L', 'C', 'R'): The correct port
        trial_counter (:class:`itertools.count`): Counts trials starting from current_trial specified as argument
        triggers (dict): Dictionary mapping triggered pins to callable methods.
        num_stages (int): number of stages in task (2)
        stages (:class:`itertools.cycle`): iterator to cycle indefinitely through task stages.
    """

    STAGE_NAMES = ["water", "response"]

    # Params
    PARAMS = odict()
    PARAMS['reward'] = {'tag':'Reward Duration (ms)',
                        'type':'int'}
    PARAMS['allow_repeat'] = {'tag':'Allow Repeated Ports?',
                              'type':'bool'}

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
            'L': autopilot.hardware.gpio.Digital_In,
            'C': autopilot.hardware.gpio.Digital_In,
            'R': autopilot.hardware.gpio.Digital_In
        },
        'LEDS':{
            # TODO: use LEDs, RGB vs. white LED option in init
            'L': autopilot.hardware.gpio.LED_RGB,
            'C': autopilot.hardware.gpio.LED_RGB,
            'R': autopilot.hardware.gpio.LED_RGB
        },
        'PORTS':{
            'L': autopilot.hardware.gpio.Solenoid,
            'C': autopilot.hardware.gpio.Solenoid,
            'R': autopilot.hardware.gpio.Solenoid
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
        """
        Args:
            stage_block (:class:`threading.Event`): used to signal to the carrying Pilot that the current trial stage is over
            current_trial (int): If not zero, initial number of `trial_counter`
            reward (int): ms to open solenoids
            allow_repeat (bool): Whether the correct port is allowed to repeat between trials
            **kwargs:
        """
        super(Free_Water, self).__init__()
        self.logger.debug('superclass initialized')

        if not stage_block:
            self.logger.warning('No stage_block Event() was passed, youll need to handle stage progression on your own')
        else:
            self.stage_block = stage_block

        # Fixed parameters
        if isinstance(reward, dict):
            self.reward = reward
        else:
            self.reward         = {'type':'duration',
                                   'value': float(reward)}




        # Variable parameters
        self.target = random.choice(['L', 'C', 'R'])
        self.trial_counter = itertools.count(int(current_trial))
        self.triggers = {}

        # Stage list to iterate
        stage_list = [self.water, self.response]
        self.num_stages = len(stage_list)
        self.stages = itertools.cycle(stage_list)

        # Init hardware
        self.hardware = {}
        self.pin_id = {} # Inverse pin dictionary
        self.init_hardware()
        self.logger.debug('hardware initialized')

        # Set reward values for solenoids
        # TODO: Super inelegant, implement better with reward manager
        if self.reward['type'] == "volume":
            self.set_reward(vol=self.reward['value'])
        else:
            self.set_reward(duration=self.reward['value'])
        self.logger.debug('reward set')

        self.allow_repeat = bool(allow_repeat)

    def water(self, *args, **kwargs):
        """
        First stage of task - open a port if it's poked.

        Returns:
            dict: Data dictionary containing::

                'target': ('L', 'C', 'R') - correct response
                'timestamp': isoformatted timestamp
                'trial_num': number of current trial
        """
        self.stage_block.clear()

        # Choose random port
        if self.allow_repeat:
            self.target = random.choice(['L', 'C', 'R'])
        else:
            other_ports = [t for t in ['L', 'C', 'R'] if t is not self.target]
            self.target = random.choice(other_ports)

        # Set triggers and set the target LED to green.
        self.triggers[self.target] = self.hardware['PORTS'][self.target].open
        self.set_leds({self.target: [0, 255, 0]})

        # Return data
        data = {
            'target': self.target,
            'timestamp': datetime.datetime.now().isoformat(),
            'trial_num' : next(self.trial_counter)
        }
        return data


    def response(self):
        """
        Just have to alert the Terminal that the current trial has ended
        and turn off any lights.
        """
        # we just have to tell the Terminal that this trial has ended

        # mebs also turn the light off rl quick
        self.set_leds()

        return {'TRIAL_END':True}



    def end(self):
        """
        When shutting down, release all hardware objects and turn LEDs off.
        """
        for k, v in self.hardware.items():
            for pin, obj in v.items():
                obj.release()


