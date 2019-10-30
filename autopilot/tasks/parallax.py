"""
Parallax Jumping Task

Pilot:
    - 2x FLIR cameras at 100fps
    - 9DOF sensor
Child:
    - 2x opencv cameras at 30fps

"""


import datetime
import itertools
import tables
import threading
from random import random


from autopilot.core import hardware
from autopilot.hardware import cameras, i2c
from autopilot.tasks import Task
from collections import OrderedDict as odict
from autopilot.core.networking import Net_Node

from autopilot import prefs
TASK = 'Parallax'

class Parallax(Task):
    STAGE_NAMES = ["initiate", "jump", "reinforcement"]

    PLOT = {
        'data': {
            'accel_x': 'shaded'
        },
        'continuous': True
    }

    class TrialData(tables.IsDescription):
        trial_num = tables.Int32Col()
        # other stuff once we formalize the task more

    # since continuous data is one folder per session, one table per stream, specify with dict
    ContinuousData = {
        'accel_x': tables.Float64Col(),
        'accel_y': tables.Float64Col(),
        'accel_z': tables.Float64Col(),
        'head_1': 'infer',
        'head_2': 'infer',
        'flir_1': 'infer'
    }

    HARDWARE = {
        'CAMS': {
            'SIDE': cameras.Camera_Spin,
            # top...
        },
        'DOF': {
            'HEAD': i2c.I2C_9DOF
        }
    }

    CHILDREN = {
        'HEADCAM': {
            'task_type': "Video Child",
            'cams': [
                {'type': 'Camera_OpenCV',
                 'name': 'head_1',
                 'camera_idx': 0,
                 'stream': True,
                 },
                {'type': 'Camera_OpenCV',
                 'name': 'head_2',
                 'camera_idx': 1,
                 'stream': True,
                 }
            ]
        }
    }

    def __init__(self, stage_block = None, **kwargs):

        super(Parallax, self).__init__()

        self.stage_block = stage_block

        self.init_hardware()

        self.node = Net_Node(id="T_{}".format(prefs.NAME),
                             upstream=prefs.NAME,
                             port=prefs.MSGPORT,
                             listens = {},
                             instance = True)

        self.subject = kwargs['subject']
        value = {
            'child': {'parent': prefs.NAME, 'subject': kwargs['subject']},
            'subject' : self.subject,

        }
        value.update(self.CHILDREN['HEADCAM'])

        self.node.send(to=prefs.NAME, key='CHILD', value=value)

        self.stages = itertools.cycle([self.test])

        self.n_trials = itertools.count()

    def test(self):
        self.stage_block.clear()

        n_trial = self.n_trials.next()

        return {'trial_num':n_trial}



