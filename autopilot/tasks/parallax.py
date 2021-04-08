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
import typing
from collections import OrderedDict as odict
import threading

import numpy as np

from autopilot.hardware import cameras
from autopilot.hardware.esoteric import Parallax_Platform
from autopilot.tasks import Task
from autopilot.core.networking import Net_Node

from autopilot import prefs
TASK = 'Parallax'

class Parallax(Task):
    STAGE_NAMES = ["request", "jump", "reinforcement"]

    PARAMS = odict()
    PARAMS['reward'] = {
        'tag': 'Reward Duration (ms)',
        'type': 'int'
    }
    PARAMS['request_bbox'] = {
        'tag': 'Bounding Box of request platform, like [top, left, width, height] in pixels',
        'type': 'list'
    }
    PARAMS['platform_height'] = {
        'tag': 'Height to raise platform to on request, in mm',
        'type': 'float'
    }
    PARAMS['platform_widths'] = {
        'tag': 'Centered widths of pillars to pick from like [2,4,6]',
        'type': 'list'
    }
    PARAMS['platform_distances'] = {
        'tag': 'Distances of single rows to raise to pick from like [0, 1, 5]',
        'type': 'list'
    }
    PARAMS['velocity_multipliers'] = {
        'tag': 'Scale factors for converting IMU velocity to platform velocity, as a list like [0, -1, 0.5]',
        'type': 'list'
    }
    PARAMS['timeout'] = {
        'tag': 'Time from request to aborting trial if mouse has not jumped, in seconds',
        'type': 'float'
    },
    PARAMS['dlc_model_name'] = {
        'tag': 'name of DLC model to use, model files must be in <autopilot_dir>/dlc on the processing child',
        'type': 'str'
    },



    PLOT = {
        'data': {
            'accel_y': 'shaded'
        },
        # 'video' : ['SIDE', 'EYE', 'POV'],
        'video': ['SIDE'],
        'continuous': True
    }

    class TrialData(tables.IsDescription):
        trial_num = tables.Int32Col()
        platform_width = tables.Int32Col()
        platform_distance = tables.Int32Col()
        timestamp_request = tables.StringCol(26)
        timestamp_raised = tables.StringCol(26)
        timestamp_jumped = tables.StringCol(26)
        bailed = tables.BoolCol()
        multiplier = tables.Float32Col()




        # other stuff once we formalize the task more

    # since continuous data is one folder per session, one table per stream, specify with dict
    ContinuousData = {
        'accel_x': tables.Float64Col(),
        'accel_y': tables.Float64Col(),
        'accel_z': tables.Float64Col(),
        'SIDE': 'infer',
        'velocity': tables.Float64Col(),
        'pose': 'infer'
    }

    HARDWARE = {
        'PLAT':{
            'FORM': Parallax_Platform
        }
    }

    CHILDREN = {
        'MOTION': {
            'task_type': "Parallax Child",
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

    def __init__(self, reward:float=20, request_bbox:tuple=(0,0,128,128),
                 platform_height:float=50,
                 platform_widths:typing.Tuple[int, ...]=(2, 4, 6),
                 platform_distances:typing.Tuple[int, ...]=(0,1,2,3,4,5),
                 velocity_multipliers:typing.Tuple[float, ...] = (1,),
                 timeout:float=10,
                 dlc_model_name:typing.Optional[str]=None,
                 stage_block = None, *args, **kwargs):

        super(Parallax, self).__init__(*args, **kwargs)

        # store parameters
        self.reward = float(reward)
        self.request_bbox = (int(bbox) for bbox in request_bbox)
        self.platform_height = float(platform_height)
        self.platform_widths = (int(width) for width in platform_widths)
        self.platform_distances = (int(distance) for distance in platform_distances)
        self.velocity_multipliers = (float(vel) for vel in velocity_multipliers)
        self.timeout = float(timeout)
        self.dlc_model_name = dlc_model_name
        self.stage_block = stage_block

        # init attributes
        self.velocity_multiplier = 0
        """
        Current velocity multiplier to use when setting platform velocity
        """
        self.velocity_active = threading.Event()
        """
        :class:`threading.Event` that is set when velocity readings from the IMU are
        to be fed to the :class:`~.hardware.esoteric.Parallax_Platform` , multiplied
        by :attr:`~.velocity_multiplier`
        """
        self.platform_width = None
        """
        int: current platform width
        """
        self.platform_distance = None
        """
        int: current platform distance
        """
        self.current_stage = None
        """
        str: name of current stage
        """


        self.init_hardware()

        # initialize net node for communicating with child
        self.node = Net_Node(id="{}_TASK".format(prefs.get('NAME')),
                             upstream=prefs.get('NAME'),
                             port=prefs.get('MSGPORT'),
                             listens = {},
                             instance = False)

        self.stream = self.node.get_stream("{}_TASK_STREAM".format(prefs.get('NAME')))


        # value = {
        #     'child': {'parent': prefs.get('NAME'), 'subject': self.subject},
        #     'subject' : self.subject,
        #
        # }
        # value.update(self.CHILDREN['HEADCAM'])
        #
        # self.node.send(to=prefs.get('NAME'), key='CHILD', value=value)

        self.stages = itertools.cycle([self.test])

        self.n_trials = itertools.count()

        # print(self.hardware)

        # self.hardware['CAMS']['EYE'].capture()
        # self.hardware['CAMERAS']['SIDE'].stream(to="T")
        # self.hardware['CAMERAS']['SIDE'].capture()

    # --------------------------------------------------
    # Stage methods
    # --------------------------------------------------

    def request(self):
        self.stage_block.clear()

        # prevent calling any triggers rn
        self.trigger_lock.acquire()
        self.triggers = {}
        self.current_stage = "request"

        # reset state flags
        self.velocity_active.clear()

        # calculate stage params
        self.platform_width = np.random.choice(self.platform_widths)
        self.platform_distance = np.random.choice(self.platform_distances)
        self.velocity_multiplier = np.random.choice(self.velocity_multipliers)

        self.current_trial = next(self.trial_counter)


        pass

    def jump(self):
        pass

    def reinforcement(self):
        pass

    def test(self):
        self.stage_block.clear()

        n_trial = next(self.n_trials)

        return {'trial_num':n_trial}

    def l_velocity(self, value):
        if self.velocity_active.is_set():
            self.hardware['PLAT']['FORM'].velocity = value['velocity_y']*self.velocity_multiplier







