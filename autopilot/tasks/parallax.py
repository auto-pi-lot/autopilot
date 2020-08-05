"""
Parallax Jumping Task

Pilot:
    - 2x FLIR cameras at 100fps
    - 9DOF sensor
Child:
    - 2x opencv cameras at 30fps

"""

import itertools
import tables

from autopilot.hardware import cameras
from autopilot.tasks import Task
from autopilot.core.networking import Net_Node

from autopilot import prefs
TASK = 'Parallax'

class Parallax(Task):
    STAGE_NAMES = ["initiate", "jump", "reinforcement"]

    PLOT = {
        'data': {
            'accel_x': 'shaded'
        },
        # 'video' : ['SIDE', 'EYE', 'POV'],
        'video': ['SIDE'],
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
        'SIDE': 'infer',
        'EYE': 'infer',
        'POV': 'infer'
    }

    HARDWARE = {
        'CAMERAS': {
            'SIDE': cameras.Camera_Spinnaker,
            # 'EYE': cameras.Camera_CV
            # top...
        },
        # 'DOF': {
        #     'HEAD': i2c.I2C_9DOF
        # }
    }

    CHILDREN = {
        'HEADCAM': {
            'task_type': "Video Child",
            'cams': [
                {'type': 'Camera_OpenCV',
                 'name': 'POV',
                 'camera_idx': 0,
                 'stream': True
                 },
                # {'type': 'Camera_OpenCV',
                #  'name': 'head_2',
                #  'camera_idx': 2,
                #  'stream': True,
                #  }
            ]
        }
    }

    def __init__(self, stage_block = None, **kwargs):

        super(Parallax, self).__init__()

        self.stage_block = stage_block

        self.init_hardware()

        self.node = Net_Node(id="{}_TASK".format(prefs.NAME),
                             upstream=prefs.NAME,
                             port=prefs.MSGPORT,
                             listens = {},
                             instance = False)

        self.subject = kwargs['subject']
        # value = {
        #     'child': {'parent': prefs.NAME, 'subject': self.subject},
        #     'subject' : self.subject,
        #
        # }
        # value.update(self.CHILDREN['HEADCAM'])
        #
        # self.node.send(to=prefs.NAME, key='CHILD', value=value)

        self.stages = itertools.cycle([self.test])

        self.n_trials = itertools.count()

        # print(self.hardware)

        # self.hardware['CAMS']['EYE'].capture()
        self.hardware['CAMERAS']['SIDE'].stream(to="T")
        self.hardware['CAMERAS']['SIDE'].capture()

    def test(self):
        self.stage_block.clear()

        n_trial = next(self.n_trials)

        return {'trial_num':n_trial}





