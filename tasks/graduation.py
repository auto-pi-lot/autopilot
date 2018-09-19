# graduation criteria
from collections import deque
import numpy as np
from itertools import count


class Accuracy(object):
    PARAMS = ['threshold', 'window']
    def __init__(self, threshold=0.75, window=500., **kwargs):
        self.threshold = float(threshold)
        self.window    = int(window)

        self.corrects = deque(maxlen=window)


    def update(self, row):
        if 'correct' in row.keys():
            self.corrects.append(int(row['correct']))
        else:
            return False

        if np.mean(self.corrects)>self.threshold:
            return True
        else:
            return False

class NTrials(object):
    '''graduate after doing n trials'''
    PARAMS = ['n_trials']
    def __init__(self, n_trials, current_trial=0, **kwargs):
        self.n_trials = int(n_trials)
        print('n_trials: {}, current_trial: {}'.format(n_trials, current_trial))
        self.counter = count(start=current_trial)

    def update(self, row):
        trials = self.counter.next()
        if trials >= self.n_trials:
            return True
        else:
            return False




GRAD_LIST = {
    'accuracy':Accuracy,
    'n_trials':NTrials
}