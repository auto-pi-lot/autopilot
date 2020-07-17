"""
Tasks to test different features of autopilot.

Benchmarks, diagnostics, etc.
"""
from collections import OrderedDict as odict
from itertools import cycle, count
import tables
from datetime import datetime
from time import sleep
import threading

from autopilot import prefs
from autopilot.tasks.task import Task
from autopilot.hardware import gpio, cameras
from autopilot.transform import make_transform, transforms
from autopilot.core.networking import Net_Node


class DLC_Latency(Task):
    """
    Test Deeplabcut live end-to-end latency

    * Capture video -- all dark but with LED triggered by pilot
    * Send frames to Jetson (or other compute child)
    * Process with DLC
    * If LED is detected, jetson sends trigger back to Pilot
    * Pilot sends GPIO pulse

    """
    STAGE_NAMES = ['trig', 'wait']

    PARAMS = odict()
    PARAMS['child_id'] = {'tag': 'id of Child to process frames',
                          'type': 'str'}
    PARAMS['model_name'] = {'tag': 'name of deeplabcut project (located in <autopilot_dir>/dlc',
                            'type': 'str'}
    PARAMS['point_name'] = {'tag': 'name of deeplabcut point used to trigger',
                            'type': 'str'}
    PARAMS['trigger_freq'] = {'tag': 'Frequency of LED trigger (Hz)',
                              'type': 'float'}
    PARAMS['trigger_thresh'] = {'tag': 'Probability Threshold of Detection (0-1)',
                                'type': 'float'}
    PARAMS['trigger_limits_x'] = {'tag': 'Range of x (pixels) for object detection - list like [min, max]',
                                  'type': 'str'}
    PARAMS['trigger_limits_y'] = {'tag': 'Range of x (pixels) for object detection - list like [min, max]',
                                  'type': 'str'}
    PARAMS['trigger_max_y'] = {'tag': 'Maximum y (pixels) for object detection',
                                  'type': 'int'}
    PARAMS['crop_box'] = {'tag': 'Bounding box of image capture for FLIR camera [x_offset, y_offset, x_width, y_height]',
                          'type': 'str'}
    PARAMS['fps'] = {'tag': 'FPS of image acquisition',
                     'type': 'int'}
    PARAMS['exposure'] = {'tag': 'Exposure of camera (see cameras.Camera_Spinnaker.exposure)',
                          'type':'float'}
    PARAMS['delay'] = {'tag': 'Delay between trials (ms)',
                       'type': 'int'}


    PLOT = {
        'data': {
            'plot_trigger': 'segment',
            'plot_response': 'point'
        },
        'continuous': True
    }

    class TrialData(tables.IsDescription):
        trial_num = tables.Int32Col()
        trigger = tables.StringCol(26)
        response = tables.StringCol(26)
        plot_trigger = tables.Int8Col()
        plot_response = tables.Int8Col()

    HARDWARE = {
        'LEDS': {
            'C': gpio.LED_RGB
        },
        'CAMERAS': {
            'MAIN': cameras.Camera_Spinnaker
        },
        'DIGITAL_OUT': {
            'C': gpio.Digital_Out
        }
    }

    CHILDREN = {
        'DLC': {
            'task_type': 'Transformer',
            'transform': []
        }
    }


    def __init__(self,
                 child_id: str,
                 model_name: str,
                 point_name: str,
                 trigger_limits_x: list,
                 trigger_limits_y: list,
                 trigger_freq: float = 0.5,
                 trigger_thresh: float = 0.6,
                 crop_box: list = None,
                 fps: int = 30,
                 exposure: float = 0.5,
                 delay : int = 5000,
                 *args, **kwargs):
        """

        Args:
            child_id:
            trigger_freq:
            trigger_thresh:
            trigger_limits_x:
            trigger_limitx_y:
            crop_box:
            fps:
            exposure:
            delay (int): time to wait between trials (ms)
        """

        # if we have left and right LEDs, init them and turn them off
        HAS_LR_LEDS = False
        if 'L' in prefs.HARDWARE['LEDS'].keys() and 'R' in prefs.HARDWARE['LEDS'].keys():
            HAS_LR_LEDS = True

            self.HARDWARE['LEDS']['L'] = gpio.LED_RGB
            self.HARDWARE['LEDS']['R'] = gpio.LED_RGB

        super(DLC_Latency, self).__init__(*args, **kwargs)

        self.child_id = child_id
        self.model_name = model_name
        self.point_name = point_name
        self.trigger_limits_x = trigger_limits_x
        self.trigger_limits_y = trigger_limits_y
        self.trigger_freq = trigger_freq
        self.trigger_thresh = trigger_thresh
        self.crop_box = crop_box
        self.fps = fps
        self.exposure = exposure
        self.delay = delay
        self.trial_counter = count()
        self.current_trial = 0



        self.init_hardware()

        # if we have extra LEDs attached (as in the tripoke mount), turn them off
        if HAS_LR_LEDS:
            self.hardware['LEDS']['L'].set(0.0001)
            self.hardware['LEDS']['R'].set(0.0001)

        # configure the child
        transform_descriptor = [
            {'transform': 'T_DLC',
             'kwargs':{
                 'model_dir': self.model_name
             }},
            {'transform': 'T_DLCSlice',
             'kwargs':{
                 'select': self.point_name,
                 'min_probability': self.trigger_thresh
             }},
            {'transform': 'T_Condition',
             'kwargs': {
                 'minimum': [self.trigger_limits_x[0], self.trigger_limits_y[0]],
                 'maximum': [self.trigger_limits_x[1], self.trigger_limits_y[1]],
                 'elementwise': False
             }}
            ]

        self.node_id = f"T_{prefs.NAME}"
        self.node = Net_Node(id=self.node_id,
                             upstream=prefs.NAME,
                             port=prefs.MSGPORT,
                             listens={'STATE':self.l_state,
                                      'TRIGGER':self.l_trigger},
                             instance=False)

        # get our child started
        self.subject = kwargs['subject']
        value = {
            'child': {'parent': prefs.NAME, 'subject': kwargs['subject']},
            'task_type': 'Transformer',
            'subject': kwargs['subject'],
            'operation':'stream',
            'transform':transform_descriptor,
            'return_id': self.node_id
        }

        self.node.send(to=prefs.NAME, key='CHILD', value=value)

        # configure camera
        self.cam = self.hardware['CAMERAS']['MAIN']

        self.cam.fps = self.fps
        self.cam.exposure = self.exposure
        if self.crop_box:
            self.cam.set('Width', self.crop_box[2])
            self.cam.set('Height', self.crop_box[3])
            self.cam.set('OffsetX', self.crop_box[0])
            self.cam.set('OffsetY', self.crop_box[1])

        print(f"""
        Width: {self.cam.get('Width')}
        Height: {self.cam.get('Height')}
        OffsetX: {self.cam.get('OffsetX')}
        OffsetY: {self.cam.get('OffsetY')}
        FPS: {self.cam.get('AcquisitionFrameRate')}
        """)


        self.cam.stream(to=f"{self.child_id}_TRANSFORMER",
                        ip=prefs.CHILDIP, # FIXME: Hack before network discovery is fixed
                        port=prefs.CHILDPORT,
                        min_size=1)

        self.stages = cycle([self.trig, self.wait])
        self.stage_block = kwargs['stage_block']

    def trig(self, *args, **kwargs):
        """
        Blink the LED and await a trigger

        Returns:

        """
        self.stage_block.clear()

        self.current_trial = next(self.trial_counter)

        # pulse gpio and turn off LED when triggered
        self.triggers['CAMERA'] = [self.hardware['DIGITAL_OUT']['C'].pulse]

        trig_time = datetime.now().isoformat()
        self.hardware['LEDS']['C'].set(1)

        return {
            'trigger': trig_time,
            'trial_num': self.current_trial,
            'plot_trigger': 1
        }

    def wait(self):
        # self.stage_block.clear()
        response_time = datetime.now().isoformat()
        self.hardware['LEDS']['C'].set(0.0001)

        sleep(self.delay/1000)
        # timer = threading.Timer(interval=self.delay/1000, target=self.stage_block.clear)
        # timer.start()

        return {
            'response' : response_time,
            'plot_response': 1,
            'TRIAL_END': True
        }


    def l_state(self, value):
        self.logger.debug(f'STATE from transformer: {value}')

        if value == 'READY':
            if not self.cam.capturing.is_set():
                self.cam.capture()
                self.logger.debug(f"started capture")

    def l_trigger(self, value):
        if value:
            self.handle_trigger(pin="CAMERA")
            self.hardware['DIGITAL_OUT']['C'].pulse






