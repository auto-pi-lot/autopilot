# classes that yield sounds according to some rule
import prefs
import os
from collections import deque
import numpy as np



class Stim_Manager(object):
    """

    """
    stimuli = {}

    target = None # What is the correct port?
    distractor = None # What is the incorrect port
    response = None # What was the last response?
    correct = 0 # Was the last response correct?
    last_stim = None # What was the last stim?

    # Correction trials
    correction = False # Are we doing correction trials
    correction_trial = False # Is this a correction trial?
    last_was_correction = False # Was the last trial a correction trial?
    correction_pct = 0.5 # proportion of trials that are correction trials

    # Bias correction
    bias = False # or a bias correction mode

    # Metaclass for managing stimuli...
    def __init__(self, stim):
        # for now, only one type of stimulus at a time
        if 'sounds' in stim.keys():
            self.init_sounds(stim['sounds'])

    def do_correction(self, correction_pct = 0.5):
        """

        :param correction_pct:
        """
        self.correction = True
        self.correction_pct = correction_pct

    def do_bias(self, **kwargs):
        """

        :param kwargs:
        """
        self.bias = Bias_Correction(**kwargs)

    def init_sounds(self, sounds):
        """

        :param sounds:
        """
        # sounds should be a dictionary like...
        # {
        # 'L': [{'type':'tone',...},{...}],
        # 'R': [{'type':'tone',...},{...}]
        # }
        # Iterate through sounds and load them to memory
        for k, v in sounds.items():
            # If multiple sounds on one side, v will be a list
            if isinstance(v, list):
                self.stimuli[k] = []
                for sound in v:
                    # We send the dict 'sound' to the function specified by 'type' and 'SOUND_LIST' as kwargs
                    self.stimuli[k].append(sounds.SOUND_LIST[sound['type']](**sound))
            # If not a list, a single sound
            else:
                self.stimuli[k] = [sounds.SOUND_LIST[v['type']](**v)]

    def set_triggers(self, trig_fn):
        """

        :param trig_fn:
        """
        # set a callback function for when the stimulus ends
        for k, v in self.stimuli:
            for stim in v:
                stim.set_trigger(trig_fn)

    def make_punishment(self, type, duration):
        """

        :param type:
        :param duration:
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

        """
        pass

    def next(self):
        """

        :return:
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
            threshold = self.bias.next()
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

        :return:
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

        :param response:
        :param correct:
        """
        self.response = response
        self.correct = correct
        if self.bias:
            self.bias.update(response, self.target)










class Bias_Correction(object):
    """

    """
    def __init__(self, mode='thresholded_linear', thresh=.2, window=100):
        # thresholded linear: above some threshold, do linear bias correction
        # eg. if response rate 65% left, make correct be right 65% of the time
        # thresh - threshold above chance, ie. 0.2 means has to be 70% biased in window
        # window - number of trials to calculate bias over
        self.mode = mode
        self.threshold = float(thresh)
        self.window = int(window)
        self.responses = deque(maxlen=self.window)
        self.targets = deque(maxlen=self.window)

    def next(self):
        """

        :return:
        """
        # compute the bias threshold
        if self.mode == 'thresholded_linear':
            return self.thresholded_linear()

    def thresholded_linear(self):
        """

        :return:
        """
        # if we are above threshold, return the bias
        bias = np.mean(self.responses)-np.mean(self.targets)
        if np.abs(bias)>self.threshold:
            return 1.0-bias
        else:
            return 0.5


    def update(self, response, target):
        """

        :param response:
        :param target:
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







class Reward_Manager(object):
    """

    """
    def __init__(self):
        pass
