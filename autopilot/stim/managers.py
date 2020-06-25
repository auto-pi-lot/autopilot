"""
This is a scrappy first draft of a stimulus manager that will be built out
to incorporate arbitrary stimulus logic. For now you can subclass `Stim_Manager` and
redefine `next_stim`

TODO:
    Make this more general, for more than just sounds.
"""

import os
import pdb
from collections import deque
import numpy as np
from autopilot import prefs
if prefs.AGENT.upper() == 'PILOT':
    if 'AUDIO' in prefs.CONFIG:
        from autopilot.stim.sound import sounds
        # TODO be loud about trying to init sounds when not in config

def init_manager(stim):
    if 'manager' in stim.keys():
        if stim['manager'] in MANAGER_MAP.keys():
            manager = stim['manager']
            return MANAGER_MAP[manager](stim)
        else:
            Exception('Couldnt find stim manager of type: {}'.format(stim['type']))
    else:
        return Stim_Manager(stim)


class Stim_Manager(object):
    """
    Yield sounds according to some set of rules.

    Currently implemented:

    * correction trials - If a subject continually answers to one side incorrectly, keep
        the correct answer on the other side until they answer in that direction
    * bias correction - above some bias threshold, skew the correct answers to the less-responded side

    Attributes:
        stimuli (dict): Dictionary of instantiated stimuli like::

            {'L': [Tone1, Tone2, ...], 'R': [Tone3, Tone4, ...]}

        target ('L', 'R'): What is the correct port?
        distractor ('L', 'R'): What is the incorrect port?
        response ('L', 'R'): What was the last response?
        correct (0, 1): Was the last response correct?
        last_stim: What was the last stim? (one of `self.stimuli`)
        correction (bool): Are we doing correction trials?
        correction_trial (bool): Is this a correction trial?
        last_was_correction (bool): Was the last trial a correction trial?
        correction_pct (float): proportion of trials that are correction trials
        bias: False, or a bias correction mode.

    """

    # Metaclass for managing stimuli...
    def __init__(self, stim=None):
        """
        Args:
            stim (dict): Dictionary describing sound stimuli, in a format like::

                {
                'L': [{'type':'tone',...},{...}],
                'R': [{'type':'tone',...},{...}]
                }
        """
        self.stimuli = {}

        self.target = None  # What is the correct port?
        self.distractor = None  # What is the incorrect port
        self.response = None  # What was the last response?
        self.correct = 0  # Was the last response correct?
        self.last_stim = None  # What was the last stim?

        # Correction trials

        self.correction = False  # Are we doing correction trials
        self.correction_trial = False  # Is this a correction trial?
        self.last_was_correction = False  # Was the last trial a correction trial?
        self.correction_pct = 0.1  # proportion of trials that are correction trials

        # Bias correction
        self.bias = False  # or a bias correction mode

        # if we're being init'd as a superclass, no stim passed.
        if stim:

            # if we're doing sounds init them here
            # TODO: Make SoundManger subclass
            if 'sounds' in stim.keys():
                self.init_sounds(stim['sounds'])

    def do_correction(self, correction_pct = 0.5):
        """
        Called to set correction trials to True and correction percent.

        Args:
            correction_pct (float): Proportion of trials that should randomly be set to be correction trials.
        """
        self.correction = True
        self.correction_pct = correction_pct

    def do_bias(self, **kwargs):
        """
        Instantiate a :class:`.Bias_Correction` module

        Args:
            kwargs: parameters to initialize :class:`.Bias_Correction` with.
        """
        self.bias = Bias_Correction(**kwargs)

    def init_sounds(self, sound_dict):
        """
        Instantiate sound objects, using the 'type' value to choose an object from
        :data:`.sounds.SOUND_LIST` .

        Args:
            sound_dict (dict): a dictionary like::
                {
                'L': [{'type':'tone',...},{...}],
                'R': [{'type':'tone',...},{...}]
                }
        """
        # sounds should be
        # Iterate through sounds and load them to memory
        for k, v in sound_dict.items():
            # If multiple sounds on one side, v will be a list
            if isinstance(v, list):
                self.stimuli[k] = []
                for sound in v:
                    # We send the dict 'sound' to the function specified by 'type' and '
                    # ' as kwargs
                    self.stimuli[k].append(sounds.SOUND_LIST[sound['type']](**sound))
            # If not a list, a single sound
            else:
                self.stimuli[k] = [sounds.SOUND_LIST[v['type']](**v)]

    def set_triggers(self, trig_fn):
        """
        Give a callback function to all of our stimuli for when the stimulus ends.

        Note:
            Stimuli need a `set_trigger` method.

        Args:
            trig_fn (callable): A function to be given to stimuli via `set_trigger`
        """
        # set a callback function for when the stimulus ends
        for k, v in self.stimuli.items():
            for astim in v:
                astim.set_trigger(trig_fn)

    def make_punishment(self, type, duration):
        """
        Warning:
            Not Implemented

        Args:
            type:
            duration:
        """
        # types: timeout, noise
        # If we want a punishment sound...
        # if self.punish_sound:
        #     self.stimuli['punish'] = sounds.Noise(self.punish_dur)
        #     #change_to_green = lambda: self.hardware['LEDS']['C'].set_color([0, 255, 0])
        #     #self.stimuli['punish'].set_trigger(change_to_green)
        pass

    def play_punishment(self):
        """
        Warning:
            Not Implemented
        """
        pass

    def next_stim(self):
        """
        Compute and return the next stimulus

        If we are doing correction trials, compute that.

        Same thing with bias correction.

        Otherwise, randomly select a stimulus to present.

        Returns:
            ('L'/'R' Target, 'L'/'R' distractor, Stimulus to present)
        """
        # compute and return the next stim

        # first: if we're doing correction trials, compute that
        if self.correction:
            self.correction_trial = self.compute_correction()
            if self.correction_trial:
                return self.target, self.distractor, self.last_stim

        # otherwise we check for bias correction
        # it will return a threshold for random choice
        if self.bias:
            threshold = self.bias.next_bias()
        else:
            threshold = 0.5

        if np.random.rand()<threshold:
            self.target = 'L'
        else:
            self.target = 'R'

        if self.target == 'L':
            self.distractor = 'R'
        elif self.target == 'R':
            self.distractor = 'L'

        self.last_stim = np.random.choice(self.stimuli[self.target])

        return self.target, self.distractor, self.last_stim

    def compute_correction(self):
        """
        If `self.correction` is true, compute correction trial logic during
        `next_stim`.

        * If the last trial was a correction trial and the response to it wasn't correct, return True
        * If the last trial was a correction trial and the response was correct, return False
        * If the last trial as not a correction trial, but a randomly generated float is less than `correction_pct`, return True.

        Returns:
            bool: whether this trial should be a correction trial.

        """
        # if we are doing a correction trial this time return true

        # if this is the first trial, we can't do correction trials now can we
        if self.target is None:
            return False

        # if the last trial was a correction trial and we didn't get it correct,
        # then this is a correction trial too
        if (self.correction_trial or self.last_was_correction) and not self.correct:
            return True
        # if the last trial was a correction trial and we just corrected, no correction trial this time
        elif (self.correction_trial or self.last_was_correction) and self.correct:
            self.last_was_correction = False
            return False
        # if last trial was not a correction trial we spin  *to test* for one
        elif np.random.rand() < self.correction_pct:
            self.last_was_correction = True
            return False
        else:
            return False

    def update(self, response, correct):
        """
        At the end of a trial, update the status of our internal variables
        with the outcome of the trial.

        Args:
            response ('L', 'R'): How the subject responded
            correct (0, 1): Whether the response was correct.
        """
        self.response = response
        self.correct = correct
        if self.bias:
            self.bias.update(response, self.target)

    def end(self):
        """
        End all of our stim. Stim should have an `.end()` method of their own

        """

        for side, v in self.stimuli.items():
            for stim in v:
                try:
                    stim.end()
                except AttributeError:
                    print('stim does not have an end method! \n{}'.format(str(stim)))

class Proportional(Stim_Manager):
    """
    Present groups of stimuli with a particular frequency.

    Frequencies do not need to add up to 1, groups will be selected with the frequency
    (frequency)/(sum(frequencies)).

    Arguments:
        stim (dict): Dictionary with the structure::

            {'manager': 'proportional',
             'type': 'sounds',
             'groups': (
                 {'name':'group_name',
                  'frequency': 0.2,
                  'sounds':{
                      'L': [{Tone1_params}, {Tone2_params}...],
                      'R': [{Tone3_params}, {Tone4_params}...]
                  }
                },
                {'name':'second_group',
                  'frequency': 0.8,
                  'sounds':{
                      'L': [{Tone1_params}, {Tone2_params}...],
                      'R': [{Tone3_params}, {Tone4_params}...]
                  }
                })
            }

    Attributes:
        stimuli (dict): A dictionary of stimuli organized into groups
        groups (dict): A dictionary mapping group names to frequencies

    """

    def __init__(self, stim):
        super(Proportional, self).__init__()

        self.stimuli = {}

        self.frequency_type = None

        if stim['type'] == 'sounds':
            if 'groups' in stim.keys():
                self.frequency_type = "within_groups"
                # top-level groups, choose group then choose side
                self.init_sounds_grouped(stim['groups'])
                self.store_groups(stim)
            else:
                self.frequency_type = "within_side"
                # second-level frequencies, side is chosen and then
                # probability from within a side
                self.init_sounds_individual(stim['sounds'])



    def init_sounds_grouped(self, sound_stim):
        """
        Instantiate sound objects similarly to :class:`.Stim_Manager`, just organizes them into groups.

        Args:
            sound_stim (tuple, list): an iterator like::
                (
                 {'name':'group_name',
                  'frequency': 0.2,
                  'sounds': {
                      'L': [{Tone1_params}, {Tone2_params}...],
                      'R': [{Tone3_params}, {Tone4_params}...]
                    }
                },
                {'name':'second_group',
                  'frequency': 0.8,
                  'sounds':{
                      'L': [{Tone1_params}, {Tone2_params}...],
                      'R': [{Tone3_params}, {Tone4_params}...]
                  }
                })
        """
        # Iterate through sounds and load them to memory
        self.stimuli = {}

        if isinstance(sound_stim, tuple) or isinstance(sound_stim, list):
            for group in sound_stim:
                group_name = group['name']

                # instantiate sounds
                self.stimuli[group_name] = {}
                for k, v in group['sounds'].items():
                    if isinstance(v, list):
                        self.stimuli[group_name][k] = []
                        for sound in v:
                            # We send the dict 'sound' to the function specified by 'type' and '
                            # ' as kwargs
                            self.stimuli[group_name][k].append(sounds.SOUND_LIST[sound['type']](**sound))
                    # If not a list, a single sound
                    else:
                        self.stimuli[group_name][k] = [sounds.SOUND_LIST[v['type']](**v)]


    def init_sounds_individual(self, sound_stim):
        """
        Initialize sounds with individually set presentation frequencies.

        .. todo::

            This method reflects the need for managers to have a unified schema,
            which will be built in a future release of Autopilot.

        Args:
            sound_stim (dict): Dictionary of {'side':[sound_params]} to generate sound stimuli

        Returns:

        """
        self.stim_freqs = {}
        for side, sound_params in sound_stim.items():
            self.stimuli[side] = []
            self.stim_freqs[side] = []
            if isinstance(sound_params, list):
                for sound in sound_params:
                    self.stimuli[side].append(sounds.SOUND_LIST[sound['type']](**sound))
                    self.stim_freqs[side].append(float(sound['management']['frequency']))
            else:
                self.stimuli[side].append(sounds.SOUND_LIST[sound_params['type']](**sound_params))
                self.stim_freqs[side].append(float(sound_params['management']['frequency']))

        # normalize frequencies within sides to sum to 1
        for side, freqs in self.stim_freqs.items():
            side_sum = np.sum(freqs)
            self.stim_freqs[side] = tuple([float(f)/side_sum for f in freqs])

    def store_groups(self, stim):
        """
        store groups and frequencies
        """
        self.groups = {}
        # also store (later) as tuples for choice b/c dicts are unordered
        group_names = []
        group_freqs = []
        for group in stim['groups']:
            group_name = group['name']
            frequency = float(group['frequency'])
            self.groups[group_name] = frequency
            group_names.append(group_name)
            group_freqs.append(frequency)

        self.group_names = tuple(group_names)
        group_freqs = np.array(group_freqs).astype(np.float)
        group_freqs = group_freqs/np.sum(group_freqs)

        self.group_freqs = tuple(group_freqs)



    def set_triggers(self, trig_fn):
        """
        Give a callback function to all of our stimuli for when the stimulus ends.

        Note:
            Stimuli need a `set_trigger` method.

        Args:
            trig_fn (callable): A function to be given to stimuli via `set_trigger`
        """
        # set a callback function for when the stimulus ends

        if self.frequency_type == "within_group":
            for _, group in self.stimuli.items():
                    for _, v in group.items():
                        for astim in v:
                            astim.set_trigger(trig_fn)
        elif self.frequency_type == "within_side":
            for side, sound_group in self.stimuli.items():
                for astim in sound_group:
                    astim.set_trigger(trig_fn)

        else:
            ValueError('Dont know how to set triggers')


    def next_stim(self):
        """
        Compute and return the next stimulus

        If we are doing correction trials, compute that.

        Same thing with bias correction.

        Otherwise, randomly select a stimulus to present, weighted by its group frequency.

        Returns:
            ('L'/'R' Target, 'L'/'R' distractor, Stimulus to present)
        """
        # compute and return the next stim

        # first: if we're doing correction trials, compute that
        if self.correction:
            self.correction_trial = self.compute_correction()
            if self.correction_trial:
                return self.target, self.distractor, self.last_stim

        # otherwise we check for bias correction
        # it will return a threshold for random choice
        if self.bias:
            threshold = self.bias.next_bias()
        else:
            threshold = 0.5

        # choose side
        if np.random.rand()<threshold:
            self.target = 'L'
        else:
            self.target = 'R'

        if self.target == 'L':
            self.distractor = 'R'
        elif self.target == 'R':
            self.distractor = 'L'

        if self.frequency_type == "within_group":

            # pick a stimulus based on group frequency
            group = np.random.choice(self.group_names, p=self.group_freqs)
            # within that group pick a random stimulus
            self.last_stim = np.random.choice(self.stimuli[group][self.target])

        elif self.frequency_type == "within_side":
            self.last_stim = np.random.choice(self.stimuli[self.target],
                                              p=self.stim_freqs[self.target])
        else:
            ValueError('Dont know what freq type we are')

        return self.target, self.distractor, self.last_stim





class Bias_Correction(object):
    """
    Basic Bias correction module. Modifies the threshold of random stimulus
    choice based on history of biased responses.

    Attributes:
        responses (:class:`collections.deque`): History of prior responses
        targets (:class:`collections.deque`): History of prior targets.
    """

    def __init__(self, mode='thresholded_linear', thresh=.2, window=100):
        """
        Args:
            mode: One of the following:

                * `'thresholded linear'` : above some threshold, do linear bias correction
                    eg. if response rate 65% left, make correct be right 65% of the time

            thresh (float): threshold above chance, ie. 0.2 means has to be 70% biased in window
            window (int): number of trials to calculate bias over
        """
        self.mode = mode
        self.threshold = float(thresh)
        self.window = int(window)
        self.responses = deque(maxlen=self.window)
        self.targets = deque(maxlen=self.window)

    def next_bias(self):
        """
        Compute the next bias depending on `self.mode`

        Returns:
            float: Some threshold :class:`.Stim_Manager` uses to decide left vs right.

        """

        # compute the bias threshold
        if self.mode == 'thresholded_linear':
            return self.thresholded_linear()

    def thresholded_linear(self):
        """
        If we are above the threshold, linearly correct the rate of
        presentation to favor the rarely responded side.

        eg. if response rate 65% left, make correct be right 65% of the time

        Returns:
            float: 0.5-bias, where bias is the difference between the mean response and mean target.
        """
        # if we are above threshold, return the bias
        bias = np.mean(self.responses)-np.mean(self.targets)
        if np.abs(bias)>self.threshold:
            return 0.5-bias
        else:
            return 0.5


    def update(self, response, target):
        """
        Store some new response and target values

        Args:
            response ('R', 'L'): Which side the subject responded to
            target ('R', 'L'): The correct side.
        """
        if isinstance(response, str):
            if response == "R":
                response = 1.0
            elif response == "L":
                response = 0.0

        if isinstance(target, str):
            if target == "R":
                target = 1.0
            elif target == "L":
                target = 0.0

        self.responses.append(float(response))
        self.targets.append(float(target))

MANAGER_MAP = {
    'proportional': Proportional
}





# class Reward_Manager(object):
#     def __init__(self):
#         pass
