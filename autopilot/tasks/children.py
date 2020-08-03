"""
Sub-tasks that serve as children to other tasks.

.. note::

    The Child agent will be formalized in an upcoming release, until then these classes
    remain relatively undocumented as their design will likely change.

"""

from collections import OrderedDict as odict
from collections import deque

import autopilot.transform
from autopilot import prefs
from autopilot.hardware.gpio import Digital_Out
from autopilot.hardware.usb import Wheel
from autopilot.hardware import cameras
from autopilot.core.networking import Net_Node
from autopilot.transform import transforms
from itertools import cycle
from queue import Empty, LifoQueue
import threading
import logging
from time import sleep

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
        self.hardware['OUTPUT'] = Digital_Out(prefs.HARDWARE['OUTPUT'])
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


class Video_Child(object):
    PARAMS = odict()
    PARAMS['cams'] = {'tag': 'Dictionary of camera params, or list of dicts',
                      'type': ('dict', 'list')}

    def __init__(self, cams=None, stage_block = None, start_now=True, **kwargs):
        """
        Args:
            cams (dict, list): Should be a dictionary of camera parameters or a list of dicts. Dicts should have, at least::

                {
                    'type': 'string_of_camera_class',
                    'name': 'name_of_camera_in_task',
                    'param1': 'first_param'
                }
        """

        if cams is None:
            Exception('Need to give us a cams dictionary!')

        self.cams = {}

        self.start_now = start_now


        if isinstance(cams, dict):

            try:
                cam_class = getattr(cameras, cams['type'])
                self.cams[cams['name']] = cam_class(**cams)
                # if start:
                #     self.cams[cams['name']].capture()
            except AttributeError:
                AttributeError("Camera type {} not found!".format(cams['type']))

        elif isinstance(cams, list):
            for cam in cams:
                try:
                    cam_class = getattr(cameras, cam['type'])
                    self.cams[cam['name']] = cam_class(**cam)
                    # if start:
                    #     self.cams[cam['name']].capture()
                except AttributeError:
                    AttributeError("Camera type {} not found!".format(cam['type']))

        self.stages = cycle([self.noop])
        self.stage_block = stage_block


        if self.start_now:
            self.start()
        # self.thread = threading.Thread(target=self._stream)
        # self.thread.daemon = True
        # self.thread.start()

    def start(self):
        for cam in self.cams.values():
            cam.capture()

    def stop(self):
        for cam_name, cam in self.cams.items():
            try:
                cam.release()
            except Exception as e:
                Warning('Couldnt release camera {},\n{}'.format(cam_name, e))



    def _stream(self):
        self.node = Net_Node(
            "T_CHILD",
            upstream=prefs.NAME,
            port=prefs.MSGPORT,
            listens = {},
            instance=True
        )

        while True:
            for name, cam in self.cams.items():
                try:
                    frame, timestamp = cam.q.get_nowait()
                    self.node.send(key='CONTINUOUS',
                                   value={cam.name:frame,
                                          'timestamp':timestamp},
                                   repeat=False,
                                   flags={'MINPRINT':True})
                except Empty:
                    pass



    def noop(self):
        # just fitting in with the task structure.
        self.stage_block.clear()
        return {}

    # def start(self):
    #     for cam in self.cams.values():
    #         cam.capture()
    #
    # def stop(self):
    #     for cam in self.cams.values():
    #         cam.release()

class Transformer(object):

    def __init__(self, transform,
                 operation: str ="trigger",
                 return_id = 'T',
                 return_key = None,
                 stage_block = None,
                 value_subset=None,
                 **kwargs):
        """

        Args:
            transform:
            operation (str): either

                * "trigger", where the last transform is a :class:`~autopilot.transform.transforms.Condition`
                and a trigger is returned to sender only when the return value of the transformation changes, or
                * "stream", where each result of the transformation is returned to sender

            return_id:
            stage_block:
            value_subset (str): Optional - subset a value from from a dict/list sent to :meth:`.l_process`
            **kwargs:
        """
        assert operation in ('trigger', 'stream', 'debug')
        self.operation = operation
        self._last_result = None

        if return_key is None:
            self.return_key = self.operation.upper()
        else:
            self.return_key = return_key

        self.return_id = return_id
        self.stage_block = stage_block
        self.stages = cycle([self.noop])
        # self.input_q = LifoQueue()
        self.input_q = deque(maxlen=1)
        self.value_subset = value_subset

        self.logger = logging.getLogger('main')

        self.process_thread = threading.Thread(target=self._process, args=(transform,))
        self.process_thread.daemon = True
        self.process_thread.start()

    def noop(self):
        # just fitting in with the task structure.
        self.stage_block.clear()
        return {}



    def _process(self, transform):

        self.transform = autopilot.transform.make_transform(transform)

        self.node = Net_Node(
            f"{prefs.NAME}_TRANSFORMER",
            upstream=prefs.NAME,
            port=prefs.MSGPORT,
            listens = {
                'CONTINUOUS': self.l_process
            },
            instance=False
        )

        self.node.send(self.return_id, 'STATE', value='READY')

        while True:
            try:
                # value = self.input_q.get_nowait()
                value = self.input_q.popleft()
            # except Empty:
            except IndexError:
                sleep(0.001)
                continue
            result = self.transform.process(value)

            self.node.logger.debug(f'Processed frame, result: {result}')


            if self.operation == "trigger":
                if result != self._last_result:
                    self.node.send(self.return_id, self.return_key, result)
                    self._last_result = result

            elif self.operation == 'stream':
                # FIXME: Another key that's not TRIGGER
                self.node.send(self.return_id, self.return_key, result)

            elif self.operation == 'debug':
                pass


    def l_process(self, value):
        # get array out of value

        # FIXME hack for dlc
        self.node.logger.debug('Received and queued processing!')
        # self.input_q.put_nowait(value['MAIN'])
        if self.value_subset:
            value = value[self.value_subset]
        self.input_q.append(value)










