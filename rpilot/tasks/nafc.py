
import datetime
import itertools
import tables
import threading

from rpilot.core import hardware
from rpilot.tasks import Task
from rpilot.stim import init_manager
from collections import OrderedDict as odict
from rpilot.core.networking import Net_Node

from rpilot import prefs

# This declaration allows Mouse to identify which class in this file contains the task class. Could also be done with __init__ but yno I didnt for no reason.
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
        bailed (0, 1): Mouse answered before stimulus was finished playing.
        current_stage (int): As each stage is reached, update for asynchronous event reference

    """
    STAGE_NAMES = ["request", "discrim", "reinforcement"]

    # Class attributes


    # List of needed params, returned data and data format.
    # Params are [name]={'tag': Human Readable Tag, 'type': 'int', 'float', 'check', etc.}
    PARAMS = odict()
    # TODO: Reward no longer just duration -- fix with parameter structure
    PARAMS['reward']         = {'tag':'Reward Duration (ms)',
                                'type':'int'}
    PARAMS['req_reward']     = {'tag':'Request Rewards',
                                'type':'check'}
    PARAMS['punish_stim']   = {'tag':'White Noise Punishment',
                                'type':'check'}
    PARAMS['punish_dur']     = {'tag':'Punishment Duration (ms)',
                                'type':'int'}
    PARAMS['correction']     = {'tag':'Correction Trials',
                                'type':'check'}
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
        # This class allows the Mouse object to make a data table with the correct data types. You must update it for any new data you'd like to store
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

    def __init__(self, stage_block=None, stim=None, reward=50, req_reward=False,
                 punish_stim=False, punish_dur=100, correction=False, correction_pct=50.,
                 bias_mode=False, bias_threshold=20, current_trial=0, **kwargs):
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
    #     # We use this to handle the mouse leaving the port early
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
        # We make two triggers to play the sound and change the light color
        change_to_blue = lambda: self.pins['LEDS']['C'].set_color([0,0,255])

        # set triggers
        if self.req_reward is True:
            self.triggers['C'] = [change_to_blue, self.stim_start, self.pins['PORTS']['C'].open, self.stim.play]
        else:
            self.triggers['C'] = [change_to_blue, self.stim_start, self.stim.play]

        self.current_trial = self.trial_counter.next()
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

        self.triggers[self.target] = [lambda: self.respond(self.target), self.pins['PORTS'][self.target].open]
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
        self.set_leds({'L':[0,255,0], 'R':[0,255,0]})

    # def bail_trial(self):
    #     # If a timer ends or the mouse pulls out too soon, we punish and bail
    #     self.bailed = 1
    #     self.triggers = {}
    #     self.punish()
    #     self.stage_block.set()

    # def clear_triggers(self):
    #     for pin in self.pins.values():
    #         pin.clear_cb()

    def flash_leds(self):
        """
        flash lights for punish_dir
        """
        for k, v in self.pins['LEDS'].items():
            v.flash(self.punish_dur)


class Nafc_Wheel(Nafc):
    """
    2afc using a wheel run on a child pi as the input device
    """
    HARDWARE = {
        'POKES': {
            'C': hardware.Beambreak,
        },
        'FLAGS': {
            'L': hardware.Flag,
            'R': hardware.Flag
        },
        'LEDS': {
            # TODO: use LEDs, RGB vs. white LED option in init
            'L': hardware.LED_RGB,
            'C': hardware.LED_RGB,
            'R': hardware.LED_RGB
        }
    }

    PLOT = {
        'data': {
            'x':'shaded',
            'response':'segment'
        },
        'continuous' : True
    }

    PARAMS = Nafc.PARAMS



    def __init__(self, **kwargs):
        self.init_networking(kwargs)

        super(Nafc_Wheel, self).__init__(**kwargs)


        # TODO: Update PARAMS with wheel params
    def init_networking(self, kwargs):

        self.node = Net_Node(id="T_{}".format(prefs.NAME),
                             upstream=prefs.NAME,
                             port=prefs.MSGPORT,
                             listens = {},
                             instance=True)

        value = {
            'child': {'parent':prefs.NAME, 'mouse':kwargs['mouse']},
            'task_type': 'Wheel Child',
            'mouse': kwargs['mouse']
        }

        self.node.send(key='CHILD', value=value)





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
#             self.triggers['C'] = [self.pins['PORTS']['C'].open, sound_trigger, self.stim_end]
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
#         for k, v in self.pins.items():
#             for pin, obj in v.items():
#                 if k == "LEDS":
#                     obj.set_color([0,0,0])
#                 obj.release()









