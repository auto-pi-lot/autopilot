# graduation criteria
from collections import deque
import numpy as np


class Accuracy(object):
    PARAMS = ['threshold', 'window']
    def __init__(self, threshold=0.75, window=500):
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


GRAD_LIST = {
    'accuracy':Accuracy
}