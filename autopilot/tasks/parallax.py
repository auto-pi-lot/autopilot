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
from datetime import datetime

import numpy as np

from autopilot.hardware import cameras
from autopilot.hardware.esoteric import Parallax_Platform
from autopilot.tasks import Task
from autopilot.networking import Net_Node

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
    PARAMS['bail_height'] = {
        'tag': 'Height below which to consider the trial bailed',
        'type': 'int'
    }
    PARAMS['dlc_model_name'] = {
        'tag': 'name of DLC model to use, model files must be in <autopilot_dir>/dlc on the processing child',
        'type': 'str'
    },
    PARAMS['dlc_use_point'] = {
        'tag': 'Name of point from DLC model to use in motion estimation and task control',
        'type': 'str'
    }
    PARAMS['dlc_platform_points'] = {
        'tag': 'Names of left and right points used to track the platform lip (as a list)',
        'type': 'list'
    }
    PARAMS['dlc_jumpoff_points'] = {
        'tag': 'Names of left and right points used to track the platform the mouse jumps from (as a list)',
        'type': 'list'
    }
    PARAMS['child_dlc_id'] = {
        'tag': 'ID of agent that is running the DLC transformation',
        'type': 'str'
    }
    PARAMS['child_motion_id'] = {
        'tag': 'ID of agent that is running the motion controller',
        'type': 'str'
    }
    PARAMS['node_port'] = {
        'tag': 'Port to receive messages from our children',
        'type': 'int'
    }


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
        },
        'CAMS':{
            'SIDE': cameras.PiCamera
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
                 bail_height:int=None,
                 dlc_model_name:typing.Optional[str]=None,
                 dlc_use_point:typing.Optional[str] = None,
                 dlc_platform_points:typing.Optional[list] = None,
                 dlc_jumpoff_points:typing.Optional[list] = None,
                 child_dlc_id: typing.Optional[str] = None,
                 child_motion_id: typing.Optional[str] = None,
                 node_port:int=5570,
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
        self.bail_height = bail_height
        self.dlc_model_name = dlc_model_name
        self.dlc_use_point = dlc_use_point
        self.dlc_platform_points = dlc_platform_points
        self.dlc_jumpoff_points = dlc_jumpoff_points
        self.child_dlc_id = child_dlc_id
        self.child_motion_id = child_motion_id
        self.stage_block = stage_block
        self.node_port = node_port
        self.subject = kwargs.get('subject', prefs.get('SUBJECT'))

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
        self.node_id ="{}_TASK".format(prefs.get('NAME'))
        self.node = Net_Node(id=self.node_id,
                             upstream=prefs.get('NAME'),
                             port=prefs.get('MSGPORT'),
                             router_port=node_port,
                             listens = {
                                 'DLC': self.l_dlc,
                                 'MOTION': self.l_motion
                             },
                             instance = True)

        # stream to send continuous data back to Terminal
        self.stream = self.node.get_stream(
            id="{}_TASK_STREAM".format(prefs.get('NAME')),
            key='CONTINUOUS'
        )

        ## ------------------
        # Children

        # start DLC child
        transform_descriptor = [
            {
                'transform': 'image.DLC',
                'kwargs': {
                    'model_dir': self.dlc_model_name
                }
            }
        ]
        # this will start the DLC transformer, see tasks/children::Transformer
        self.node.send(
            to=[prefs.get('NAME'), self.child_dlc_id],
            key='START',
            value= {
                'child': {'parent': prefs.get('NAME'), 'subject': self.subject},
                'task_type': 'Transformer',
                'subject': self.subject,
                'operation': 'stream',
                'transform': transform_descriptor,
                'return_id': self.node_id,
                'return_ip': self.node.ip,
                'return_port': self.node_port,
                'return_key': 'DLC'
            }
        )

        # start IMU child
        self.node.send(
            to = [prefs.get('NAME'), self.child_motion_id],
            key='START',
            value = {
                'child': {'parent': prefs.get('NAME'), 'subject': self.subject},
                'task_type': 'Stream_Hardware',
                'subject': self.subject,
                'return_id': self.node_id,
                'return_ip': self.node.ip,
                'return_port': self.node_port,
                'return_key': 'MOTION',
                'device': ('I2C', 'IMU'),
            }
        )

        ## -------------------

        # TODO: Setup kalman filter transform

        # Start streaming frames to DLC agent
        self.hardware['CAMS']['SIDE'].stream(
            to=self.child_dlc_id,
            min_size=1
        )
        self.hardware['CAMS']['SIDE'].capture()

        self.stages = itertools.cycle([self.request, self.jump, self.reinforcement])

        self.n_trials = itertools.count()



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

        return {
            'trial_num': self.current_trial,
            'platform_width': self.platform_width,
            'platform_distance': self.platform_distance,
            'velocity_multiplier': self.velocity_multiplier
        }

    def jump(self):
        """
        Raise the platform to the particular level,

        Returns:

        """
        self.stage_block.clear()

        timestamp_requested = datetime.now().isoformat()
        # raise platform to height
        mask = self.hardware['PLAT']['FORM'].mask
        mask[:,:] = 0
        if self.platform_width == 2:
            mask[2:4, self.platform_distance:] = 1
        elif self.platform_width == 4:
            mask[1:5, self.platform_distance:] = 1
        elif self.platform_width == 6:
            mask[:,self.platform_distance:] = 1
        self.hardware['PLAT']['FORM'].mask = mask
        self.hardware['PLAT']['FORM'].height = self.platform_height
        # wait until the movement is finished
        self.hardware['PLAT']['FORM'].join()

        timestamp_raise = datetime.now().isoformat()

        # set the platform velocity control mode active
        self.velocity_active.set()
        self.current_stage = 'jump'

        # TODO: start timeout timer

        return {
            'timestamp_request': timestamp_requested,
            'timestamp_raise': timestamp_raise
        }


    def reinforcement(self):
        timestamp_jumped = datetime.now().isoformat()

        # TODO: clear timeout timer
        # TODO: deliver reward or don't

        # reset platform (level is blocking)
        self.hardware['PLAT']['FORM'].level()

        return {
            'timestamp_jumped': timestamp_jumped
        }


    def l_motion(self, value):
        if self.velocity_active.is_set():
            # TODO: kalman filter and transformation
            self.hardware['PLAT']['FORM'].velocity = value['velocity_y']*self.velocity_multiplier
        # TODO: send velocity on to T


    def l_dlc(self, value):
        if self.current_stage == 'request':
            # test that the mouse is above and between the jump platform
            on_plat = self._point_above(
                value[self.dlc_use_point],
                value[self.dlc_jumpoff_points[0]],
                value[self.dlc_jumpoff_points[1]]
            )
            # set the stage block to advance the task
            if on_plat:
                # unset until the stage method re-sets it
                self.current_stage = ''
                self.stage_block.set()

        elif self.current_stage == 'jump':
            # test that the mouse is above and between the parallax platform
            # test that the mouse is above and between the jump platform
            on_plat = self._point_above(
                value[self.dlc_use_point],
                value[self.dlc_platform_points[0]],
                value[self.dlc_platform_points[1]]
            )
            # set the stage block to advance the task
            if on_plat:
                # unset until the stage method re-sets it
                self.current_stage = ''
                self.stage_block.set()

        # TODO: send to terminal and add to kalman filter


    def _point_above(self, test_point, left_point, right_point):

        # check if x coord is within the left and right points
        within = left_point[0]<=test_point[0]<=right_point[0]
        if not within:
            return False

        # check if y coord is above the line formed by the two points
        b = left_point[1]
        m = (right_point[1] - left_point[1]) / (right_point[0] - left_point[0])
        # minimum y for the x position of the point
        y = m*(test_point[0]-left_point[0]) + b
        return test_point[1]>y










