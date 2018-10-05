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
import pprint
import pyo
from core import hardware, sounds
from collections import OrderedDict as odict

# This declaration allows Mouse to identify which class in this file contains the task class. Could also be done with __init__ but yno I didnt for no reason.
# TODO: Move this to __init__
TASK = 'Nafc'

# TODO: Make meta task class that has logic for loading sounds, starting pyo server etc.

class Nafc(object):
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
    PARAMS['punish_sound']   = {'tag':'White Noise Punishment',
                                'type':'check'}
    PARAMS['punish_dur']     = {'tag':'Punishment Duration (ms)',
                                'type':'int'}
    PARAMS['correction']     = {'tag':'Correction Trials',
                                'type':'check'}
    PARAMS['pct_correction'] = {'tag':'% Correction Trials',
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
    PARAMS['sounds']         = {'tag':'Sounds',
                                'type':'sounds'}

    # Dict of data and info about that data that will be returned for each complete trial
    # 'type' refers to the datatype in PyTables, but truth be told I don't remember where these abbrevs came from
    # 'plot' gives information about which data and how it should be plotted. The syntax for this is still evolving
    # DATA = {
    #     'trial_num':       {'type':'i32'},
    #     'target':          {'type':'S1', 'plot':'target'},
    #     'target_sound_id': {'type':'S32'},
    #     'response':        {'type':'S1', 'plot':'response'},
    #     'correct':         {'type':'i32','plot':'correct_roll'},
    #     'bias':            {'type':'f32'}, # TODO: Shouldn't this just be calculated but not stored?
    #     'RQ_timestamp':    {'type':'S26'},
    #     'DC_timestamp':    {'type':'S26'},
    #     'bailed':          {'type':'i32','plot':'bail'}
    # }

    # Set plot params, which data should be plotted, its default shape, etc.
    # TODO: Plots should take the default type, but options panel should be able to set - eg. corrects are done by rolling mean as default, but can be made points
    PLOT = {
        'data': {
            'target'   : 'point',
            'response' : 'segment',
            'correct'  : 'rollmean'
            #'bailed'   : 'highlight'
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
        #target_sound_id = tables.StringCol(32) # FIXME need to do ids way smarter than this
        response = tables.StringCol(1)
        correct = tables.Int32Col()
        #correction = tables.Int32Col()
        bias = tables.Float32Col()
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

    def __init__(self, prefs=None, stage_block=None, sounds=None, reward=50, req_reward=False,
                 punish_sound=False, punish_dur=100, correction=True, pct_correction=50,
                 bias_mode=1, bias_threshold=15, timeout=10000, current_trial=0, **kwargs):
        # Sounds come in two flavors
        #   soundict: a dict of parameters like:
        #       {'L': 'path/to/file.wav', 'R': 'etc'} or
        #       {'L':['path/to/sound1.wav','path/to/sound2.wav']} or
        #       {'L':{'type':'tone', 'frequency':500}} etc.
        #       This is the type that should be passed to the __init__. soundicts are useful for record keeping,
        #       protocol design, etc. but obviously can't be played. Because we want to keep the task class agnostic to
        #       the implementation of the sound system (and PYO is very picky about its namespace anyway),
        #       we also can't make the sounds here. Instead, RPilot should assign a 'sound' dict to the task instance on run.
        #   sounds: a dict of PYO sound tables or other audio objects that the RPilot knows how to play. like:
        #       {'L':[<sound object 1>,<sound object 2>],etc.}
        #       Ideally, the objects will be passed with their playing function unevaluated (eg. pyoTable.out) so that
        #       RPilot can just call it to play (its default behavior). A sound object should also have an additional
        #       attribute "id," created at run by RPilot so that each sound can be uniquely identified.
        # Rewards, punish time, etc. in ms.
        # pct_correction is the % of trials that are correction trials
        # bias_correct is 1 or 0 whether you'd like bias correction enabled: eg. if mice are 65% biased towards one side,
        #     that side will only be the target 35% of the time.
        # Pass assign as 1 to be prompted for all necessary params.

        if not sounds:
            raise RuntimeError("Cant instantiate task without sounds!")

        # If we aren't passed prefs, try to load them from default location
        if not prefs:
            prefs_file = '/usr/rpilot/prefs.json'
            if not os.path.exists(prefs_file):
                raise RuntimeError("No prefs file passed and none found in {}".format(prefs_file))

            with open(prefs_file) as prefs_file_open:
                prefs = json.load(prefs_file_open)
                raise Warning('No prefs file passed, loaded from default location. Should pass explicitly')

        self.prefs = prefs

        # If we aren't passed an event handler
        # (used to signal that a trigger has been tripped),
        # we should warn whoever called us that things could get a little screwy
        if not stage_block:
            raise Warning('No stage_block Event() was passed, youll need to handle stage progression on your own')
        else:
            self.stage_block = stage_block

        # We use another event handler to block for punishment without blocking stage calculation
        self.punish_block = threading.Event()
        self.punish_block.set()

        # Fixed parameters
        # Because the current protocol is json.loads from a string,
        # we should explicitly type everything to be safe.
        self.soundict       = sounds
        self.reward         = int(reward)
        self.req_reward     = bool(req_reward)
        self.punish_sound   = bool(punish_sound)
        self.punish_dur     = float(punish_dur)
        self.correction     = bool(correction)
        self.pct_correction = float(pct_correction)/100
        self.bias_mode      = int(bias_mode)
        self.bias_threshold = float(bias_threshold)
        self.timeout        = int(timeout)

        # Variable Parameters
        self.target = None
        self.target_sound = None
        self.target_sound_id = None
        self.distractor = None
        self.bias = float(0)
        self.response = None
        self.correct = None
        self.correction_trial = False
        self.last_was_correction = False
        self.trial_counter = itertools.count(int(current_trial))
        self.current_trial = 0
        self.triggers = {}
        self.timers = []
        self.last_pin = None # Some functions will depend on the last triggered pin
        #self.discrim_finished = False # Set to true once the discrim stim has finished, used for punishing leaving C early
        self.discrim_playing = False
        self.current_stage = None # Keep track of stages so some asynchronous callbacks know when it's their turn
        self.bailed = 0

        # We make a list of the variables that need to be reset each trial so it's easier to do so
        self.resetting_variables = [self.response, self.last_pin,
                                    self.bailed]

        # This allows us to cycle through the task by just repeatedly calling self.stages.next()
        stage_list = [self.request, self.discrim, self.reinforcement]
        self.num_stages = len(stage_list)
        self.stages = itertools.cycle(stage_list)

        # Initialize hardware
        # TODO: class subtypes with different hardware
        self.pins = {}
        self.pin_id = {} # Take pin numbers back to letters
        self.init_hardware()

        # Load sounds
        #self.init_pyo()
        self.sounds       = {}
        self.sound_lookup = {}
        self.load_sounds()

    def init_hardware(self):
        # We use the HARDWARE dict that specifies what we need to run the task
        # alongside the PINS subdict in the prefs structure to tell us how they're plugged in to the pi
        self.pins = {}
        self.pin_id = {} # Reverse dict to identify pokes
        pin_numbers = self.prefs['PINS']

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
                        # If center port, add an additional callback for when something leaves it
                        # TODO: Disabling for now, make with a bounce time
                        #if pin == 'C':
                        #    self.pins[type][pin].assign_cb(self.center_out, manual_trigger='U', add=True)
                    except:
                        # TODO: More informative exception
                        Exception('Something went wrong instantiating pins, tell jonny to handle this better!')

            # Then LEDs
            elif type == 'LEDS':
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

    def load_sounds(self):
        # TODO: Definitely put this in a metaclass

        # Iterate through sounds and load them to memory
        for k, v in self.soundict.items():
            # If multiple sounds on one side, v will be a list
            if isinstance(v, list):
                self.sounds[k] = []
                for sound in v:
                    if sound['type'] in ['File', 'Speech']:
                        # prepend sounddir
                        sound['path'] = os.path.join(self.prefs['SOUNDDIR'], sound['path'])
                    # We send the dict 'sound' to the function specified by 'type' and 'SOUND_LIST' as kwargs
                    self.sounds[k].append(sounds.SOUND_LIST[sound['type']](**sound))
                    # Then give the sound a callback to mark when it's finished
                    self.sounds[k][-1].set_trigger(self.stim_end)
            # If not a list, a single sound
            else:
                if v['type'] in ['File', 'Speech']:
                    # prepend sounddir
                    v['path'] = os.path.join(self.prefs['SOUNDDIR'], v['path'])
                self.sounds[k] = sounds.SOUND_LIST[v['type']](**v)
                self.sounds[k].set_trigger(self.stim_end)

        # If we want a punishment sound...
        if self.punish_sound:
            self.sounds['punish'] = sounds.Noise(self.punish_dur)
            #change_to_green = lambda: self.pins['LEDS']['C'].set_color([0, 255, 0])
            #self.sounds['punish'].set_trigger(change_to_green)

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

        if pin == 'TIMEUP':
            # TODO: Handle timers, reset trial
            # TODO: Handle bailing, for example by replacing the cycle with a single function that returns the 'bail' flag
            return

        self.last_pin = pin
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

    def center_out(self, pin, level, tick):
        # Called when something leaves the center pin,
        # We use this to handle the mouse leaving the port early
        if self.discrim_playing:
            self.bail_trial()

    def mark_playing(self):
        self.discrim_playing = True



    ##################################################################################
    # Stage Functions
    ##################################################################################
    def request(self,*args,**kwargs):
        # Set the event lock
        self.stage_block.clear()

        # Reset all the variables that need to be
        for v in self.resetting_variables:
            v = None

        self.triggers = {}

        if not self.sounds:
            raise RuntimeError('\nSound objects have not been passed! Make sure RPilot makes sounds from the soundict before running.')
        if self.punish_sound and ('punish' not in self.sounds.keys()):
            warnings.warn('No Punishment Sound defined.')

        # Set bias threshold
        if self.bias_mode == 0:
            randthresh = 0.5
        elif self.bias_mode == 1:
            randthresh = 0.5 + self.bias
        else:
            randthresh = 0.5
            warnings.warn("bias_mode is not defined or defined incorrectly")

        # Decide if correction trial (repeat last stim) or choose new target/stim
        if (self.correction is True) and (self.target is not None):
            # if the last trial wasn't a correction trial, we spin to see if this one will be
            if (self.last_was_correction is False) and (self.correct == 0) and (random.random() < self.pct_correction):
                # do nothing, repeat last stim
                self.correction_trial = True
                self.last_was_correction = True
            elif (self.last_was_correction is True) and (self.correction_trial is True):
                # otherwise if we were in a correction trial and haven't corrected, keep going
                pass
            elif (self.last_was_correction is True) and (self.correction_trial is False):
                # otherwise if we just corrected we switch the flag and choose randomly
                self.last_was_correction = False
                if random.random() > randthresh:
                    self.target = 'R'
                    self.target_sound = random.choice(self.sounds['R'])
                    self.distractor = 'L'
                else:
                    self.target = 'L'
                    self.target_sound = random.choice(self.sounds['L'])
                    self.distractor = 'R'
            else:
                # if it's just a normal trial, randomly select
                if random.random() > randthresh:
                    self.target = 'R'
                    self.target_sound = random.choice(self.sounds['R'])
                    self.distractor = 'L'
                else:
                    self.target = 'L'
                    self.target_sound = random.choice(self.sounds['L'])
                    self.distractor = 'R'

        else:
            # if correction trials are turned off, just randomly select
            # Choose target side and sound
            if random.random() > randthresh:
                self.target = 'R'
                self.target_sound = random.choice(self.sounds['R'])
                self.distractor = 'L'
            else:
                self.target = 'L'
                self.target_sound = random.choice(self.sounds['L'])
                self.distractor = 'R'



        # Attempt to identify target sound
        #TODO: Implement sound ID's better
        #try:
        #    self.target_sound_id = self.target_sound.id
        #except AttributeError:
        #    warnings.warn("Sound ID not defined! Sounds cannot be uniquely identified!")
        #    self.target_sound_id = None

        # Set sound trigger and LEDs
        # We make two triggers to play the sound and change the light color
        change_to_blue = lambda: self.pins['LEDS']['C'].set_color([0,0,255])

        # set triggers
        if self.req_reward is True:
            self.triggers['C'] = [change_to_blue, self.mark_playing, self.pins['PORTS']['C'].open, self.target_sound.play]
        else:
            self.triggers['C'] = [change_to_blue, self.mark_playing, self.target_sound.play]
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
        sound_info = {k:getattr(self.target_sound, k) for k in self.target_sound.PARAMS}
        data.update(sound_info)
        data.update({'type':self.target_sound.type})

        self.current_stage = 0
        return data

    def discrim(self,*args,**kwargs):
        self.stage_block.clear()

        self.triggers[self.target] = [lambda: self.respond(self.target), self.pins['PORTS'][self.target].open]
        #self.triggers[self.target] = self.test_correct
        self.triggers[self.distractor] = [lambda: self.respond(self.distractor), self.punish]

        # TODO: Handle timeout

        # Only data is the timestamp
        # TODO: Timestamps are fucked up here, should shift down a stage
        data = {'DC_timestamp': datetime.datetime.now().isoformat(),
                'trial_num': self.current_trial}
        self.current_stage = 1
        return data

    def reinforcement(self,*args,**kwargs):
        # We do NOT clear the task event flag here because we want
        # the pi to call the next stage immediately
        # We are just filling in the last data
        # and performing any calculations we need for the next trial
        if self.bailed:
            self.bailed = 0
            data = {
                'bailed':1,
                'trial_num': self.current_trial,
                'TRIAL_END':True
            }
            return data

        #self.response = self.last_pin

        if self.response == self.target:
            self.correct = 1
        else:
            self.correct = 0

        if self.correct == 1:
            self.correction_trial = False

        if self.bias_mode == 1:
            # TODO: Take window length from terminal preferences
            # TODO: Implement other bias modes
            # Use a "running average" of responses to control bias. Rather than computing the bias each time from
            # a list of responses, we just update a float weighted with the inverse of the "window size"
            # Sign is arbitrary, but make sure it corresponds to the inequality that assigns targets in request()!
            # The window_size is multiplied by two so our values stay between -0.5 and 0.5 rather than -1 and 1
            # That way, when added to the default 0.5 chance of selecting a side, we are bounded between -1 and 1
            window_size = float(50)*2
            if self.response == 'L':
                self.bias = max(self.bias-(1/window_size),-0.5)
            elif self.response == 'R':
                self.bias = min(self.bias+(1/window_size),0.5)

        data = {
            'response':self.response,
            'correct':self.correct,
            'bias':self.bias,
            'bailed':0,
            'trial_num': self.current_trial,
            'TRIAL_END':True
        }
        self.current_stage = 2
        return data

    def test_correct(self):
        print('correct!')

    def respond(self, pin):
        self.response = pin
        # test

    def punish(self):
        # TODO: If we're not in the last stage (eg. we were timed out after stim presentation), reset stages
        self.punish_block.clear()
        threading.Timer(self.punish_dur / 1000., self.punish_block.set).start()
        if self.punish_sound and ('punish' in self.sounds.keys()):
            self.sounds['punish'].play()
        # TODO: Ask for whether we should flash or not and either .set_leds() or flash_leds()
        #self.set_leds()
        self.flash_leds()



    def stim_end(self):
        # Called by the discrim sound's table trigger when playback is finished
        # Used in punishing leaving early
        self.discrim_playing = False
        if not self.bailed and self.current_stage == 1:
            self.set_leds({'L':[0,255,0], 'R':[0,255,0]})


    def bail_trial(self):
        # If a timer ends or the mouse pulls out too soon, we punish and bail
        self.bailed = 1
        self.triggers = {}
        self.punish()
        self.stage_block.set()

    def reset_stages(self):
        """
        Remake stages to reset cycle
        """

        self.stages = itertools.cycle(enumerate([self.request, self.discrim, self.reinforcement]))

    def clear_triggers(self):
        for pin in self.pins.values():
            pin.clear_cb()

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

    def flash_leds(self):
        for k, v in self.pins['LEDS'].items():
            v.flash(self.punish_dur)

    def end(self):
        for k, v in self.pins.items():
            for pin, obj in v.items():
                if k == "LEDS":
                    obj.set_color([0,0,0])
                obj.release()


class Gap_2AFC(Nafc):
    def __init__(self, **kwargs):

        super(Gap_2AFC, self).__init__(**kwargs)


    def load_sounds(self):
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
        pass

    def stim_end(self):
        # Called by the discrim sound's table trigger when playback is finished
        # Used in punishing leaving early

        self.set_leds({'L':[0,255,0], 'R':[0,255,0]})

    def request(self,*args,**kwargs):
        # Set the event lock
        self.stage_block.clear()

        # Reset all the variables that need to be
        for v in self.resetting_variables:
            v = None

        self.triggers = {}

        if not self.sounds:
            raise RuntimeError('\nSound objects have not been passed! Make sure RPilot makes sounds from the soundict before running.')
        if self.punish_sound and ('punish' not in self.sounds.keys()):
            warnings.warn('No Punishment Sound defined.')

        # Set bias threshold
        if self.bias_mode == 0:
            randthresh = 0.5
        elif self.bias_mode == 1:
            randthresh = 0.5 + self.bias
        else:
            randthresh = 0.5
            warnings.warn("bias_mode is not defined or defined incorrectly")

        # Decide if correction trial (repeat last stim) or choose new target/stim
        if (self.correction is True) and (self.target is not None):
            # if the last trial wasn't a correction trial, we spin to see if this one will be
            if (self.last_was_correction is False) and (self.correct == 0) and (random.random() < self.pct_correction):
                # do nothing, repeat last stim
                self.correction_trial = True
                self.last_was_correction = True
            elif (self.last_was_correction is True) and (self.correction_trial is True):
                # otherwise if we were in a correction trial and haven't corrected, keep going
                pass
            elif (self.last_was_correction is True) and (self.correction_trial is False):
                # otherwise if we just corrected we switch the flag and choose randomly
                self.last_was_correction = False
                if random.random() > randthresh:
                    self.target = 'R'
                    self.target_sound = random.choice(self.sounds['R'])
                    self.distractor = 'L'
                else:
                    self.target = 'L'
                    self.target_sound = random.choice(self.sounds['L'])
                    self.distractor = 'R'
            else:
                # if it's just a normal trial, randomly select
                if random.random() > randthresh:
                    self.target = 'R'
                    self.target_sound = random.choice(self.sounds['R'])
                    self.distractor = 'L'
                else:
                    self.target = 'L'
                    self.target_sound = random.choice(self.sounds['L'])
                    self.distractor = 'R'

        else:
            # if correction trials are turned off, just randomly select
            # Choose target side and sound
            if random.random() > randthresh:
                self.target = 'R'
                self.target_sound = random.choice(self.sounds['R'])
                self.distractor = 'L'
            else:
                self.target = 'L'
                self.target_sound = random.choice(self.sounds['L'])
                self.distractor = 'R'



        # Attempt to identify target sound
        #TODO: Implement sound ID's better
        #try:
        #    self.target_sound_id = self.target_sound.id
        #except AttributeError:
        #    warnings.warn("Sound ID not defined! Sounds cannot be uniquely identified!")
        #    self.target_sound_id = None

        # Set sound trigger and LEDs
        # We make two triggers to play the sound and change the light color
        change_to_blue = lambda: self.pins['LEDS']['C'].set_color([0,0,255])

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







#################################################################################################
# Prebuilt Parameter Sets


FREQ_DISCRIM = {
    'description':'Pure_Tone_Discrimination',
    'sounds':{
        'L': {'type':'tone','frequency':500, 'duration':500,'amplitude':.1},
        'R': {'type':'tone','frequency':2000,'duration':500,'amplitude':.1}
    },
    'reward':50,
    'punish':2000,
    'pct_correction':0.5,
    'bias_mode':1
}

FREQ_DISCRIM_TEST = {
    'description':'Pure_Tone_Discrimination',
    'sounds':{
        'L': [{'type':'tone','frequency':500, 'duration':500,'amplitude':.3,'id':'L1'},
             {'type':'tone','frequency':700, 'duration':500,'amplitude':.3,'id':'L2'}],
        'R': {'type':'tone','frequency':2000,'duration':500,'amplitude':.3,'id':'R1'},
        'punish':{'type':'noise','duration':500,'amplitude':0.3,'id':'punish'}
    },
    'reward':[50,60,70],
    'punish':2000,
    'pct_correction':0.5,
    'bias_mode':1
}

SOUND_TEST = {
    'L': [{'type': 'tone', 'frequency': 500, 'duration': 500, 'amplitude': .1},
          {'type': 'tone', 'frequency': 700, 'duration': 500, 'amplitude': .1}],
    'R': {'type': 'tone', 'frequency': 2000, 'duration': 500, 'amplitude': .1}
}

# Dict of templates for GUI
TEMPLATES = {'Frequency Discrimination':FREQ_DISCRIM,
             'Sound Test':SOUND_TEST}








