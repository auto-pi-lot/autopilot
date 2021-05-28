
import datetime
import itertools
import tables
import threading
from copy import copy
import typing

import numpy as np

import autopilot.hardware.gpio
from autopilot.tasks import Task
from autopilot.stim import init_manager
from autopilot.stim.sound import sounds as stim_sounds
from autopilot.hardware import gpio
from collections import OrderedDict as odict
from autopilot.core.networking import Net_Node
from autopilot.core.utils import find_recursive

from autopilot import prefs
import pdb
import pickle

# This declaration allows Subject to identify which class in this file contains the task class. Could also be done with __init__ but yno I didnt for no reason.
# TODO: Move this to __init__
TASK = 'Nafc'

class Nafc(Task):
    """
    A Two-alternative forced choice task.

    *(can't have number as first character of class.)*

    **Stages**

    * **request** - compute stimulus, set request trigger in center port.
    * **discrim** - respond to input, set reward/punishment triggers on target/distractor ports
    * **reinforcement** - deliver reward/punishment, end trial.

    Attributes:
        target ("L", "R"): Correct response
        distractor ("L", "R"): Incorrect response
        stim : Current stimulus
        response ("L", "R"): Response to discriminand
        correct (0, 1): Current trial was correct/incorrect
        correction_trial (bool): If using correction trials, last trial was a correction trial
        trial_counter (:class:`itertools.count`): Which trial are we on?
        discrim_playing (bool): Is the stimulus playing?
        bailed (0, 1): Subject answered before stimulus was finished playing.
        current_stage (int): As each stage is reached, update for asynchronous event reference

    """
    STAGE_NAMES = ["request", "discrim", "reinforcement"]

    # Class attributes


    # List of needed params, returned data and data format.
    # Params are [name]={'tag': Human Readable Tag, 'type': 'int', 'float', 'bool', etc.}
    PARAMS = odict()
    # TODO: Reward no longer just duration -- fix with parameter structure
    PARAMS['reward']         = {'tag':'Reward Duration (ms)',
                                'type':'int'}
    PARAMS['req_reward']     = {'tag':'Request Rewards',
                                'type':'bool'}
    PARAMS['punish_stim']   = {'tag':'White Noise Punishment',
                                'type':'bool'}
    PARAMS['punish_dur']     = {'tag':'Punishment Duration (ms)',
                                'type':'int'}
    PARAMS['correction']     = {'tag':'Correction Trials',
                                'type':'bool'}
    PARAMS['correction_pct'] = {'tag':'% Correction Trials',
                                'type':'int',
                                'depends':{'correction':True}}
    PARAMS['bias_mode']      = {'tag':'Bias Correction Mode',
                                'type':'list',
                                'values':{'None':0, 'Proportional':1, 'Thresholded Proportional':2}}
    PARAMS['bias_threshold'] = {'tag': 'Bias Correction Threshold (%)',
                                'type':'int',
                                'depends':{'bias_mode':2}}
    #PARAMS['timeout']        = {'tag':'Delay Timeout (ms)',
    #                            'type':'int'}
    PARAMS['stim']           = {'tag':'Sounds',
                                'type':'sounds'}

    # Set plot params, which data should be plotted, its default shape, etc.
    # TODO: Plots should take the default type, but options panel should be able to set - eg. corrects are done by rolling mean as default, but can be made points
    PLOT = {
        'data': {
            'target'   : 'point',
            'response' : 'segment',
            'correct'  : 'rollmean'
        },
        'chance_bar'  : True, # Draw a red bar at 50%
        'roll_window' : 50 # number of trials to roll window over
    }

    # PyTables Data descriptor
    # for numpy data types see http://docs.scipy.org/doc/numpy/reference/arrays.dtypes.html#arrays-dtypes-constructing
    class TrialData(tables.IsDescription):
        # This class allows the Subject object to make a data table with the correct data types. You must update it for any new data you'd like to store
        trial_num = tables.Int32Col()
        target = tables.StringCol(1)
        response = tables.StringCol(1)
        correct = tables.Int32Col()
        correction = tables.Int32Col()
        RQ_timestamp = tables.StringCol(26)
        DC_timestamp = tables.StringCol(26)
        bailed = tables.Int32Col()

    HARDWARE = {
        'POKES':{
            'L': gpio.Digital_In,
            'C': gpio.Digital_In,
            'R': gpio.Digital_In
        },
        'LEDS':{
            # TODO: use LEDs, RGB vs. white LED option in init
            'L': gpio.LED_RGB,
            'C': gpio.LED_RGB,
            'R': gpio.LED_RGB
        },
        'PORTS':{
            'L': gpio.Solenoid,
            'C': gpio.Solenoid,
            'R': gpio.Solenoid
        }
    }


    def __init__(self, stage_block=None, stim=None, reward=50, req_reward=False,
                 punish_stim=False, punish_dur=100, correction=False, correction_pct=50.,
                 bias_mode=False, bias_threshold=20, current_trial=0, stim_light=True, **kwargs):
        """
        Args:
            stage_block (:class:`threading.Event`): Signal when task stages complete.
            stim (dict): Stimuli like::


                "sounds": {
                    "L": [{"type": "Tone", ...}],
                    "R": [{"type": "Tone", ...}]
                }

            reward (float): duration of solenoid open in ms
            req_reward (bool): Whether to give a water reward in the center port for requesting trials
            punish_stim (bool): Do a white noise punishment stimulus
            punish_dur (float): Duration of white noise in ms
            correction (bool): Should we do correction trials?
            correction_pct (float):  (0-1), What proportion of trials should randomly be correction trials?
            bias_mode (False, "thresholded_linear"): False, or some bias correction type (see :class:`.managers.Bias_Correction` )
            bias_threshold (float): If using a bias correction mode, what threshold should bias be corrected for?
            current_trial (int): If starting at nonzero trial number, which?
            stim_light (bool): Should the LED be turned blue while the stimulus is playing?
            **kwargs:
        """
        super(Nafc, self).__init__()

        # Fixed parameters
        # Because the current protocol is json.loads from a string,
        # we should explicitly type everything to be safe.
        if isinstance(reward, dict):
            self.reward = reward
        else:
            self.reward         = {'type':'duration',
                                   'value': float(reward)}
        self.req_reward     = bool(req_reward)
        self.punish_stim   = bool(punish_stim)
        self.punish_dur     = float(punish_dur)
        self.correction     = bool(correction)
        self.correction_pct = float(correction_pct)/100
        self.bias_mode      = bias_mode
        self.bias_threshold = float(bias_threshold)/100
        self.stim_light      = bool(stim_light)
        #self.timeout        = int(timeout)

        # Variable Parameters
        self.target = None
        self.distractor = None
        self.stim = None
        self.response = None
        self.correct = None
        self.correction_trial = False
        self.trial_counter = itertools.count(int(current_trial))
        self.current_trial = int(current_trial)
        #self.discrim_finished = False # Set to true once the discrim stim has finished, used for punishing leaving C early
        self.discrim_playing = False
        self.current_stage = None # Keep track of stages so some asynchronous callbacks know when it's their turn
        self.bailed = 0

        # We make a list of the variables that need to be reset each trial so it's easier to do so
        self.resetting_variables = [self.response, self.bailed]

        # This allows us to cycle through the task by just repeatedly calling self.stages.next()
        stage_list = [self.request, self.discrim, self.reinforcement]
        self.num_stages = len(stage_list)
        self.stages = itertools.cycle(stage_list)

        # Initialize hardware
        self.init_hardware()
        self.logger.debug('Hardware initialized')

        # Set reward values for solenoids
        # TODO: Super inelegant, implement better with reward manager
        if self.reward['type'] == "volume":
            self.set_reward(vol=self.reward['value'])
        else:
            self.set_reward(duration=self.reward['value'])

        # Initialize stim manager
        if not stim:
            raise RuntimeError("Cant instantiate task without stimuli!")
        else:
            self.stim_manager = init_manager(stim)

        # give the sounds a function to call when they end
        self.stim_manager.set_triggers(self.stim_end)

        if self.correction:
            self.stim_manager.do_correction(self.correction_pct)

        if bias_mode:
            self.stim_manager.do_bias(mode=self.bias_mode,
                                      thresh=self.bias_threshold)
        self.logger.debug('Stimulus manager initialized')

        # If we aren't passed an event handler
        # (used to signal that a trigger has been tripped),
        # we should warn whoever called us that things could get a little screwy
        if not stage_block:
            raise Warning('No stage_block Event() was passed, youll need to handle stage progression on your own')
        else:
            self.stage_block = stage_block

    #
    # def center_out(self, pin, level, tick):
    #     """
    #
    #     """
    #     # Called when something leaves the center pin,
    #     # We use this to handle the subject leaving the port early
    #     if self.discrim_playing:
    #         self.bail_trial()


    ##################################################################################
    # Stage Functions
    ##################################################################################
    def request(self,*args,**kwargs):
        """
        Stage 0: compute stimulus, set request trigger in center port.

        Returns:
            data (dict): With fields::

                {
                'target': self.target,
                'trial_num' : self.current_trial,
                'correction': self.correction_trial,
                'type': stimulus type,
                **stim.PARAMS
                }

        """
        # Set the event lock
        self.stage_block.clear()

        # Reset all the variables that need to be
        for v in self.resetting_variables:
            v = None

        # reset triggers if there are any left
        self.triggers = {}

        # get next stim
        self.target, self.distractor, self.stim = self.stim_manager.next_stim()
        # buffer it
        self.stim.buffer()

        # if we're doing correction trials, check if this is one
        if self.correction:
            self.correction_trial = self.stim_manager.correction_trial

        # Set sound trigger and LEDs
        self.triggers['C'] = [self.stim.play, self.stim_start]
        if self.stim_light:
            change_to_blue = lambda: self.hardware['LEDS']['C'].set([0, 0, 255])
            self.triggers['C'].append(change_to_blue)
        else:
            # just turn the center light off and side lights on immediately.
            turn_off = lambda: self.set_leds({
                'L': [0,255,0],
                'R': [0,255,0]
            })
            #turn_off = lambda: self.hardware['LEDS']['C'].set([0,0,0])
            self.triggers['C'].append(turn_off)

        if self.req_reward:
            self.triggers['C'].append(self.hardware['PORTS']['C'].open)


        self.current_trial = next(self.trial_counter)
        data = {
            'target':self.target,
            'trial_num' : self.current_trial,
            'correction':self.correction_trial
        }
        # get stim info and add to data dict
        sound_info = {k:getattr(self.stim, k) for k in self.stim.PARAMS}
        data.update(sound_info)
        data.update({'type':self.stim.type})

        self.current_stage = 0

        # wait on punish block
        # FIXME: Only waiting to test whether this is where the bug that hangs after this stage is
        self.punish_block.wait(20)

        # set to green in the meantime
        self.set_leds({'C': [0, 255, 0]})


        return data

    def discrim(self,*args,**kwargs):
        """
        Stage 1:  respond to input, set reward/punishment triggers on target/distractor ports

        Returns:
            data (dict): With fields::
                {
                'RQ_timestamp': datetime.datetime.now().isoformat(),
                'trial_num': self.current_trial,
                }

        """
        # moust just poked in center, set response triggers
        self.stage_block.clear()

        self.triggers[self.target] = [lambda: self.respond(self.target), self.hardware['PORTS'][self.target].open]
        self.triggers[self.distractor] = [lambda: self.respond(self.distractor), self.punish]

        # TODO: Handle timeout

        # Only data is the timestamp
        data = {'RQ_timestamp': datetime.datetime.now().isoformat(),
                'trial_num': self.current_trial}
        self.current_stage = 1
        return data

    def reinforcement(self,*args,**kwargs):
        """
        Stage 2 - deliver reward/punishment, end trial.

        Returns:
            data (dict): With fields::

                 {
                'DC_timestamp': datetime.datetime.now().isoformat(),
                'response': self.response,
                'correct': self.correct,
                'bailed': self.bailed,
                'trial_num': self.current_trial,
                'TRIAL_END': True
                }
        """
        # We do NOT clear the task event flag here because we want
        # the pi to call the next stage immediately
        # We are just filling in the last data
        # and performing any calculations we need for the next trial
        if self.bailed:
            self.bailed = 0
            data = {
                'DC_timestamp': datetime.datetime.now().isoformat(),
                'bailed':1,
                'trial_num': self.current_trial,
                'TRIAL_END':True
            }
            return data

        if self.response == self.target:
            self.correct = 1
        else:
            self.correct = 0

        # update stim manager
        self.stim_manager.update(self.response, self.correct)


        data = {
            'DC_timestamp': datetime.datetime.now().isoformat(),
            'response':self.response,
            'correct':self.correct,
            'bailed':0,
            'trial_num': self.current_trial,
            'TRIAL_END':True
        }
        self.current_stage = 2
        return data

    def punish(self):
        """
        Flash lights, play punishment sound if set
        """
        # TODO: If we're not in the last stage (eg. we were timed out after stim presentation), reset stages
        self.punish_block.clear()

        if self.punish_stim:
            self.stim_manager.play_punishment()

        # self.set_leds()
        self.flash_leds()
        threading.Timer(self.punish_dur / 1000., self.punish_block.set).start()


    def respond(self, pin):
        """
        Set self.response

        Args:
            pin: Pin to set response to
        """
        self.response = pin

    def stim_start(self):
        """
        mark discrim_playing = true
        """
        self.discrim_playing = True


    def stim_end(self):
        """
        called by stimulus callback

        set outside lights blue
        """
        # Called by the discrim sound's table trigger when playback is finished
        # Used in punishing leaving early
        self.discrim_playing = False
        #if not self.bailed and self.current_stage == 1:
        if self.stim_light:
            self.set_leds({'L':[0,255,0], 'R':[0,255,0]})

    # def bail_trial(self):
    #     # If a timer ends or the subject pulls out too soon, we punish and bail
    #     self.bailed = 1
    #     self.triggers = {}
    #     self.punish()
    #     self.stage_block.set()

    # def clear_triggers(self):
    #     for pin in self.hardware.values():
    #         pin.clear_cb()

    def flash_leds(self):
        """
        flash lights for punish_dir
        """
        for k, v in self.hardware['LEDS'].items():
            if isinstance(v, gpio.LED_RGB):
                v.flash(self.punish_dur)

class Nafc_Gap(Nafc):
    PARAMS = copy(Nafc.PARAMS)
    del PARAMS['punish_stim']
    PARAMS['noise_amplitude'] = {'tag':'Amplitude of continuous white noise',
                                 'type': 'float'}

    def __init__(self, noise_amplitude = 0.01, **kwargs):
        """
        A Mild variation of :class:`Nafc` that starts continuous white noise that plays
        continuously while the task is active.

        Args:
            noise_amplitude (float): Multiplier used to scale amplitude of continuous noise
            **kwargs: passed to :class:`Nafc`
        """

        # Can't really have a white noise punishment when there is continuous noise
        kwargs['punish_stim'] = False
        kwargs['stim_light'] = False
        super(Nafc_Gap, self).__init__(**kwargs)

        self.logger.debug('starting background sound')
        self.noise_amplitude = noise_amplitude
        self.noise_duration = 10*1000 # 10 seconds
        self.noise = stim_sounds.Noise(duration=self.noise_duration,
                                  amplitude=self.noise_amplitude)

        self.noise.play_continuous()
        self.logger.debug('background sound started')


    def end(self):
        """
        Stop the task, ending the continuous white noise.
        """
        self.noise.stop_continuous()
        super(Nafc_Gap, self).end()


class Nafc_Gap_Laser(Nafc_Gap):
    PARAMS = copy(Nafc_Gap.PARAMS)
    PARAMS['laser_probability'] = {'tag': 'Probability (of trials whose targets match laser_mode) of laser being turned on (0-1)',
                                   'type':'float'}
    PARAMS['laser_mode'] = {'tag':'Laser Mode, laser will be possible when target == ?',
        'type':'list',
        'values':{
            'L':0,
            'R':1,
            'Both':2
        }}
    PARAMS['laser_freq'] = {'tag': 'Laser Pulse Frequency (Hz), list-like [20, 30]',
                            'type': 'str'}
    PARAMS['laser_duty_cycle'] = {'tag': 'Laser Duty Cycle (0-1), list-like [0.1, 0.2]',
                                  'type': 'str'}
    PARAMS['laser_durations'] = {'tag': 'Laser durations (ms), list-like [10, 20]. if blank, use durations from stimuli',
                                 'type': 'str'}
    PARAMS['arena_led_mode'] = {'tag': 'Arena LED Mode: always ON vs. on for longest stim duration during requests',
                                'type': 'list',
                                'values':{'ON': 0, 'STIM': 1}}

    HARDWARE = copy(Nafc_Gap.HARDWARE)

    HARDWARE['LASERS'] = {
        'LR': gpio.Digital_Out
    }

    HARDWARE['LEDS']['TOP'] = gpio.Digital_Out

    TrialData = copy(Nafc_Gap.TrialData)
    TrialData.laser = tables.Int32Col()
    TrialData.laser_duration = tables.Float32Col()
    TrialData.laser_freq = tables.Float32Col()
    TrialData.laser_duty_cycle = tables.Float32Col()


    def __init__(self,
                 laser_probability: float,
                 laser_mode: str,
                 laser_freq: typing.Union[str, list],
                 laser_duty_cycle: typing.Union[str, list],
                 laser_durations: typing.Union[str, list],
                 arena_led_mode: str = 'ON',
                 **kwargs):
        """
        Gap detection task with ability to control lasers via TTL logic for optogenetics

        :attr:`.laser_freq`, :attr:`.laser_duty_cycle`, and :attr:`.laser_durations` can be passed
        either as an integer (actually typically a string because of the way the value is pulled from the protocol wizard),
        or as a list -- the product of values for all three are generated and presented equiprobably
        (eg. if ``laser_freq = 20, laser_duty_cycle=[0.1, 0.2, 0.3], laser_durations = [1, 2, 4, 8]`` were passed,
        then 1*3*4=12 different laser conditions would be possible.

        .. note::

            Subclasses like these will be made obsolete with the completion of stimulus managers

        Args:
            laser_probability (float): if trial satisfies ``laser_mode``, probability that laser will be
            laser_mode ('L', 'R', or 'Both'): Selects whether the laser is to be presented when :attr:`.target` is ``'L', 'R'`` or Either.
            laser_freq (str, list): Single value or list of possible laser frequencies in Hz
            laser_duty_cycle (str, list): Single value or list of possible duty cycles from 0-1
            laser_durations (str, list): Single value or list of possible laser durations (total time laser is on) in ms
            arena_led_mode ('ON', 'STIM'): Whether the overhead LED should always be 'ON', or whether it should be illuminated for the duration of the longest stimulus at every request

        Attributes:
            laser_conditions (tuple): tuple of dicts of laser conditions, of format::

                {
                'freq': laser frequency,
                'duty_cycle': laser duty cycle,
                'duration': laser duration,
                'script_id': script ID for the series used by the laser Digital Out object,
                }
        """
        self.laser_probability = float(laser_probability)
        self.laser_mode = laser_mode
        self.arena_led_mode = arena_led_mode

        # accept them if we're given a list of values, otherwise they should be strings that are single values,
        # which are put in lists so they can be iterated over in the product iterator.
        self.laser_freq = laser_freq if isinstance(laser_freq, list) else [float(laser_freq)] # type: list
        self.laser_duty_cycle = laser_duty_cycle if isinstance(laser_duty_cycle, list) else [float(laser_duty_cycle)] # type: list
        self.laser_durations = laser_durations if isinstance(laser_durations, list) else [float(laser_durations)] # type: list

        self.laser_conditions = tuple() # type: typing.Tuple[typing.Dict]

        super(Nafc_Gap_Laser, self).__init__(**kwargs)

        self.init_lasers()

        # -----------------------------------
        # create a pulse for the LED that's equal to the longest stimulus duration
        # use find_recursive to find all durations
        # FIXME: implement stimulus managers properly, including API to get attributes of stimuli
        if self.arena_led_mode == "ON":
            self.hardware['LEDS']['TOP'].turn(True)
        elif self.arena_led_mode == "STIM":
            stim_durations = list(find_recursive('duration', kwargs['stim']))
            max_duration = np.max(stim_durations)
            self.hardware['LEDS']['TOP'].store_series('on', values=1, durations=max_duration )
        else:
            raise ValueError(f'arena_led_mode must be one of ON or STIM, got {self.arena_led_mode}')

    def init_lasers(self):
        """
        Given :attr:`.laser_freq`, :attr:`.laser_duty_cycle`, :attr:`.laser_durations` ,
        create series with :meth:`.Digital_Out.store_series` and populate :attr:`.laser_conditions`
        """

        # TODO: This really should be something that Digital_Out should be capable of doing -- specifying series from these params...

        # --------------------------------------
        # create description of laser pulses
        # iterate over laser condition lists,
        # create lists of values (on/off) and durations (ms)
        # use them to create pigpio scripts using the Digital_Out.store_series() method
        # --------------------------------------------------
        self.logger.debug('Creating laser and LED series')
        # create iterator
        condition_iter = itertools.product(self.laser_durations, self.laser_freq, self.laser_duty_cycle)

        conditions = []
        for duration, freq, duty_cycle in condition_iter:
            # get the durations of on and off for a single cycle
            cycle_duration = (1/freq)*1000 # convert Hz to ms
            duty_cycle_on = duty_cycle * cycle_duration
            duty_cycle_off = cycle_duration - duty_cycle_on

            # get number of repeats to make
            n_cycles = int(np.floor(duration/cycle_duration))
            durations = [duty_cycle_on, duty_cycle_off]*n_cycles
            values = [1, 0]*n_cycles

            # pad any incomplete cycles
            dur_remaining = duration-(cycle_duration*n_cycles)
            if dur_remaining < duty_cycle_on:
                durations.append(dur_remaining)
                values.append(1)
            else:
                durations.extend([duty_cycle_on, dur_remaining-duty_cycle_on])
                values.extend([1, 0])

            # create ID from params
            script_id = f"{duration}_{freq}_{duty_cycle}"


            # store pulses as pigpio scripts
            self.hardware['LASERS']['LR'].store_series(script_id, values=values, durations=durations)

            conditions.append({
                'freq':freq,
                'duty_cycle': duty_cycle,
                'duration': duration,
                'script_id': script_id
            })

        self.laser_conditions = tuple(conditions)

        self.logger.debug(f'Laser series created with {len(self.laser_conditions)} conditions')




    def request(self,*args,**kwargs):
        """
        Call the superclass request method, and then compute laser presentation logic.

        If :attr:`.target` == :attr:`.laser_mode`, spin for a laser trial depending on :attr:`.laser_probability`.

        If we present a laser on this trial, we randomly draw from :attr:`.laser_conditions` and call the appropriate script.
        """
        # call the super method
        data = super(Nafc_Gap_Laser, self).request(*args, **kwargs)

        # handle laser logic
        # if the laser_mode is fulfilled, roll for a laser
        test_laser = False
        if self.laser_mode == "L" and self.target == "L":
            test_laser = True
        elif self.laser_mode == "R" and self.target == "R":
            test_laser = True
        elif self.laser_mode == "Both":
            test_laser = True

        duration = 0
        duty_cycle = 0
        frequency = 0
        do_laser = False
        if test_laser:
            # if we've rolled correctly for a laser...
            if np.random.rand() <= self.laser_probability:
                do_laser = True

                # If we're doing laser, we don't do the stim, so we pop the first two triggers
                del self.triggers['C'][:2]

                # pick a random duration
                condition = np.random.choice(self.laser_conditions)
                duration = condition['duration']
                duty_cycle = condition['duty_cycle']
                frequency = condition['freq']
                # insert the laser triggers before the rest of the triggers
                self.triggers['C'].insert(0, lambda: self.hardware['LASERS']['LR'].series(id=condition['script_id']))

        # always turn the light on
        if self.arena_led_mode == "STIM":
            self.triggers['C'].insert(0, lambda: self.hardware['LEDS']['TOP'].series(id='on'))


        # store the data about the laser status
        data['laser'] = do_laser
        data['laser_duration'] = duration
        data['laser_duty_cycle'] = duty_cycle
        data['laser_frequency'] = frequency

        # return the data created by the original task
        return data

    def set_leds(self, color_dict=None):
        """
        Set the color of all LEDs at once.

        Override base method to exclude TOP led

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
            if k == "TOP":
                continue
            if k in color_dict.keys():
                v.set(color_dict[k])
            else:
                v.set(0)









#
# class Nafc_Wheel(Nafc):
#     """
#     2afc using a wheel run on a child pi as the input device
#     """
#     HARDWARE = {
#         'POKES': {
#             'C': hardware.Beambreak,
#         },
#         'FLAGS': {
#             'L': hardware.Flag,
#             'R': hardware.Flag
#         },
#         'LEDS': {
#             # TODO: use LEDs, RGB vs. white LED option in init
#             'L': hardware.LED_RGB,
#             'C': hardware.LED_RGB,
#             'R': hardware.LED_RGB
#         }
#     }
#
#     PLOT = {
#         'data': {
#             'x':'shaded',
#             'response':'segment'
#         },
#         'continuous' : True
#     }
#
#     PARAMS = Nafc.PARAMS
#
#
#
#     def __init__(self, **kwargs):
#         self.init_networking(kwargs)
#
#         super(Nafc_Wheel, self).__init__(**kwargs)
#
#
#         # TODO: Update PARAMS with wheel params
#     def init_networking(self, kwargs):
#
#         self.node = Net_Node(id="T_{}".format(prefs.get('NAME')),
#                              upstream=prefs.get('NAME'),
#                              port=prefs.get('MSGPORT'),
#                              listens = {},
#                              instance=True)
#
#         value = {
#             'child': {'parent':prefs.get('NAME'), 'subject':kwargs['subject']},
#             'task_type': 'Wheel Child',
#             'subject': kwargs['subject']
#         }
#
#         self.node.send(key='CHILD', value=value)
#




#
# class Gap_2AFC(Nafc):
#     def __init__(self, **kwargs):
#
#         """
#         Args:
#             **kwargs:
#         """
#         super(Gap_2AFC, self).__init__(**kwargs)
#
#
#     def load_sounds(self):
#         # TODO: Definitely put this in a metaclass
#
#         # Iterate through sounds and load them to memory
#         for k, v in self.soundict.items():
#             # If multiple sounds on one side, v will be a list
#             if isinstance(v, list):
#                 self.sounds[k] = []
#                 for sound in v:
#                     if float(sound['duration']) == 0:
#                         self.sounds[k].append(None)
#                         continue
#                         # a zero duration gap doesn't change the continuous noise object
#
#                     # We send the dict 'sound' to the function specified by 'type' and 'SOUND_LIST' as kwargs
#                     self.sounds[k].append(sounds.SOUND_LIST[sound['type']](**sound))
#                     # Then give the sound a callback to mark when it's finished
#                     #self.sounds[k][-1].set_trigger(self.stim_end)
#             # If not a list, a single sound
#             else:
#                 if v['duration'] == 0:
#                     self.sounds[k] = [None]
#                     continue
#
#                 self.sounds[k] = sounds.SOUND_LIST[v['type']](**v)
#                 #self.sounds[k].set_trigger(self.stim_end)
#
#     def blank_trigger(self):
#         print('blank trig')
#         sys.stdout.flush()
#         #pass
#
#     def stim_end(self):
#         # Called by the discrim sound's table trigger when playback is finished
#         # Used in punishing leaving early
#
#         self.set_leds({'L':[0,255,0], 'R':[0,255,0]})
#
#     def request(self,*args,**kwargs):
#         """
#         Args:
#             args:
#             kwargs:
#         """
#         # Set the event lock
#         self.stage_block.clear()
#
#         # Reset all the variables that need to be
#         for v in self.resetting_variables:
#             v = None
#
#         self.triggers = {}
#
#
#
#         # Attempt to identify target sound
#         #TODO: Implement sound ID's better
#         #try:
#         #    self.target_sound_id = self.target_sound.id
#         #except AttributeError:
#         #    warnings.warn("Sound ID not defined! Sounds cannot be uniquely identified!")
#         #    self.target_sound_id = None
#
#         # Set sound trigger and LEDs
#         # We make two triggers to play the sound and change the light color
#
#         # set triggers
#         if self.target_sound is None:
#             sound_trigger = self.blank_trigger
#         else:
#             sound_trigger = self.target_sound.play
#
#
#         if self.req_reward is True:
#             self.triggers['C'] = [self.hardware['PORTS']['C'].open, sound_trigger, self.stim_end]
#         else:
#             self.triggers['C'] = [sound_trigger, self.stim_end]
#         self.set_leds({'C': [0, 255, 0]})
#
#         self.current_trial = self.trial_counter.next()
#         data = {
#             'target':self.target,
#             #'target_sound_id':self.target_sound_id,
#             'RQ_timestamp':datetime.datetime.now().isoformat(),
#             'trial_num' : self.current_trial
#             #'correction':self.correction_trial
#         }
#         # get sound info and add to data dict
#         if self.target_sound is None:
#             sound_info = {'duration':0, 'amplitude':0.01}
#         else:
#             sound_info = {k:getattr(self.target_sound, k) for k in self.target_sound.PARAMS}
#             data.update({'type': self.target_sound.type})
#
#         data.update(sound_info)
#
#
#         self.current_stage = 0
#         return data
#
#     def end(self):
#         for k, v in self.sounds.items():
#             if isinstance(v, list):
#                 for sound in v:
#                     try:
#                         sound.stop()
#                     except:
#                         pass
#             else:
#                 try:
#                     v.stop()
#                 except:
#                     pass
#
#         for k, v in self.hardware.items():
#             for pin, obj in v.items():
#                 if k == "LEDS":
#                     obj.set_color([0,0,0])
#                 obj.release()









