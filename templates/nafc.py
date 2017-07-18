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

import random
from taskontrol.settings import rpisettings as rpiset
import datetime
import itertools
import warnings
import tables

# This declaration allows Mouse to identify which class in this file contains the task class. Could also be done with __init__ but yno I didnt for no reason.
TASK = 'Nafc'

class Nafc:
    """
    Actually 2afc, but can't have number as first character of class.
    Template for 2afc tasks. Pass in a dict. of sounds & other parameters,
    """

    # Class attributes
    # for numpy data types see http://docs.scipy.org/doc/numpy/reference/arrays.dtypes.html#arrays-dtypes-constructing
    class DataTypes(tables.IsDescription):
        # This class allows the Mouse object to make a data table with the correct data types. You must update it for any new data you'd like to store
        trial_num = tables.Int32Col()
        target = tables.StringCol(1)
        target_sound_id = tables.StringCol(32) # FIXME need to do ids way smarter than this
        response = tables.StringCol(1)
        correct = tables.Int32Col()
        bias = tables.Float32Col()
        RQ_timestamp = tables.StringCol(26)
        DC_timestamp = tables.StringCol(26)
        bailed = tables.Int32Col()

    # List of needed params, returned data and data format.
    PARAM_LIST = ['sounds', 'reward', 'punish', 'pct_correction', 'bias_mode', 'timeout']
    DATA_LIST = {'trial_num':'i32','target':'S1','target_sound_id':'S32', 'response':'S1', 'correct':'i32', 'bias':'f32', 'RQ_timestamp':'S26','DC_timestamp':'S26','bailed':'i32'}

    def __init__(self, sounds, reward=50, punish=2000, pct_correction=.5, bias_mode=1, timeout=30000, assisted_assign=0, **kwargs):
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

        if assisted_assign:
            self.assisted_assign()
            return

        # Fixed parameters
        self.soundict = sounds # Sounds should always be soundicts on __init__
        self.reward = reward
        self.punish = punish
        self.pct_correction = pct_correction
        self.bias_mode = bias_mode
        self.stage_names = ["request","discrim","reinforcement"]
        self.timeout = timeout

        # Variable Parameters
        self.target = None
        self.target_sound = None
        self.target_sound_id = None
        self.distractor = None
        self.bias = float(0)
        self.response = None
        self.correct = None
        self.correction = None

        # Passed by RPilot after init
        self.sounds = None
        self.sound_lookup = None

        # This allows us to cycle through the task by just repeatedly calling self.stages.next()
        stage_list = [self.request,self.discrim,self.reinforcement]
        self.num_stages = len(stage_list)
        self.stages = itertools.cycle(enumerate(stage_list)) # Enumerate lets us get the number of the stage we're on.

        # TODO: Probably some error checking around here.



    ##################################################################################
    # Stage Functions
    ##################################################################################
    def request(self,*args,**kwargs):

        if not self.sounds:
            raise RuntimeError('\nSound objects have not been passed! Make sure RPilot makes sounds from the soundict before running.')
        if 'punish' not in self.sounds.keys():
            warnings.warn('No Punishment Sound defined.')

        # Set bias threshold
        if self.bias_mode == 0:
            randthresh = 0.5
        elif self.bias_mode ==1:
            randthresh = 0.5 + self.bias
        else:
            randthresh = 0.5
            warnings.warn("bias_mode is not defined or defined incorrectly")

        # Decide if correction trial (repeat last stim) or choose new target/stim
        if (random.random() > self.pct_correction) or (self.target == None):
            # Choose target side and sound
            self.correction = 0
            if random.random() > randthresh:
                self.target = 'R'
                self.target_sound = random.choice(self.sounds['R'])
                self.distractor = 'L'
            else:
                self.target = 'L'
                self.target_sound = random.choice(self.sounds['L'])
                self.distractor = 'R'
        else:
            self.correction = 1
            # No need to define the rest, just keep it from the last trial.


        # Attempt to identify target sound
        try:
            self.target_sound_id = self.target_sound.id
        except AttributeError:
            warnings.warn("Sound ID not defined! Sounds cannot be uniquely identified!")
            self.target_sound_id = None

        data = {
            'target':self.target,
            'target_sound_id':self.target_sound_id,
            'RQ_timestamp':datetime.datetime.now().isoformat()
        }
        triggers = {
            'C':self.target_sound.out
        }
        timers = {
            'inf':None
        }
        return data,triggers,timers

    def discrim(self,*args,**kwargs):

        # Only data is the timestamp
        data = {'DC_timestamp': datetime.datetime.now().isoformat()}

        try:
            triggers = {
                self.target:{'reward':self.reward},
                self.distractor:{'punish':self.punish,'sound':self.sounds['punish'].out}
            }
        except KeyError:
            # If we get a KeyError it's probably because we don't have a punish_sound
            triggers = {
                self.target:{'reward':self.reward},
                self.distractor:{'punish':self.punish}
            }

        timers = {
            'timeout':{'duration':self.timeout,'sound':self.sounds['punish'].out}
        }

        return data,triggers,timers

    def reinforcement(self,pin,*args,**kwargs):
        # pin passed from callback function as string version ('L', 'C', etc.)
        self.response = pin
        if self.response == self.target:
            self.correct = 1
        else:
            self.correct = 0

        if self.bias_mode == 1:
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
            'bailed':0
        }
        triggers = {
            'task_end':None
        }
        timers = {
            None:None # Next trial is called by RPilot automatically at last stage.
        }
        return data, triggers, timers
        # Also calc ongoing vals. like bias.

    def reset_stages(self):
        """
        Remake stages to reset cycle
        """

        self.stages = itertools.cycle(enumerate([self.request, self.discrim, self.reinforcement]))

    def assisted_assign(self):
        # This should actually be just a way to send the param_list to terminal
        # for param in self.param_list: ...
        # TODO Implement this as a generic template function: ask for params in the param list.
        pass




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










