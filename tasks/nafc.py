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
import sys
import os
import random
# from taskontrol.settings import rpisettings as rpiset
import datetime
import itertools
import warnings
import tables
import json
import threading

try:
    import pyo
except ImportError:
    Warning('pyo could not be loaded, sounds will be unavailable!')
from core import hardware
from tasks import Task
from stim.sound import sounds
from stim import Stim_Manager
from collections import OrderedDict as odict

import prefs

# This declaration allows Mouse to identify which class in this file contains the task class. Could also be done with __init__ but yno I didnt for no reason.
# TODO: Move this to __init__
TASK = 'Nafc'

# TODO: Make meta task class that has logic for loading sounds, starting pyo server etc.

class Nafc(Task):
    """
    Actually 2afc, but can't have number as first character of class.
    Template for 2afc tasks. Pass in a dict. of sounds & other parameters,
    """

    # TODO: Make shutdown method, clear pins, etc.

    STAGE_NAMES = ["request", "discrim", "reinforcement"]

    # Class attributes


    # List of needed params, returned data and data format.
    # Params are [name]={'tag': Human Readable Tag, 'type': 'int', 'float', 'check', etc.}
    PARAMS = odict()
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
    PARAMS['timeout']        = {'tag':'Delay Timeout (ms)',
                                'type':'int'}
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
                 punish_stim=False, punish_dur=100, correction=True, correction_pct=50.,
                 bias_mode="None", bias_threshold=20, timeout=10000, current_trial=0, **kwargs):
        # Rewards, punish time, etc. in ms.
        # pct_correction is the % of trials that are correction trials
        # bias_correct is 1 or 0 whether you'd like bias correction enabled: eg. if mice are 65% biased towards one side,
        #     that side will only be the target 35% of the time.

        super(Nafc, self).__init__()

        # Fixed parameters
        # Because the current protocol is json.loads from a string,
        # we should explicitly type everything to be safe.
        self.reward         = float(reward)
        self.req_reward     = bool(req_reward)
        self.punish_stim   = bool(punish_stim)
        self.punish_dur     = float(punish_dur)
        self.correction     = bool(correction)
        self.correction_pct = float(correction_pct)/100
        self.bias_mode      = str(bias_mode)
        self.bias_threshold = float(bias_threshold)/100
        self.timeout        = int(timeout)

        # Variable Parameters
        self.target = None
        self.distractor = None
        self.stim = None
        self.response = None
        self.correct = None
        self.correction_trial = False
        self.last_was_correction = False
        self.trial_counter = itertools.count(int(current_trial))
        self.current_trial = int(current_trial)
        self.timers = []
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
        self.set_reward(reward)

        # Initialize stim manager
        if not stim:
            raise RuntimeError("Cant instantiate task without stimuli!")
        else:
            self.stim_manager = Stim_Manager(stim)

        # give the sounds a function to call when they end
        self.stim_manager.set_triggers(self.stim_end)

        if self.correction:
            self.stim_manager.do_correction(self.correction_pct)

        if self.bias_mode != "None":
            self.stim_manager.do_bias(mode=self.bias_mode,
                                      thresh=self.bias_threshold)

        # If we aren't passed an event handler
        # (used to signal that a trigger has been tripped),
        # we should warn whoever called us that things could get a little screwy
        if not stage_block:
            raise Warning('No stage_block Event() was passed, youll need to handle stage progression on your own')
        else:
            self.stage_block = stage_block


    def center_out(self, pin, level, tick):
        """

        :param pin:
        :param level:
        :param tick:
        """
        # Called when something leaves the center pin,
        # We use this to handle the mouse leaving the port early
        if self.discrim_playing:
            self.bail_trial()

    def mark_playing(self):
        """

        """
        self.discrim_playing = True



    ##################################################################################
    # Stage Functions
    ##################################################################################
    def request(self,*args,**kwargs):
        """

        :param args:
        :param kwargs:
        :return:
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

        print(self.target, self.distractor, self.stim)
        sys.stdout.flush()

        # if we're doing correction trials, check if this is one
        if self.correction:
            self.correction_trial = self.stim_manager.correction_trial

        # Set sound trigger and LEDs
        # We make two triggers to play the sound and change the light color
        change_to_blue = lambda: self.pins['LEDS']['C'].set_color([0,0,255])

        # set triggers
        if self.req_reward is True:
            self.triggers['C'] = [change_to_blue, self.mark_playing, self.pins['PORTS']['C'].open, self.stim.play]
        else:
            self.triggers['C'] = [change_to_blue, self.mark_playing, self.stim.play]

        # set to green in the meantime
        self.set_leds({'C': [0, 255, 0]})

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
        return data

    def discrim(self,*args,**kwargs):
        """

        :param args:
        :param kwargs:
        :return:
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

        :param args:
        :param kwargs:
        :return:
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

    def respond(self, pin):
        """

        :param pin:
        """
        self.response = pin



    def stim_end(self):
        """

        """
        # Called by the discrim sound's table trigger when playback is finished
        # Used in punishing leaving early
        self.discrim_playing = False
        if not self.bailed and self.current_stage == 1:
            self.set_leds({'L':[0,255,0], 'R':[0,255,0]})


    def bail_trial(self):
        """

        """
        # If a timer ends or the mouse pulls out too soon, we punish and bail
        self.bailed = 1
        self.triggers = {}
        self.punish()
        self.stage_block.set()

    def clear_triggers(self):
        """

        """
        for pin in self.pins.values():
            pin.clear_cb()


    def flash_leds(self):
        """

        """
        for k, v in self.pins['LEDS'].items():
            v.flash(self.punish_dur)


class Gap_2AFC(Nafc):
    """

    """
    def __init__(self, **kwargs):

        super(Gap_2AFC, self).__init__(**kwargs)


    def load_sounds(self):
        """

        """
        # TODO: Definitely put this in a metaclass

        # Iterate through sounds and load them to memory
        for k, v in self.soundict.items():
            # If multiple sounds on one side, v will be a list
            if isinstance(v, list):
                self.sounds[k] = []
                for sound in v:
                    if float(sound['duration']) == 0:
                        self.sounds[k].append(None)
                        continue
                        # a zero duration gap doesn't change the continuous noise object

                    # We send the dict 'sound' to the function specified by 'type' and 'SOUND_LIST' as kwargs
                    self.sounds[k].append(sounds.SOUND_LIST[sound['type']](**sound))
                    # Then give the sound a callback to mark when it's finished
                    #self.sounds[k][-1].set_trigger(self.stim_end)
            # If not a list, a single sound
            else:
                if v['duration'] == 0:
                    self.sounds[k] = [None]
                    continue

                self.sounds[k] = sounds.SOUND_LIST[v['type']](**v)
                #self.sounds[k].set_trigger(self.stim_end)

    def blank_trigger(self):
        """

        """
        print('blank trig')
        sys.stdout.flush()
        #pass

    def stim_end(self):
        """

        """
        # Called by the discrim sound's table trigger when playback is finished
        # Used in punishing leaving early

        self.set_leds({'L':[0,255,0], 'R':[0,255,0]})

    def request(self,*args,**kwargs):
        """

        :param args:
        :param kwargs:
        :return:
        """
        # Set the event lock
        self.stage_block.clear()

        # Reset all the variables that need to be
        for v in self.resetting_variables:
            v = None

        self.triggers = {}



        # Attempt to identify target sound
        #TODO: Implement sound ID's better
        #try:
        #    self.target_sound_id = self.target_sound.id
        #except AttributeError:
        #    warnings.warn("Sound ID not defined! Sounds cannot be uniquely identified!")
        #    self.target_sound_id = None

        # Set sound trigger and LEDs
        # We make two triggers to play the sound and change the light color

        # set triggers
        if self.target_sound is None:
            sound_trigger = self.blank_trigger
        else:
            sound_trigger = self.target_sound.play


        if self.req_reward is True:
            self.triggers['C'] = [self.pins['PORTS']['C'].open, sound_trigger, self.stim_end]
        else:
            self.triggers['C'] = [sound_trigger, self.stim_end]
        self.set_leds({'C': [0, 255, 0]})

        self.current_trial = self.trial_counter.next()
        data = {
            'target':self.target,
            #'target_sound_id':self.target_sound_id,
            'RQ_timestamp':datetime.datetime.now().isoformat(),
            'trial_num' : self.current_trial
            #'correction':self.correction_trial
        }
        # get sound info and add to data dict
        if self.target_sound is None:
            sound_info = {'duration':0, 'amplitude':0.01}
        else:
            sound_info = {k:getattr(self.target_sound, k) for k in self.target_sound.PARAMS}
            data.update({'type': self.target_sound.type})

        data.update(sound_info)


        self.current_stage = 0
        return data

    def end(self):
        """

        """
        for k, v in self.sounds.items():
            if isinstance(v, list):
                for sound in v:
                    try:
                        sound.stop()
                    except:
                        pass
            else:
                try:
                    v.stop()
                except:
                    pass

        for k, v in self.pins.items():
            for pin, obj in v.items():
                if k == "LEDS":
                    obj.set_color([0,0,0])
                obj.release()









