import threading
from subprocess import Popen, PIPE
import sys
import os
import csv
from skvideo import io
from skvideo.utils import vshape
import numpy as np
import base64
from datetime import datetime
import multiprocessing as mp
from tqdm.auto import tqdm


import time
import traceback
import blosc
import warnings
import subprocess
import logging
from ctypes import c_char_p




# import the Queue class from Python 3
if sys.version_info >= (3, 0):
    from queue import Queue, Empty

# otherwise, import the Queue class for Python 2.7
else:
    from queue import Queue, Empty

if sys.version_info >= (3,8):
    from multiprocessing import shared_memory

try:
    import PySpin
    PYSPIN = True
    PYSPIN_SYSTEM = None
except:
    PYSPIN = False

try:
    import cv2
    OPENCV = True
except:
    OPENCV = False

from autopilot import prefs
from autopilot.core.networking import Net_Node
from autopilot.hardware import Hardware

OPENCV_LAST_INIT_TIME = mp.Value('d', 0.0)
"""
Time the last OpenCV camera was initialized (seconds, from time.time()).

v4l2 has an extraordinarily obnoxious ...feature -- 
if you try to initialize two cameras at ~the same time,
you will get a neverending stream of informative error message: 'VIDIOC_QBUF: Invalid argument'

The workaround is relatively simple, we just wait ~2 seconds if another camera was just initialized.
"""
LAST_INIT_LOCK = mp.Lock()

class Camera(Hardware):
    input = True
    type = "CAMERA"

    def __init__(self, fps=None, queue=False, queue_size = 256, timed=False, **kwargs):
        super(Camera, self).__init__(**kwargs)
        self._cam = None
        # self._frame = None
        # self._shm = None
        self._output_filename = None
        self._capture_thread = None
        self.capturing = False
        self.q = None
        self.queue_size = None
        self.listens = None
        self.node = None
        self._writer = None
        self._write_q = None
        self._stream_q = None
        self.blosc = True
        self.shape = None
        self._indicator = None

        self.queue = queue
        self.fps = fps
        #self.write = write
        self.timed = timed

        if self.queue:
            self.queue_size = queue_size
            self.q =Queue(maxsize=self.queue_size)

        self.initialized = threading.Event()
        self.initialized.clear()

        # event to end acquisition
        self.stopping = threading.Event()
        self.stopping.clear()

        self.capturing = threading.Event()
        self.capturing.clear()

        self.streaming = threading.Event()
        self.streaming.clear()

        self.writing = threading.Event()
        self.writing.clear()

        self.indicating = threading.Event()
        self.indicating.clear()

    def capture(self, timed = None):


        if self.capturing.is_set():
            self.logger.warning("Already Capturing!")
            return

        if timed:
            self.timed = timed

        self._capture_thread = threading.Thread(target=self._capture)
        self._capture_thread.setDaemon(True)
        self._capture_thread.start()

    def _capture(self):

        self.capturing.set()
        self.stopping.clear()

        self.capture_init()

        if self.streaming.is_set():
            self.node.send(key='STATE', value='CAPTURING')

        try:
            self._process()
            if isinstance(self.timed, int) or isinstance(self.timed, float):
                if self.timed > 0:
                    start_time = time.time()
                    end_time = start_time + self.timed

            while not self.stopping.is_set():
                self._process()

                if self.timed:
                    if time.time() >= end_time:
                        self.stopping.set()


        finally:
            self.logger.info('Capture Ending')

            try:
                if self.streaming.is_set():
                    self.node.send(key='STATE', value='STOPPING')
                    self._stream_q.put('END')
            except Exception as e:
                self.logger.exception('Failed to end stream, error message: {}'.format(e))

            try:
                if self.writing.is_set():
                    self._write_deinit()

            except Exception as e:
                self.logger.exception('Failed to end writer, error message: {}'.format(e))

            if self.indicating.is_set():
                try:
                    self._indicator.close()
                except:
                    pass

            self.capturing.clear()
            self.capture_deinit()
            #self.release()
            #self.logger.info('Camera Released')

    def _process(self):

        try:
            self.frame = self._grab()
        except Exception as e:
            self.logger.exception(e)

        if self.streaming.is_set():
            self._stream_q.put_nowait({'timestamp': self.frame[0],
                                       self.name  : self.frame[1]})

        if self.writing.is_set():
            self._write_frame()

        if self.queue:
            self.q.put_nowait(self.frame)


        if self.writing.is_set():
            self._write_frame()

        if self.indicating.is_set():
            if not self._indicator:
                self._indicator = tqdm()
            self._indicator.update()



    def stream(self, to='T', ip=None, port=None, **kwargs):
        if to=='T':
            if not ip:
                ip = prefs.TERMINALIP
            if not port:
                port = prefs.TERMINALPORT

        else:

            if not ip:
                self.logger.warning('ip not passed, using localhost as default')
                ip = 'localhost'
            if not port:
                self.logger.warning('port not passed, using prefs.MSGPORT')
                port = prefs.MSGPORT


        self.listens = {
            'START': self.l_start,
            'STOP': self.l_stop
        }
        self.node = Net_Node(
            self.name,
            upstream=prefs.NAME,
            port=prefs.MSGPORT,
            listens=self.listens,
            instance=False,
            **kwargs
            #upstream_ip=prefs.TERMINALIP,
            #daemon=False
        )

        if hasattr(prefs, 'SUBJECT'):
            subject = prefs.SUBJECT
        else:
            self.logger.warning('nothing found for prefs.SUBJECT, probably running outside of task context')
            subject = None

        self._stream_q = self.node.get_stream(
            'stream', 'CONTINUOUS', upstream=to,
            ip=ip, port=port, subject=subject
        )

        self.streaming.set()

    def l_start(self, val):
        self.capture()

    def l_stop(self, val):
        self.release()



    def write(self, output_filename = None, timestamps=True, blosc=True):
        if not output_filename:
            output_filename = self.output_filename
        else:
            self._output_filename = output_filename

        self.blosc = blosc
        self.write_queue = mp.Queue()
        self.writer = Video_Writer(self.write_queue, output_filename, self.fps, timestamps=timestamps, blosc=blosc)
        self.writer.start()
        self.writing.set()

    def _write_frame(self):
        if self.blosc:
            self._write_q.put_nowait((self.frame[0], blosc.pack_array(self.frame[1])))
        else:
            self._write_q.put_nowait(self.frame)

    def _write_deinit(self):
        self._write_q.put_nowait('END')
        checked_empty = False
        while not self._write_q.empty():
            if not checked_empty:
                self.logger.warning(
                    'Writer still has ~{} frames, waiting on it to finish'.format(self._write_q.qsize()))
                checked_empty = True
            time.sleep(0.1)
        self.logger.warning('Writer finished, closing')






    @property
    def fps(self):
        return self._fps

    @fps.setter
    def fps(self, fps):
        self._fps = fps


    @property
    def cam(self):
        if not self._cam:
            self._cam = self.init_cam()
        return self._cam

    #
    # @property
    # def frame(self):
    #     if self._frame:
    #         return self._frame
    #     else:
    #         return False
    #
    # @frame.setter
    # def frame(self, frame):
    #     """
    #     Frame should be set (timestamp, frame)
    #
    #     Just making a property so we can automatically set the shape attribute
    #
    #     Args:
    #         frame:
    #
    #     Returns:
    #
    #     """
    #     # if not self._frame:
    #     #     # self._shm = shared_memory.SharedMemory(create=True, size=frame.nbytes)
    #     #     # self._frame = np.ndarray(frame.shape, dtype=frame.dtype, buffer=self._shm.buf)
    #     #     self._frame = (frame[0], np.ndarray(frame[1].shape, dtype=frame.dtype)
    #     #     self._frame[:] = frame[:]
    #     # else:
    #     #     self._frame[:] = frame[:]
    #
    #     self._frame = frame
    #     if not self.shape:
    #         self.shape = self._frame[1].shape

    # @property
    # def timestamp(self):
    #     if self._timestamp:
    #         return self._timestamp.value
    #     else:
    #         return False
    #
    # @timestamp.setter
    # def timestamp(self, timestamp):
    #     if not self._timestamp:
    #         # self._timestamp = mp.Value(c_char_p, timestamp)
    #     else:
    #         self._timestamp.value = timestamp

    @property
    def output_filename(self, new=False):
        # TODO: choose output directory

        if self._output_filename is None:
            new = True
        elif os.path.exists(self._output_filename) and not self.capturing.is_set():
            new = True

        if new:
            user_dir = os.path.expanduser('~')
            self._output_filename = os.path.join(user_dir, "capture_{}_{}.mp4".format(self.name,
                                                                                            datetime.now().strftime(
                                                                                                "%y%m%d-%H%M%S")))

        return self._output_filename

    def _grab(self):
        raise Exception("internal _grab method must be overwritten by camera subclass!!")

    def _timestamp(self):
        raise Exception("internal _timestamp method must be overwritten by camera subclass!!")


    def init_cam(self):
        raise Exception('init_camera must be overwritten by camera subclass!!')

    def capture_init(self):
        """
        An extra method a subclass can use to execute something that happens after initialization of the object, but before capturing

        by default dont't do anything. overriding this method is not required

        Returns:

        """
        pass

    def capture_deinit(self):
        """
        like the capture init function

        Returns:

        """

    def stop(self):
        self.stopping.set()

    def release(self):
        pass
        # if self._shm:
        #     try:
        #         self._shm.close()
        #         self._shm.unlink()
        #     except Exception as e:
        #         self.logger.exception(e)






class Camera_CV(Camera):
    def __init__(self, camera_idx = 0, **kwargs):
        if not OPENCV:
            ImportError('opencv was not imported, and is required for Camera_CV')

        super(Camera_CV, self).__init__(**kwargs)

        self._v4l_info = None

        self.last_opencv_init = globals()['OPENCV_LAST_INIT_TIME']
        self.last_init_lock = globals()['LAST_INIT_LOCK']

        self.camera_idx = camera_idx

    @property
    def fps(self):
        fps = self.cam.get(cv2.CAP_PROP_FPS)
        if fps == 0:
            fps = 30
            warnings.warn('Couldnt get fps from camera, using {} as default'.format(fps))
        return fps

    @property
    def shape(self):
        return (self.cam.get(cv2.CAP_PROP_FRAME_WIDTH),
                self.cam.get(cv2.CAP_PROP_FRAME_HEIGHT))

    def _grab(self):
        ret, frame = self.cam.read()
        if not ret:
            return False, False
        ts = self._timestamp()
        return (ts, frame)

    def _timestamp(self):
        return self.cam.get(cv2.CAP_PROP_POS_MSEC)

    @property
    def backend(self):
        return self.cam.getBackendName()

    def init_cam(self, camera_idx = None):

        self.initialized.set()

        if camera_idx is None:
            camera_idx = self.camera_idx

        with self.last_init_lock:
            time_since_last_init = time.time() - self.last_opencv_init.value
            if time_since_last_init < 2.:
                time.sleep(2.0 - time_since_last_init)
            vid = cv2.VideoCapture(camera_idx)
            self.last_opencv_init.value = time.time()

        self.logger.info("Camera Initialized")

        return vid

    def release(self):
        self.stop()
        self.cam.release()
        self._cam = None
        super(Camera_CV, self).release()


    @property
    def v4l_info(self):
        # TODO: get camera by other properties than index
        if not self._v4l_info:
            # query v4l device info
            cmd = ["/usr/bin/v4l2-ctl", '-D']
            out, err = Popen(cmd, stdout=PIPE, stderr=PIPE).communicate()
            out, err = out.strip(), err.strip()

            # split by \n to get lines, then group by \t
            out = out.split('\n')
            out_dict = {}
            vals = {}
            key = ''
            n_indents = 0
            for l in out:

                # if we're a sublist, but not a subsublist, split and strip, make a subdictionary
                if l.startswith('\t') and not l.startswith('\t\t'):
                    this_list = [k.strip() for k in l.strip('\t').split(':')]
                    subkey, subval = this_list[0], this_list[1]
                    vals[subkey] = subval

                # but if we're a subsublist... shouldn't have a dictionary
                elif l.startswith('\t\t'):
                    if not isinstance(vals[subkey], list):
                        # catch the previously assined value from the top level of the subdictionary
                        vals[subkey] = [vals[subkey]]

                    vals[subkey].append(l.strip('\t'))

                else:
                    # otherwise if we're at the bottom level, stash the key and any value dictioanry we've gathered before
                    key = l.strip(':')
                    if vals:
                        out_dict[key] = vals
                        vals = {}

            # get the last one
            out_dict[key] = vals

            self._v4l_info = out_dict

        return self._v4l_info


class Camera_Spinnaker(Camera):
    """
    Use: https://github.com/klecknerlab/simple_pyspin/blob/master/simple_pyspin/__init__.py
    """
    type="CAMERA_SPIN"


    if PYSPIN:
        ATTR_TYPES = {
            PySpin.intfIFloat      : PySpin.CFloatPtr,
            PySpin.intfIBoolean    : PySpin.CBooleanPtr,
            PySpin.intfIInteger    : PySpin.CIntegerPtr,
            PySpin.intfIEnumeration: PySpin.CEnumerationPtr,
            PySpin.intfIString     : PySpin.CStringPtr,
        }

        ATTR_TYPE_NAMES = {
            PySpin.intfIFloat      : 'float',
            PySpin.intfIBoolean    : 'bool',
            PySpin.intfIInteger    : 'int',
            PySpin.intfIEnumeration: 'enum',
            PySpin.intfIString     : 'string',
            PySpin.intfICommand    : 'command',
        }

        RW_MODES = {
            PySpin.RO: {'read':True, 'write': False},
            PySpin.RW: {'read': True, 'write': False},
            PySpin.WO: {'read': False, 'write': False},
            PySpin.NA: {'read': False, 'write': False}
        }
    else:

        ATTR_TYPES = {}
        ATTR_TYPE_NAMES = {}
        RW_MODES = {}

    def __init__(self, serial=None, camera_idx=None, save_timestamps=False, **kwargs):
        if not PYSPIN:
            ImportError('PySpin was not imported, and is required for Camera_Spinnaker')

        if serial and camera_idx:
            self.logger.warning("serial and camera_idx were both passed, defaulting to serial")
            camera_idx = None

        self.serial = serial
        self.camera_idx = camera_idx
        self.save_timestamps = save_timestamps



        self.system = None #spinnaker system
        self.cam_list = None
        self.nmap = None

        # internal variables
        self._bin = None
        self._exposure = None
        self._fps = None
        self._frame_trigger = None
        self._pixel_format = None
        self._acquisition_mode = None
        self._camera_attributes = {}
        self._camera_methods = {}
        self._camera_node_types = {}
        self._readable_attributes = {}
        self._writable_attributes = {}
        self._timestamps = []

        super(Camera_Spinnaker, self).__init__(**kwargs)

    def init_cam(self):

        # find our camera!
        # get the spinnaker system handle
        self.system = PySpin.System.GetInstance()
        # need to hang on to camera list for some reason, could be cargo cult code
        self.cam_list = self.system.GetCameras()


        if self.serial:
            cam = self.cam_list.GetBySerial(self.serial)
        elif self.camera_idx:
            self.logger.warning(
                'No camera serial number provided. \nAddressing cameras by serial number is STRONGLY recommended to avoid randomly using the wrong one')
            self.serial = 'noserial'
            cam = self.cam_list.GetByIndex(self.camera_idx)
        else:
            self.logger.warning(
                'No camera serial number OR camera index provided. Trying to use the first camera. This is a really bad way to call this object'
            )
            cam = self.cam_list.GetByIndex(0)

        # initialize the cam - need to do this before messing w the values
        cam.Init()
        # TODO: Document what a nodemap is...
        self.nmap = cam.GetTLDeviceNodeMap()

        # get list of camera methods and attributes for use with 'get' and 'set' methods
        for node in cam.GetNodeMap().GetNodes():
            pit = node.GetPrincipalInterfaceType()
            name = node.GetName()
            self._camera_node_types[name] = self.ATTR_TYPE_NAMES.get(pit, pit)
            if pit == PySpin.intfICommand:
                self._camera_methods[name] = PySpin.CCommandPtr(node)
            if pit in self.ATTR_TYPES:
                self._camera_attributes[name] = self.ATTR_TYPES[pit](node)

        return cam

    def capture_init(self):


        self.cam.BeginAcquisition()
        self.frame = self._grab()
        # FIXME: I think this will break single-shot or multishot modes.
        self.shape = self.frame[1].GetNDArray().shape
        self._frame = np.zeros_like(self.frame[1].GetNDArray())


    def capture_deinit(self):
        self.cam.EndAcquisition()




    def _process(self):
        frame_array = None
        try:
            self.frame = self._grab()
        except Exception as e:
            self.logger.exception(e)

        self._frame[:] = self.frame[1].GetNDArray()


        if self.writing.is_set():
            self._write_frame()

        if self.streaming.is_set():
            if not frame_array:
                frame_array = self.frame[1].GetNDArray()
            self._stream_q.put_nowait({'timestamp': self.frame[0],
                                       self.name  : frame_array})

        if self.indicating.is_set():
            if self._indicator is None:
                self._indicator = tqdm()
            self._indicator.update()

        # if self.queue:
        #     if not frame_array:
        #         frame_array = self.frame[1].GetNDArray()
        #     self.q.put_nowait(frame_array)

        if self.save_timestamps:
            self._timestamps.append(self.frame[0])

        self.frame[1].Release()

    def _grab(self):
        img = self.cam.GetNextImage()
        return (img.GetTimeStamp(), img)

    def write(self, output_filename = None, timestamps=True, blosc=True):
        # TODO: Jonny probably needs to fix this and overwrite the parent getter
        if not output_filename:
            output_filename = self.output_filename
        else:
            self._output_filename = output_filename

        # PNG images are losslessly compressed
        self.img_opts = PySpin.PNGOption()
        self.img_opts.compressionLevel = 1

        # make directory
        output_dir = self.output_filename
        os.makedirs(output_dir)

        # create base_path for output images
        self.base_path = os.path.join(output_dir, "capture_{}__".format(self.name))

        # self.blosc = blosc
        # self.write_q = mp.Queue()
        # self.writer = Video_Writer(self.write_queue, output_filename, self.fps, timestamps=timestamps, blosc=blosc)
        # self.writer.start()
        self.writing.set()

    def _write_frame(self):
        self.frame[1].Save(self.base_path+str(self.frame[0])+'.png', self.img_opts)


    def _write_deinit(self):
        self.logger.info('Writing images in {} to {}'.format(self.base_path, self.base_path + '.mp4'))
        self.writer = Directory_Writer(self.base_path, fps=self.fps)
        self.writer.encode()

    @property
    def bin(self):
        return (int(self.cam.BinningHorizontal.ToString()),
                int(self.cam.BinningVertical.ToString()))

    @bin.setter
    def bin(self, bin):
        self.cam.BinningSelector.SetValue(PySpin.BinningSelector_All)
        try:
            self.cam.BinningHorizontalMode.SetValue(PySpin.BinningHorizontalMode_Average)
            self.cam.BinningVerticalMode.SetValue(PySpin.BinningVerticalMode_Average)
        except PySpin.SpinnakerException:
            self.logger.warning('Average binning not supported, using sum')

        self.cam.BinningHorizontal.SetValue(int(bin[0]))
        self.cam.BinningVertical.SetValue(int(bin[1]))


    @property
    def exposure(self):
        if not self._exposure:
            self._exposure = self.get('ExposureTime')
        return self._exposure

    @exposure.setter
    def exposure(self, exposure):

        if exposure == 'auto':
            self.cam.ExposureAuto.SetValue(PySpin.ExposureAuto_Continuous)
            self._exposure = 'auto'
        elif isinstance(exposure, int) or isinstance(exposure, float):
            if exposure < 1:
                # proportional to fps
                exposure = (1.0 / self.fps) * exposure * 1e6

            self.cam.ExposureAuto.SetValue(PySpin.ExposureAuto_Off)
            self.cam.ExposureMode.SetValue(PySpin.ExposureMode_Timed)
            self.cam.ExposureTime.SetValue(exposure)
            self._exposure = exposure
        else:
            self.logger.exception('Dont know how to set exposure {}'.format(exposure))


    @property
    def fps(self):
        return self.cam.AcquisitionFrameRate.GetValue()

    @fps.setter
    def fps(self, fps):
        if isinstance(fps, int):
            self.cam.AcquisitionFrameRateEnable.SetValue(True)
            self.cam.AcquisitionFrameRate.SetValue(fps)
        elif fps is None:
            # initially set to None on superclass init
            pass
        else:
            self.logger.exception('Need to set FPS with an integer')

    @property
    def frame_trigger(self):
        pass

    @frame_trigger.setter
    def frame_trigger(self, frame_trigger):
        """
        https://www.flir.com/support-center/iis/machine-vision/application-note/configuring-synchronized-capture-with-multiple-cameras
        https://www.flir.com/support-center/iis/machine-vision/knowledge-base/what-external-iidc-trigger-modes-are-supported-by-my-camera/
        Args:
            frame_trigger:

        Returns:

        """
        # if we're generating the triggers...
        if frame_trigger == "lead":
            self.cam.LineSelector.SetValue(PySpin.LineSelector_Line2)
            self.cam.V3_3Enable.SetValue(True)
        elif frame_trigger == "follow":
            self.cam.TriggerMode.SetValue(PySpin.TriggerMode_Off)
            self.cam.TriggerSource.SetValue(PySpin.TriggerSource_Line3)
            # this article says that setting triggeroverlap is necessary, but not sure what it does
            # http://justinblaber.org/acquiring-stereo-images-with-spinnaker-api-hardware-trigger/
            self.cam.TriggerOverlap.SetValue(PySpin.TriggerOverlap_ReadOut)
            # In continuous mode, each trigger captures one frame8
            self.cam.TriggerSelector.SetValue(PySpin.TriggerSelector_FrameStart)

            self.cam.TriggerMode.SetValue(PySpin.TriggerMode_On)



    @property
    def acquisition_mode(self):
        return self.cam.AcquisitionMode.ToString()

    @acquisition_mode.setter
    def acquisition_mode(self, acquisition_mode):
        if acquisition_mode == 'continuous':
            self.cam.AcquisitionMode.SetValue(PySpin.AcquisitionMode_Continuous)
        elif acquisition_mode.startwsith("single"):
            self.cam.AcquisitionMode.SetValue(PySpin.AcquisitionMode_SingleFrame)
        elif acquisition_mode.startswith("multi"):
            self.cam.AcquisitionMode.SetValue(PySpin.AcquisitionMode_SingleFrame)
        else:
            self.logger.exception('Acquisition mode must be continuous, single, or multi')


    @property
    def readable_attributes(self):
        if not self._readable_attributes:

            for k, v in self._camera_attributes.items():
                if '_' in k:
                    continue
                if PySpin.IsReadable(v):
                    self._readable_attributes[k] = self.get(k)

        return self._readable_attributes

    @property
    def writable_attributes(self):
        if not self._writable_attributes:
            for k, v in self._camera_attributes.items():
                if '_' in k:
                    continue
                if PySpin.IsWritable(v):
                    self._writable_attributes[k] = self.get(k)

        return self._writable_attributes


    def get(self, attr):
        if attr in self._camera_attributes:

            prop = self._camera_attributes[attr]
            if not PySpin.IsReadable(prop):
                self.logger.exception("Camera property '%s' is not readable" % attr)

            if hasattr(prop, "GetValue"):
                return prop.GetValue()
            elif hasattr(prop, "ToString"):
                return prop.ToString()
            else:
                self.logger.exception("Camera property '%s' is not readable" % attr)
        elif attr in self._camera_methods:
            return self._camera_methods[attr].Execute
        else:
            raise AttributeError(attr)

    def set(self, attr, val):
        if attr in self._camera_attributes:

            prop = self._camera_attributes[attr]
            if not PySpin.IsWritable(prop):
                self.logger.exception("Property '%s' is not currently writable!" % attr)

            if hasattr(prop, 'SetValue'):
                prop.SetValue(val)
            else:
                prop.FromString(val)

        elif attr in self._camera_methods:
            self.logger.exception("Camera method '%s' is a function -- you can't assign it a value!" % attr)
        else:

            self.__setattr__(attr, val)


    def list_options(self, name):
        entries = {}

        if name in self._camera_attributes:
            node = self._camera_attributes[name]
        elif name in self._camera_methods:
            node = self._camera_methods[name]
        else:
            raise ValueError("'%s' is not a camera method or attribute" % name)

        access = False
        if hasattr(node, 'GetAccessMode'):
            access = node.GetAccessMode()

        # print(info)
        if access:
            if hasattr(node, 'GetEntries'):

                for entry in node.GetEntries():
                    entries[entry.GetName().lstrip('EnumEntry_')] = entry.GetDescription().strip()

        else:
            self.logger.exception("Couldn't access attribute {}".format(name))

        return entries

    @property
    def device_info(self):
        """
        Device information like ID, serial number, version. etc.

        Returns:

        """

        device_info = PySpin.CCategoryPtr(self.nmap.GetNode('DeviceInformation'))

        features = device_info.GetFeatures()

        # save information to a dictionary
        info_dict = {}
        for feature in features:
            node_feature = PySpin.CValuePtr(feature)
            info_dict[node_feature.GetName()] = node_feature.ToString()

        return info_dict

    def release(self):

        super(Camera_Spinnaker, self).release()

        self.stopping.set()

        self._camera_attributes = {}
        self._camera_methods = {}
        self._camera_node_types = {}

        if self.node:
            self.node.release()

        try:
            self.cam.EndAcquisition()
        except Exception as e:
            print(e)

        try:
            self.cam.DeInit()
        except AttributeError:
            pass
        except Exception as e:
            print(e)
            traceback.print_exc(file=sys.stdout)

        try:
            del self._cam
        except AttributeError as e:
            pass
        except Exception as e:
            self.logger.exception(e)

        try:
            self.cam_list.Clear()
            del self.cam_list
        except AttributeError:
            pass
        except Exception as e:
            self.logger.exception(e)

        try:
            del self.nmap
        except AttributeError:
            pass
        except Exception as e:
            self.logger.exception(e)

        try:
            self.system.ReleaseInstance()
        except Exception as e:
            self.logger.exception(e)

        if self.writing.is_set():
            self.writer.wait()





class Camera_Picam(Camera):
    """
    also can be used w/ picapture
    https://lintestsystems.com/wp-content/uploads/2016/09/PiCapture-SD1-Documentation.pdf
    """
    pass

#
# class Camera_Spin_Old(mp.Process):
#     """
#     A camera that uses the Spinnaker SDK + PySpin (eg. FLIR cameras)
#
#     .. todo::
#
#         should implement attribute setting like in https://github.com/justinblaber/multi_pyspin/blob/master/multi_pyspin.py
#
#         and have prefs loaded from .json like they do rather than making a bunch of config profiles
#
#
#     """
#
#     trigger = False
#     pin = None
#     type = "CAMERA_SPIN" # what are we known as in prefs?
#     input = True
#     output = False
#
#     def __init__(self, serial=None, name=None, write=False, stream = False, timed=False, bin=(4, 4), fps=None, exposure=None, cam_trigger=None, networked=False, blosc=True):
#         """
#
#
#         Args:
#             serial (str): Serial number of the camera to be initialized
#             bin (tuple): How many pixels to bin (Horizontally, Vertically).
#             fps (int): frames per second. If None, automatic exposure and continuous acquisition are used.
#             exposure (int, float): Either a float from 0-1 to set the proportion of the frame interval (0.9 is default) or absolute time in us
#         """
#         super(Camera_Spin, self).__init__()
#
#         # FIXME: Hardcoding just for testing
#         #serial = '19269891'
#         self.name = name
#         self.serial = serial
#
#         self.write = write
#         self.stream = stream
#         self.timed = timed
#         self.blosc = blosc
#
#         self.bin = bin
#         self.exposure = exposure
#         self.fps = fps
#         self.cam_trigger = cam_trigger
#         self.networked = networked
#         self.node = None
#
#         # used to quit the stream thread
#         self.quitting =  mp.Event()
#         self.quitting.clear()
#
#         self.capturing = False
#
#
#     def init_camera(self):
#
#         # find our camera!
#         # get the spinnaker system handle
#         self.system = PySpin.System.GetInstance()
#         # need to hang on to camera list for some reason, could be cargo cult code
#         self.cam_list = self.system.GetCameras()
#
#         if self.serial:
#             self.cam = self.cam_list.GetBySerial(self.serial)
#         else:
#             warnings.warn(
#                 'No camera serial number provided, trying to get the first camera.\nAddressing cameras by serial number is STRONGLY recommended to avoid randomly using the wrong one')
#             self.serial = 'noserial'
#             self.cam = self.cam_list.GetByIndex(0)
#
#         # initialize the cam - need to do this before messing w the values
#         self.cam.Init()
#
#         # get nodemap
#         # TODO: Document what a nodemap is...
#         self.nmap = self.cam.GetTLDeviceNodeMap()
#
#         # Set Default parameters
#         # FIXME: Should rely on params file
#         self.cam.PixelFormat.SetValue(PySpin.PixelFormat_Mono8)
#         #self.cam.AdcBitDepth.SetValue(PySpin.AdcBitDepth_Bit8)
#         self.cam.AcquisitionMode.SetValue(PySpin.AcquisitionMode_Continuous)
#
#         # configure binning - should come before fps because fps is dependent on binning
#         if self.bin:
#             self.cam.BinningSelector.SetValue(PySpin.BinningSelector_All)
#             try:
#                 self.cam.BinningHorizontalMode.SetValue(PySpin.BinningHorizontalMode_Average)
#                 self.cam.BinningVerticalMode.SetValue(PySpin.BinningVerticalMode_Average)
#             except PySpin.SpinnakerException:
#                 warnings.warn('Average binning not supported, using sum')
#
#             self.cam.BinningHorizontal.SetValue(int(self.bin[0]))
#             self.cam.BinningVertical.SetValue(int(self.bin[1]))
#
#         # exposure time is in microseconds, can be not given (90% fps interval used)
#         # given as a proportion (0-1) or given as an absolute value
#         if not self.exposure:
#             # exposure = (1.0/fps)*.9*1e6
#             self.cam.ExposureAuto.SetValue(PySpin.ExposureAuto_Continuous)
#         else:
#             if self.exposure < 1:
#                 # proportional
#                 self.exposure = (1.0 / self.fps) * self.exposure * 1e6
#
#             self.cam.ExposureAuto.SetValue(PySpin.ExposureAuto_Off)
#             self.cam.ExposureMode.SetValue(PySpin.ExposureMode_Timed)
#             self.cam.ExposureTime.SetValue(self.exposure)
#
#         # if fps is set, change to fixed fps mode
#         if self.fps:
#             self.cam.AcquisitionFrameRateEnable.SetValue(True)
#             self.cam.AcquisitionFrameRate.SetValue(self.fps)
#
#
#         # if we want to use hardware triggers, handle that now
#         if self.cam_trigger:
#             self.init_trigger(self.cam_trigger)
#
#
#         # event to signal when _capture
#
#         # if created, thread that streams frames
#         self.stream_thread = None
#
#         # if we are in capture mode, we allow frames to be grabbed from our .frame attribute
#         self.capturing = False
#         self._frame = None
#
#         if self.name is None:
#             self.name = "camera_{}".format(self.serial)
#
#         self.node = None
#         self.listens = None
#
#         self._output_filename = None
#
#         if self.networked or self.stream:
#             self.init_networking()
#
#         #########
#         # process management stuff
#
#
#
#     def init_networking(self):
#         self.listens = {
#             'START': self.l_start,
#             'STOP': self.l_stop
#         }
#         self.node = Net_Node(
#             self.name,
#             upstream=prefs.NAME,
#             port=prefs.MSGPORT,
#             listens=self.listens,
#             instance=False
#             #upstream_ip=prefs.TERMINALIP,
#             #daemon=False
#         )
#
#     def l_start(self, val):
#         self.capture()
#
#     def l_stop(self, val):
#         self.release()
#
#
#     @property
#     def device_info(self):
#         """
#         Device information like ID, serial number, version. etc.
#
#         Returns:
#
#         """
#
#         device_info = PySpin.CCategoryPtr(self.nmap.GetNode('DeviceInformation'))
#
#         features = device_info.GetFeatures()
#
#         # save information to a dictionary
#         info_dict = {}
#         for feature in features:
#             node_feature = PySpin.CValuePtr(feature)
#             info_dict[node_feature.GetName()] = node_feature.ToString()
#
#         return info_dict
#
#     @property
#     def frame(self):
#         if not self.capturing:
#             return (False, False)
#
#         try:
#             return (self._frame, self._timestamp)
#         except AttributeError:
#             return (False, False)
#
#         #return (img, ts)
#
#     def init_trigger(self, cam_trigger=None):
#         """
#         Set the camera to either generate or follow hardware triggers
#
#         :return:
#         """
#
#         # if we're generating the triggers...
#         if cam_trigger == "lead":
#             self.cam.LineSelector.SetValue(PySpin.LineSelector_Line2)
#             self.cam.V3_3Enable.SetValue(True)
#         elif cam_trigger == "follow":
#             self.cam.TriggerMode.SetValue(PySpin.TriggerMode_Off)
#             self.cam.TriggerSource.SetValue(PySpin.TriggerSource_Line3)
#             # this article says that setting triggeroverlap is necessary, but not sure what it does
#             # http://justinblaber.org/acquiring-stereo-images-with-spinnaker-api-hardware-trigger/
#             self.cam.TriggerOverlap.SetValue(PySpin.TriggerOverlap_ReadOut)
#             # In continuous mode, each trigger captures one frame8
#             self.cam.TriggerSelector.SetValue(PySpin.TriggerSelector_FrameStart)
#
#             self.cam.TriggerMode.SetValue(PySpin.TriggerMode_On)
#
#
#     def fps_test(self, n_frames=1000, writer=True):
#         """
#         Try to acquire frames, return mean fps and inter-frame intervals
#
#
#         Returns:
#             mean_fps (float): mean fps
#             sd_fps (float): standard deviation of fps
#             ifi (list): list of inter-frame intervals
#
#         """
#
#         # start acquitision
#         self.cam.BeginAcquisition()
#
#         # keep track of how many frames captured
#         frame = 0
#
#         # list of inter-frame intervals
#         ifi = []
#
#         # start a writer to stash frames
#         try:
#             if writer:
#                 self.write_q = Queue()
#                 self.writer = threading.Thread(target=self._writer, args=(self.write_q,))
#                 self.writer.start()
#         except Exception as e:
#             print(e)
#
#         while frame < n_frames:
#             img = self.cam.GetNextImage()
#             ifi.append(img.GetTimeStamp() / float(1e9))
#             if writer:
#                 self.write_q.put_nowait(img)
#             #img.Release()
#             frame += 1
#
#
#         if writer:
#             self.write_q.put_nowait('END')
#
#         # compute returns
#         # ifi is in nanoseconds...
#         fps = 1./(np.diff(ifi))
#         mean_fps = np.mean(fps)
#         sd_fps = np.std(fps)
#
#         if writer:
#             print('Waiting on video writer...')
#
#             self.writer.join()
#
#         self.cam.EndAcquisition()
#
#         return mean_fps, sd_fps, ifi
#
#     def capture(self, write=None, stream=None, timed=None):
#         if self.capturing == True:
#             warnings.warn("Camera is already capturing!")
#             return
#
#         if write is not None:
#             self.write = write
#
#         if stream is not None:
#             self.stream = stream
#
#         if timed is not None:
#             self.timed = timed
#
#         #self.capture_thread = threading.Thread(target=self._capture)
#         #self.capture_thread.setDaemon(True)
#         self.capturing = True
#         self.start()
#
#
#     def run(self):
#
#         self.quitting.clear()
#         self.init_camera()
#
#         if self.networked or self.stream:
#             self.node.send(key='STATE', value='CAPTURING')
#
#         if self.stream:
#             if hasattr(prefs, 'TERMINALIP') and hasattr(prefs, 'TERMINALPORT'):
#                 stream_ip   = prefs.TERMINALIP
#                 stream_port = prefs.TERMINALPORT
#             else:
#                 stream_ip   = None
#                 stream_port = None
#
#             if hasattr(prefs, 'SUBJECT'):
#                 subject = prefs.SUBJECT
#             else:
#                 subject = None
#
#             stream_q = self.node.get_stream(
#                 'stream', 'CONTINUOUS', upstream="T",
#                 ip=stream_ip, port=stream_port, subject=subject)
#
#
#
#         if self.write:
#             # PNG images are losslessly compressed
#             img_opts = PySpin.PNGOption()
#             img_opts.compressionLevel = 5
#
#             # make directory
#             output_dir = self.output_filename
#             os.makedirs(output_dir)
#
#             # create base_path for output images
#             base_path = os.path.join(output_dir, "capture_SN{}__".format(self.serial))
#             timestamps = []
#
#             # write_queue = mp.Queue()
#             # writer = Video_Writer(write_queue, base_path+'.mp4', fps=self.fps,
#             #                       timestamps=True, directory=True)
#             # writer.start()
#
#         if isinstance(self.timed, int) or isinstance(self.timed, float):
#             start_time = time.time()
#             end_time = start_time + self.timed
#
#
#         # start acquisition
#         # begin acquisition here so we can get height, width, etc.
#
#         #timestamps = []
#         try:
#             self.cam.BeginAcquisition()
#             while not self.quitting.is_set():
#                 img = self.cam.GetNextImage()
#                 #timestamp = img.GetTimeStamp() / float(1e9)
#                 timestamp = img.GetTimeStamp()
#                 #timestamps.append(this_timestamp)
#                 #self._frame = img.GetNDArray()
#                 #self._timestamp = timestamp
#
#
#                 if self.write:
#                     outpath = base_path +str(timestamp) + '.png'
#                     img.Save(outpath, img_opts)
#                     timestamps.append(timestamp)
#                     #write_queue.put_nowait((timestamp, outpath))
#
#                 img.Release()
#
#                 if self.stream:
#                     frame = img.GetNDArray()
#                     stream_q.put_nowait({'timestamp':timestamp,
#                                          self.name:frame})
#
#                 if self.timed:
#                     if time.time() >= end_time:
#                         self.quitting.set()
#                 # else:
#                 #     img.Release()
#
#         finally:
#             if self.stream:
#                 stream_q.put('END')
#
#             if self.networked:
#                 self.node.send(key='STATE', value='STOPPING')
#
#
#
#             if self.write:
#                 print('Writing images in {} to {}'.format(output_dir, output_dir+'.mp4'))
#                 writer = Directory_Writer(output_dir, fps=self.fps)
#                 writer.encode()
#
#
#             self.cam.EndAcquisition()
#             self.capturing = False
#             self._release()
#
#
#
#
#     @property
#     def output_filename(self, new=False):
#         if self._output_filename is None:
#             new = True
#         elif os.path.exists(self._output_filename):
#             new = True
#
#         if new:
#             dir = os.path.expanduser('~')
#             self._output_filename = os.path.join(dir, "capture_SN{}_{}".format(self.serial, datetime.now().strftime("%y%m%d-%H%M%S")))
#
#         return self._output_filename
#
#
#
#     def stop(self):
#         """
#         just stop acquisition or streaming, but don't release all resources
#         Returns:
#
#         """
#
#         self.quitting.set()
#
#
#     def __del__(self):
#         self.release()
#
#     def release(self):
#         try:
#             self.quitting.set()
#         except AttributeError:
#             # if we're deleting, we will probs not have some of our objects anymore
#             warnings.warn('Release called, but self.quitting no longer exists')
#
#     def _release(self):
#         # FIXME: Should check if finished writing to video before deleting tmp dir
#         #os.rmdir(self.tmp_dir)
#         # set quit flag to end stream thread if any.
#         # try:
#         #     self.quitting.set()
#         # except AttributeError:
#         #     # if we're deleting, we will probs not have some of our objects anymore
#         #     warnings.warn('Release called, but self.quitting no longer exists')
#
#         # if hasattr(self, 'capture_thread'):
#         #     if self.is_alive():
#         #         warnings.warn("Capture thread has not exited yet, waiting for that to happen")
#         #         sys.stderr.flush()
#         #         self.capture_thread.join()
#         #         warnings.warn("Capture thread exited successfully!")
#         #         sys.stderr.flush()
#
#         # release the net_node
#         if self.networked or self.node:
#             self.node.release()
#
#         try:
#             self.cam.DeInit()
#             del self.cam
#         except Exception as e:
#             print(e)
#             traceback.print_exc(file=sys.stdout)
#
#         try:
#             del self.cam
#         except AttributeError as e:
#             print(e)
#
#         try:
#             self.cam_list.Clear()
#             del self.cam_list
#         except Exception as e:
#             print(e)
#             traceback.print_exc(file=sys.stdout)
#
#         try:
#             del self.nmap
#         except Exception as e:
#             print(e)
#             traceback.print_exc(file=sys.stdout)
#
#         try:
#             self.system.ReleaseInstance()
#         except Exception as e:
#             print(e)
#             traceback.print_exc(file=sys.stdout)


class FastWriter(io.FFmpegWriter):
    def __init__(self, *args, **kwargs):
        super(FastWriter, self).__init__(*args, **kwargs)


    def writeFrame(self, im):
        """Sends ndarray frames to FFmpeg
        """
        vid = vshape(im)

        if not self.warmStarted:
            T, M, N, C = vid.shape
            self._warmStart(M, N, C, im.dtype)

        #vid = vid.clip(0, (1 << (self.dtype.itemsize << 3)) - 1).astype(self.dtype)

        try:
            self._proc.stdin.write(vid.tostring())
        except IOError as e:
            # Show the command and stderr from pipe
            msg = '{0:}\n\nFFMPEG COMMAND:\n{1:}\n\nFFMPEG STDERR ' \
                  'OUTPUT:\n'.format(e, self._cmd)
            raise IOError(msg)


class Directory_Writer(object):
    IMG_EXTS = ('.png', '.jpg')
    def __init__(self, dir, fps, ext='.png'):
        #self.images = sorted([os.path.join(dir, f) for f in os.listdir(dir) if \
        #    os.path.splitext(f)[1] in self.IMG_EXTS])
        self.dir = dir
        self.fps = fps
        self.ext = ext

        self.encode_thread = None

    def encode(self):
        self.encode_thread = threading.Thread(target=self._encode)
        self.encode_thread.start()

    def _encode(self):

        glob_str = os.path.join(self.dir.rstrip(os.sep)+ '*'+self.ext)

        ffmpeg_cmd = ['ffmpeg', "-y", '-r', str(self.fps),
                      '-pattern_type', 'glob', '-i', glob_str,
                      '-pix_fmt', 'yuv420p', '-r', str(self.fps),
                      '-vcodec', 'libx264', '-preset', 'veryfast',
                      self.dir.rstrip(os.sep)+'.mp4']

        result = subprocess.call(ffmpeg_cmd)
        return result

    def wait(self):
        if self.encode_thread:
            self.encode_thread.join()



class Video_Writer(mp.Process):
    def __init__(self, q, path, fps=None, timestamps=True, blosc=True, directory=False):
        """

        :param q:
        :param path:
        :param fps:
        :param timestamps: whether we'll be given timestamps in our queue, so inputs are (timestamp, image) tuples
        """
        super(Video_Writer, self).__init__()

        self.q = q
        self.path = path
        self.fps = fps
        self.given_timestamps = timestamps
        self.timestamps = []
        self.blosc = blosc
        self.directory = directory


        if fps is None:
            warnings.warn('No FPS given, using 30fps by default')
            self.fps = 30

    def run(self):

        self.timestamps = []


        out_vid_fn = self.path
        vid_out = io.FFmpegWriter(out_vid_fn,
        #vid_out = FastWriter(out_vid_fn,
            inputdict={
                '-r': str(self.fps),
        },
            outputdict={
                #'-vcodec': 'rawvideo',
                '-vcodec': 'libx264',
                #'-vcodec': 'h264_omx',
                '-pix_fmt': 'yuv420p',
                '-r': str(self.fps),
                '-preset': 'ultrafast',
            },
            verbosity=1
        )

        try:
            if self.directory:
                for input in iter(self.q.get, 'END'):
                    if self.given_timestamps:
                        img = io.vread(input[1])
                        self.timestamps.append(input[0])
                    else:
                        img = io.vread(input)
                        self.timestamps.append(datetime.now().isoformat())
                    vid_out.writeFrame(img)

            else:
                for input in iter(self.q.get, 'END'):
                    try:

                        if self.given_timestamps:
                            self.timestamps.append(input[0])
                            if self.blosc:
                                vid_out.writeFrame(blosc.unpack_array(input[1]))
                            else:
                                vid_out.writeFrame(input[1])
                        else:
                            self.timestamps.append(datetime.now().isoformat())
                            if self.blosc:
                                vid_out.writeFrame(blosc.unpack_array(input))
                            else:
                                vid_out.writeFrame(input)

                    except Exception as e:
                        print(e)
                        traceback.print_tb()
                        # TODO: Too general
                        break

        finally:

            # save timestamps as .csv
            ts_path = os.path.splitext(self.path)[0] + '.csv'
            with open(ts_path, 'w') as ts_file:
                csv_writer = csv.writer(ts_file)
                for ts in self.timestamps:
                    csv_writer.writerow([ts])

            vid_out.close()


def list_spinnaker_cameras():
    system = PySpin.System.GetInstance()
    cam_list = system.GetCameras()

    cam_info = []
    for cam in cam_list:
        nmap = cam.GetTLDeviceNodeMap()

        device_info = PySpin.CCategoryPtr(nmap.GetNode('DeviceInformation'))

        features = device_info.GetFeatures()

        # save information to a dictionary
        info_dict = {}
        for feature in features:
            node_feature = PySpin.CValuePtr(feature)
            info_dict[node_feature.GetName()] = node_feature.ToString()

        cam_info.append(info_dict)

    del cam
    cam_list.Clear()
    system.ReleaseInstance()

    return cam_info

#
# class Camera_OpenCV_Old(mp.Process):
#     """
#     https://www.pyimagesearch.com/2017/02/06/faster-video-file-fps-with-cv2-videocapture-and-opencv/
#     """
#
#     trigger = False
#     pin = None
#     type = "CAMERA_OPENCV" # what are we known as in prefs?
#     input = True
#     output = False
#
#     def __init__(self, camera_idx=0, write=False, stream=False, timed=False, name=None, networked=False, queue=False,
#                  queue_size = 128, queue_single = True, blosc=True,
#                  *args, **kwargs):
#         super(Camera_OpenCV, self).__init__()
#
#         self.last_opencv_init = globals()['OPENCV_LAST_INIT_TIME']
#         self.last_init_lock = globals()['LAST_INIT_LOCK']
#
#         if name:
#             self.name = name
#         else:
#             self.name = "camera_{}".format(camera_idx)
#
#         self.write = write
#         self.stream = stream
#         self.timed = timed
#         self.blosc = blosc
#
#         self.init_logging()
#
#         self._v4l_info = None
#
#         self.fps = None
#
#         # get handle to camera
#         self.camera_idx = camera_idx
#         self.vid = self.init_cam()
#         self.init_opencv_info()
#         self.vid.release()
#
#         # event to end acquisition
#         # self.stopped = mp.Event()
#         # self.stopped.clear()
#         #self.stopping = threading.Event()
#         self.stopping = mp.Event()
#         self.stopping.clear()
#
#         # keep the most recent frame so others can access with the frame attribute
#         self._frame = False
#
#         self._output_filename = None
#
#         # if we want to make a queue of frames available, do so
#         # only rly relevant to multiprocessing so taking out for now
#         self.queue = queue
#         self.queue_single = queue_single
#         self.queue_size = queue_size
#         self.q = None
#         if self.queue:
#             self.q = mp.Queue(maxsize=queue_size)
#
#         #self.capturing = False
#         self.capturing = mp.Event()
#         self.capturing.clear()
#
#         self.networked = networked
#         self.node = None
#         self.listens = None
#         if networked:
#             self.init_networking()
#
#
#
#
#         # deinit the camera so the other thread can start it
#         self.vid.release()
#
#
#
#     def init_cam(self, camera_idx = None):
#         if camera_idx is None:
#             camera_idx = self.camera_idx
#
#         with self.last_init_lock:
#             time_since_last_init = time.time() - self.last_opencv_init.value
#             if time_since_last_init < 2.:
#                 time.sleep(2.0 - time_since_last_init)
#             vid = cv2.VideoCapture(camera_idx)
#             self.last_opencv_init.value = time.time()
#
#         self.logger.info("Camera Initialized")
#
#         return vid
#
#     def l_start(self, val):
#         # if 'write' in val.keys():
#         #     write = val['write']
#         # else:
#         #     write = True
#
#         self.capture()
#
#     def l_stop(self, val):
#         self.release()
#
#     def init_opencv_info(self):
#         if not self.fps:
#             self.fps = self.vid.get(cv2.CAP_PROP_FPS)
#             if self.fps == 0:
#                 self.fps = 30
#                 warnings.warn('Couldnt get fps from camera, using {} as default'.format(self.fps))
#
#         self.shape = (self.vid.get(cv2.CAP_PROP_FRAME_WIDTH),
#                       self.vid.get(cv2.CAP_PROP_FRAME_HEIGHT))
#
#         # TODO: Make sure this works more generally since CAP_PROP_BACKEND is returnign -1 now
#         self.backend = self.vid.getBackendName()
#         # backends = [cv2.videoio_registry.getBackendName(i) for i in cv2.videoio_registry.getCameraBackends()]
#         # self.backend = backends[int(self.vid.get(cv2.CAP_PROP_BACKEND))]
#
#     def init_networking(self, daemon=False, instance=False):
#         self.listens = {
#             'START': self.l_start,
#             'STOP': self.l_stop
#         }
#         self.node = Net_Node(
#             self.name,
#             upstream=prefs.NAME,
#             port=prefs.MSGPORT,
#             listens=self.listens,
#             instance=instance,
#             daemon=daemon
#         )
#
#     def run(self):
#
#         if self.capturing.is_set():
#             self.logger.warning("Already capturing!")
#             return
#
#         self.capturing.set()
#         self.vid = self.init_cam()
#
#         opencv_timestamps = True
#         _, _ = self.vid.read()
#         _, _ = self.vid.read()
#         timestamp = 0
#         try:
#             timestamp = self.vid.get(cv2.CAP_PROP_POS_MSEC)
#         except Exception as e:
#             self.logger.warning("Couldn't use opencv timestamps, using system timestamps")
#             opencv_timestamps = False
#         if timestamp == 0:
#            opencv_timestamps = False
#
#
#         if self.write:
#             write_queue = mp.Queue()
#             writer = Video_Writer(write_queue, self.output_filename, self.fps, timestamps=True, blosc=self.blosc)
#             writer.start()
#
#         if self.networked or self.stream:
#             self.init_networking()
#             self.node.send(key='STATE', value='CAPTURING')
#
#         if self.stream:
#             if hasattr(prefs, 'TERMINALIP') and hasattr(prefs, 'TERMINALPORT'):
#                 stream_ip   = prefs.TERMINALIP
#                 stream_port = prefs.TERMINALPORT
#             else:
#                 stream_ip   = None
#                 stream_port = None
#
#             if hasattr(prefs, 'SUBJECT'):
#                 subject = prefs.SUBJECT
#             else:
#                 subject = None
#
#             stream_q = self.node.get_stream(
#                 'stream', 'CONTINUOUS', upstream="T",
#                 ip=stream_ip, port=stream_port, subject=subject)
#
#
#         if isinstance(self.timed, int) or isinstance(self.timed, float):
#             start_time = time.time()
#             end_time = start_time+self.timed
#
#         self.logger.info(("Starting capture with configuration:\n"+
#                           "Write: {}\n".format(self.write)+
#                           "Stream: {}\n".format(self.stream)+
#                           "Timed: {}".format(self.timed)))
#
#         try:
#             while not self.stopping.is_set():
#                 try:
#                     ret, frame = self.vid.read()
#                 except Exception as e:
#                     print(e)
#                     continue
#
#                 if not ret:
#                     self.logger.warning("No frame grabbed :(")
#                     continue
#
#                 if opencv_timestamps:
#                     timestamp = self.vid.get(cv2.CAP_PROP_POS_MSEC)
#                 else:
#                     timestamp = datetime.now().isoformat()
#
#                 if self.write:
#                     if self.blosc:
#                         write_queue.put_nowait((timestamp, blosc.pack_array(frame, clevel=5)))
#                     else:
#                         write_queue.put_nowait((timestamp, frame))
#
#                 if self.stream:
#                     stream_q.put_nowait({'timestamp':timestamp,
#                                          self.name:frame})
#
#                 if self.queue:
#                     if self.queue_single:
#                         # if just making the most recent frame available in queue,
#                         # pull previous frame if still there
#                         try:
#                             _ = self.q.get_nowait()
#                         except Empty:
#                             pass
#                     self.q.put_nowait((timestamp, frame))
#
#                 if self.timed:
#                     if time.time() >= end_time:
#                         self.stopping.set()
#
#         finally:
#             self.logger.info("Capture Ending")
#             # closing routine...
#             if self.stream:
#                 stream_q.put('END')
#
#             if self.networked:
#                 self.node.send(key='STATE', value='STOPPING')
#
#             if self.write:
#                 write_queue.put_nowait('END')
#                 checked_empty = False
#                 while not write_queue.empty():
#                     if not checked_empty:
#                         self.logger.warning('Writer still has ~{} frames, waiting on it to finish'.format(write_queue.qsize()))
#                         checked_empty = True
#                     time.sleep(0.1)
#                 warnings.warn('Writer finished, closing')
#
#             self.capturing.clear()
#
#             self.vid.release()
#             self.logger.info("Camera Released")
#
#
#
#
#
#     def capture(self, write=None, stream=None, queue=None, queue_size=None, timed=None):
#         #if self.capturing == True:
#         if self.capturing.is_set():
#             warnings.warn("Camera is already capturing!")
#             return
#
#         # release net node so it can be recreated in process
#         if self.networked:
#             if isinstance(self.node, Net_Node):
#                 self.node.release()
#
#         # change values if they've been given to us, otherwise keep init values
#         if write is not None:
#             self.write = write
#
#         if stream is not None:
#             self.stream = stream
#
#         if queue_size is not None:
#             self.queue_size = queue_size
#
#         if queue is not None:
#             self.queue = queue
#             if self.queue and not self.q:
#                 self.q = mp.Queue(maxsize=self.queue_size)
#
#         if timed is not None:
#             self.timed = timed
#
#         self.start()
#
#
#         # self.vid.release()
#
#         # self.capture_thread = threading.Thread(target=self._capture, args=(write,))
#         # self.capture_thread.start()
#         # self.capturing = True
#
#
#     @property
#     def output_filename(self, new=False):
#         # TODO: choose output directory
#
#         if self._output_filename is None:
#             new = True
#         elif os.path.exists(self._output_filename):
#             new = True
#
#         if new:
#             user_dir = os.path.expanduser('~')
#             self._output_filename = os.path.join(user_dir, "capture_camidx{}_{}.mp4".format(self.camera_idx,
#                                                                                             datetime.now().strftime(
#                                                                                                 "%y%m%d-%H%M%S")))
#
#         return self._output_filename
#
#     def release(self):
#         self.stopping.set()
#         if self.networked:
#             self.node.release()
#         self.vid.release()
#
#     @property
#     def frame(self):
#         # _, frame = self.stream.read()
#         if self.queue:
#             return self.q.get()
#         else:
#             return self._frame
#
#     @property
#     def v4l_info(self):
#         # TODO: get camera by other properties than index
#         if not self._v4l_info:
#             # query v4l device info
#             cmd = ["/usr/bin/v4l2-ctl", '-D']
#             out, err = Popen(cmd, stdout=PIPE, stderr=PIPE).communicate()
#             out, err = out.strip(), err.strip()
#
#             # split by \n to get lines, then group by \t
#             out = out.split('\n')
#             out_dict = {}
#             vals = {}
#             key = ''
#             n_indents = 0
#             for l in out:
#
#                 # if we're a sublist, but not a subsublist, split and strip, make a subdictionary
#                 if l.startswith('\t') and not l.startswith('\t\t'):
#                     this_list = [k.strip() for k in l.strip('\t').split(':')]
#                     subkey, subval = this_list[0], this_list[1]
#                     vals[subkey] = subval
#
#                 # but if we're a subsublist... shouldn't have a dictionary
#                 elif l.startswith('\t\t'):
#                     if not isinstance(vals[subkey], list):
#                         # catch the previously assined value from the top level of the subdictionary
#                         vals[subkey] = [vals[subkey]]
#
#                     vals[subkey].append(l.strip('\t'))
#
#                 else:
#                     # otherwise if we're at the bottom level, stash the key and any value dictioanry we've gathered before
#                     key = l.strip(':')
#                     if vals:
#                         out_dict[key] = vals
#                         vals = {}
#
#             # get the last one
#             out_dict[key] = vals
#
#             self._v4l_info = out_dict
#
#         return self._v4l_info
#
#     def init_logging(self):
#         """
#         Initialize logging to a timestamped file in `prefs.LOGDIR` .
#
#         The logger name will be `'node.{id}'` .
#         """
#         #FIXME: Just copying and pasting from net node, should implement logging uniformly across hw objects
#         timestr = datetime.now().strftime('%y%m%d_%H%M%S')
#         log_file = os.path.join(prefs.LOGDIR, 'CAM_{}_{}.log'.format("CAM_"+self.name, timestr))
#
#         self.logger = logging.getLogger('cam.{}'.format("CAM_"+self.name))
#         self.log_handler = logging.FileHandler(log_file)
#         self.log_formatter = logging.Formatter("%(asctime)s %(levelname)s : %(message)s")
#         self.log_handler.setFormatter(self.log_formatter)
#         self.logger.addHandler(self.log_handler)
#         if hasattr(prefs, 'LOGLEVEL'):
#             loglevel = getattr(logging, prefs.LOGLEVEL)
#         else:
#             loglevel = logging.WARNING
#         self.logger.setLevel(loglevel)
#         self.logger.info('{} Logging Initiated'.format(self.name))
#
