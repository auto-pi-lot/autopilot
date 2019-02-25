"""
This is a scrappy first draft of a stimulus manager that will be built out
to incorporate arbitrary stimulus logic. For now you can subclass `Stim_Manager` and
redefine `next_stim`

TODO:
    Make this more general, for more than just sounds.
"""

import os
from collections import deque
import numpy as np
from rpilot.stim.sound import sounds


class Stim_Manager(object):
    """
    Yield sounds according to some set of rules.

    Currently implemented:

    * correction trials - If a mouse continually answers to one side incorrectly, keep
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
    def __init__(self, stim):
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
        self.correction_pct = 0.5  # proportion of trials that are correction trials

        # Bias correction
        self.bias = False  # or a bias correction mode

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
        #     #change_to_green = lambda: self.pins['LEDS']['C'].set_color([0, 255, 0])
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
        if self.correction_trial and not self.correct:
            return True
        # if the last trial was a correction trial and we just corrected, no correction trial this time
        elif self.correction_trial and self.correct:
            return False
        # if last trial was not a correction trial we spin for one
        elif np.random.rand() < self.correction_pct:
            return True
        else:
            return False

    def update(self, response, correct):
        """
        At the end of a trial, update the status of our internal variables
        with the outcome of the trial.

        Args:
            response ('L', 'R'): How the mouse responded
            correct (0, 1): Whether the response was correct.
        """
        self.response = response
        self.correct = correct
        if self.bias:
            self.bias.update(response, self.target)


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
            response ('R', 'L'): Which side the mouse responded to
            target ('R', 'L'): The correct side.
        """
        if isinstance(response, basestring):
            if response == "R":
                response = 1.0
            elif response == "L":
                response = 0.0

        if isinstance(target, basestring):
            if target == "R":
                target = 1.0
            elif target == "L":
                target = 0.0

        self.responses.append(float(response))
        self.targets.append(float(target))







# class Reward_Manager(object):
#     def __init__(self):
#         pass
