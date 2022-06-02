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
from autopilot.networking import Net_Node
from autopilot.utils.loggers import init_logger
from itertools import cycle
from queue import Empty
import threading
from time import sleep

class Child(object):
    """Just a placeholder class for now to work with :func:`autopilot.get`"""

class Wheel_Child(Child):
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
        super(Wheel_Child, self).__init__(**kwargs)
        self.fs = fs
        self.thresh = thresh

        self.hardware = {}
        self.hardware['OUTPUT'] = Digital_Out(prefs.get('HARDWARE')['OUTPUT'])
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


class Video_Child(Child):
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
        super(Video_Child, self).__init__(**kwargs)

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
            upstream=prefs.get('NAME'),
            port=prefs.get('MSGPORT'),
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

class Transformer(Child):

    def __init__(self, transform,
                 operation: str ="trigger",
                 node_id = None,
                 return_id = 'T',
                 return_ip = None,
                 return_port = None,
                 return_key = None,
                 router_port = None,
                 stage_block = None,
                 value_subset=None,
                 forward_id=None,
                 forward_ip=None,
                 forward_port=None,
                 forward_key=None,
                 forward_what='both',
                 **kwargs):
        """

        Args:
            transform:
            operation (str): either

                * "trigger", where the last transform is a :class:`~autopilot.transform.transforms.Condition`
                and a trigger is returned to sender only when the return value of the transformation changes, or
                * "stream", where each result of the transformation is returned to sender

            return_id:
            return_ip:
            return_port:
            return_key:
            router_port (None, int): If not ``None`` (default), spawn the node with a route port to receieve
            stage_block:
            value_subset (str): Optional - subset a value from from a dict/list sent to :meth:`.l_process`
            forward_what (str): one of 'input', 'output', or 'both' (default) that determines what is forwarded
            **kwargs:
        """
        super(Transformer, self).__init__(**kwargs)
        assert operation in ('trigger', 'stream', 'debug')
        self.operation = operation
        self._last_result = None

        if return_key is None:
            self.return_key = self.operation.upper()
        else:
            self.return_key = return_key

        self.return_id = return_id
        self.return_ip = return_ip
        self.return_port = return_port
        if self.return_port is None:
            self.return_port = prefs.get('MSGPORT')
        if node_id is None:
            self.node_id = f"{prefs.get('NAME')}_TRANSFORMER"
        else:
            self.node_id = node_id
        self.router_port = router_port

        self.forward_id = forward_id
        self.forward_ip = forward_ip
        self.forward_port = forward_port
        self.forward_key = forward_key
        self.forward_node = None
        self.forward_what = forward_what

        self.stage_block = stage_block
        self.stages = cycle([self.noop])
        # self.input_q = LifoQueue()
        self.input_q = deque(maxlen=1)
        self.value_subset = value_subset

        self.logger = init_logger(self)

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
            self.node_id,
            upstream=self.return_id,
            upstream_ip=self.return_ip,
            port=self.return_port,
            router_port=self.router_port,
            listens = {
                'CONTINUOUS': self.l_process
            },
            instance=False
        )

        if all([x is not None for x in
                (self.forward_id,
                 self.forward_ip,
                 self.forward_key,
                 self.forward_port)]):
            self.forward_node = Net_Node(
                id=self.node_id,
                upstream=self.forward_id,
                upstream_ip=self.forward_ip,
                port=self.forward_port,
                listens={}
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
                    if self.forward_node is not None:
                        self.forward(value, result)
                    self._last_result = result

            elif self.operation == 'stream':
                # FIXME: Another key that's not TRIGGER
                self.node.send(self.return_id, self.return_key, result)
                if self.forward_node is not None:
                    self.forward(value, result)

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

    def forward(self, input=None, output=None):
        if self.forward_what == 'both':
            self.forward_node.send(self.forward_id, self.forward_key, {'input':input,'output':output},flags={'MINPRINT':True,'NOREPEAT':True})
        elif self.forward_what == 'input':
            self.forward_node.send(self.forward_id, self.forward_key, input,flags={'MINPRINT':True,'NOREPEAT':True})
        elif self.forward_what == 'output':
            self.forward_node.send(self.forward_id, self.forward_key, output,flags={'MINPRINT':True,'NOREPEAT':True})
        else:
            raise ValueError("forward_what must be one of 'input', 'output', or 'both'")












