"""
Sub-tasks that serve as children to other tasks
"""

from collections import OrderedDict as odict
from rpilot import prefs
from rpilot.core.hardware import Wheel

class Wheel_Child(object):
    STAGE_NAMES = ['collect']

    PARAMS = odict()
    PARAMS['fs'] = {'tag': 'Velocity Reporting Rate (Hz)',
                    'type': 'int'}
    PARAMS['thresh'] = {'tag': 'Distance Threshold',
                        'type': 'int'}

    def __init__(self, stage_block=None):

        self.mouse = Wheel(gpio_trig=True, pins=prefs.PINS['OUTPUT'])

    def stages(self):
        # just fitting in with the task structure.
        return {}

    def end(self):
        self.mouse.release()



