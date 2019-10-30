"""
Sub-tasks that serve as children to other tasks
"""

from collections import OrderedDict as odict
from autopilot import prefs
from autopilot.core.hardware import Wheel, Digital_Out
from autopilot.hardware import cameras
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

    def __init__(self, cams, start=True, **kwargs):
        """
        Args:
            cams (dict, list): Should be a dictionary of camera parameters or a list of dicts. Dicts should have, at least::

                {
                    'type': 'string_of_camera_class',
                    'name': 'name_of_camera_in_task',
                    'param1': 'first_param'
                }
        """

        self.cams = {}


        if isinstance(cams, dict):

            try:
                cam_class = getattr(cameras, cams['type'])
                self.cams[cams['name']] = cam_class(**cams)
                if start:
                    self.cams[cams['name']].start()
            except AttributeError:
                AttributeError("Camera type {} not found!".format(cams['type']))

        elif isinstance(cams, list):
            for cam in cams:
                try:
                    cam_class = getattr(cameras, cam['type'])
                    self.cams[cam['name']] = cam_class(**cam)
                    if start:
                        self.cams[cams['name']].start()
                except AttributeError:
                    AttributeError("Camera type {} not found!".format(cam['type']))


    def start(self):
        for cam in self.cams.values():
            cam.start()

    def stop(self):
        for cam in self.cams.values():
            cam.release()






