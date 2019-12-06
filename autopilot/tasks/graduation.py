"""
Object that implement Graduation criteria to move between
different tasks in a protocol.
"""

from collections import deque
import numpy as np
from itertools import count

class Graduation(object):
    """
    Base Graduation object.

    All Graduation objects need to populate PARAMS, COLS, and define an
    `update` method.

    """
    PARAMS = []
    """
    list: list of parameters to be defined
    """

    COLS = []
    """
    list: list of any data columns that this object should be given.
    """

    def update(self, row):
        """
        Args:
            :class:`~tables.tableextension.Row` : Trial row
        """
        Exception('The update method was not redefined by the subclass!')


class Accuracy(Graduation):
    """
    Graduate stage based on percent accuracy over some window of trials.
    """

    PARAMS = ['threshold', 'window']
    COLS = ['correct']

    def __init__(self, threshold=0.75, window=500, **kwargs):
        """
        Args:
            threshold (float): Accuracy above this threshold triggers graduation
            window (int):  number of trials to consider in the past.
            **kwargs: should have 'correct' corresponding to the corrects/incorrects of the past.
        """
        #super(Accuracy, self).__init__()
        self.threshold = float(threshold)
        self.window    = int(window)

        self.corrects = deque(maxlen=self.window)

        if 'correct' in kwargs.keys():
            # don't need to trim, dqs take the last values already
            self.corrects.extend(kwargs['correct'])
        else:
            Warning("correct column not given")



    def update(self, row):
        """
        Get 'correct' from the row object. If this trial puts us over the
        threshold, return True, else False.

        Args:
            row (:class:`~tables.tableextension.Row`) : Trial row

        Returns:
            bool: Did we graduate this time or not?
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
    """
    Graduate after doing n trials

    Attributes:
        counter (:class:`itertools.count`): Counts the trials.
    """
    PARAMS = ['n_trials', 'current_trial']

    def __init__(self, n_trials, current_trial=0, **kwargs):
        """
        Args:
            n_trials (int): Number of trials to graduate after
            current_trial (int): If not starting from zero, start from here
            **kwargs:
        """
        #super(NTrials, self).__init__()

        self.n_trials = int(n_trials)
        self.counter = count(start=int(current_trial))

    def update(self, row):
        """
        If we're past n_trials in this trial, return True, else False.

        Args:
            row: ignored

        Returns:
            bool: Did we graduate or not?
        """
        if 'trial_num' in row:
            trials = row['trial_num']
            # be robust -- if we're using information from the trial row,
            # make sure our internal model is kept up to date
            # counter's don't have a good way of changing their n,
            # so we just remake it
            try:
                self.counter = count(int(trials))
            except:
                # TODO: Logging here
                pass
        else:
            trials = next(self.counter)

        if trials >= self.n_trials:
            return True
        else:
            return False




GRAD_LIST = {
    'accuracy': Accuracy,
    'n_trials': NTrials
}
"""
Mapping from string reference of graduation type to object.
"""