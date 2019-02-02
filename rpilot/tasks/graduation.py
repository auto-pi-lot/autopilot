# graduation criteria
from collections import deque
import numpy as np
from itertools import count

class Graduation(object):
    PARAMS = []
    COLS = []

    def update(self, row):
        Exception('The update method was not redefined by the subclass!')


class Accuracy(Graduation):
    # TODO: Get the corrects that we need
    PARAMS = ['threshold', 'window']
    COLS = ['correct']

    def __init__(self, threshold=0.75, window=500, **kwargs):
        """
        Args:
            threshold:
            window:
            **kwargs:
        """
        #super(Accuracy, self).__init__()
        self.threshold = float(threshold)
        self.window    = int(window)

        self.corrects = deque(maxlen=self.window)

        if 'correct' in kwargs.keys():
            # don't need to trim, dqs take the last values already
            self.corrects.extend(kwargs['correct'])



    def update(self, row):
        """
        Args:
            row:
        """
        try:
            self.corrects.append(int(row['correct']))
        except KeyError:
            Warning("key 'correct' not found in trial_row")
            return False

        if len(self.corrects)<self.window:
            return False

        if np.mean(self.corrects)>self.threshold:
            return True
        else:
            return False


class NTrials(Graduation):
    """graduate after doing n trials"""
    PARAMS = ['n_trials', 'current_trial']

    def __init__(self, n_trials, current_trial=0, **kwargs):
        # type: (unicode, unicode, object) -> None
        """
        Args:
            n_trials:
            current_trial:
            **kwargs:
        """
        #super(NTrials, self).__init__()

        self.n_trials = int(n_trials)
        self.counter = count(start=int(current_trial))

    def update(self, row):
        """
        Args:
            row:
        """
        trials = self.counter.next()
        if trials >= self.n_trials:
            return True
        else:
            return False




GRAD_LIST = {
    'accuracy': Accuracy,
    'n_trials': NTrials
}