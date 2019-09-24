"""
Sub-tasks that serve as children to other tasks
"""

from collections import OrderedDict as odict
from autopilot import prefs
from autopilot.core.hardware import Wheel, Digital_Out
from itertools import cycle

class Wheel_Child(object):
    STAGE_NAMES = ['collect']

    PARAMS = odict()
    PARAMS['fs'] = {'tag': 'Velocity Reporting Rate (Hz)',
                    'type': 'int'}
    PARAMS['thresh'] = {'tag': 'Distance Threshold',
                        'type': 'int'}

    HARDWARE = {
        "OUTPUT": Digital_Out,
        "WHEEL":  Wheel
    }



    def __init__(self, stage_block=None, fs=10, thresh=100, **kwargs):
        self.fs = fs
        self.thresh = thresh

        self.hardware = {}
        self.hardware['OUTPUT'] = Digital_Out(prefs.PINS['OUTPUT'])
        self.hardware['WHEEL'] = Wheel(digi_out = self.hardware['OUTPUT'],
                                       fs       = self.fs,
                                       thresh   = self.thresh,
                                       mode     = "steady")
        self.stages = cycle([self.noop])
        self.stage_block = stage_block

    def noop(self):
        # just fitting in with the task structure.
        self.stage_block.clear()
        return {}

    def end(self):
        self.hardware['WHEEL'].release()
        self.stage_block.set()



