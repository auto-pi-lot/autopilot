import cv2
import threading
from subprocess import Popen, PIPE
import sys
import time
from itertools import count
import os
from skvideo import io
import numpy as np
#from tqdm import tqdm, trange
from datetime import datetime

# import the Queue class from Python 3
if sys.version_info >= (3, 0):
    from queue import Queue, Empty

# otherwise, import the Queue class for Python 2.7
else:
    from Queue import Queue, Empty

import multiprocessing as mp
from autopilot.core.networking import Net_Node


try:
    import PySpin
    PYSPIN = True
except:
    PYSPIN = False

from autopilot import prefs



class Camera_OpenCV(object):
    """
    https://www.pyimagesearch.com/2017/02/06/faster-video-file-fps-with-cv2-videocapture-and-opencv/
    """

    trigger = False

    def __init__(self, camera_idx = 0, stream=False, queue=False, queue_size = 128, name = None, *args, **kwargs):
        super(Camera_OpenCV, self).__init__()


        if name:
            self.name = name
        else:
            self.name = "camera_{}".format(camera_idx)

        self._v4l_info = None

        self.camera_idx = camera_idx
        self.vid = None

        self.stopped = mp.Event()
        self.stopped.clear()

        self._frame = False

        self.queue = queue
        self.q = None
        if self.queue:
            self.q = mp.Queue(maxsize=queue_size)

        self.stream = stream
        self.node = None
        self.listens = None
        if self.stream:
            self.listens = {
                'STOP': self.release
            }
            # self.node = Net_Node(
            #     self.name,
            #     upstream=prefs.NAME,
            #     port=prefs.MSGPORT,
            #     listens=self.listens,
            #     instance = False
            # )



    # def run(self):
    #     self._update()
    #     # t = Thread(target=self._update)
    #     # t.daemon = True
    #     # t.start()

    def start(self):
        self.thread = threading.Thread(target=self._update)
        self.thread.daemon = True
        self.thread.start()

    def _update(self):

        self.vid = cv2.VideoCapture(self.camera_idx)


        if self.stream:
            self.node = Net_Node(
                self.name,
                upstream=prefs.NAME,
                port=prefs.MSGPORT,
                listens=self.listens,
                instance = True
            )

        while not self.stopped.is_set():
            _, self._frame = self.vid.read()
            timestamp = self.vid.get(cv2.CAP_PROP_POS_MSEC)
            if self.stream:
                self.node.send(key='CONTINUOUS',
                               value={self.name:self._frame,
                                      'timestamp':timestamp},
                               repeat=False)

            if self.queue:
                if not self.q.full():
                    self.q.put_nowait(self._frame)

    def release(self):
        self.stopped.set()
        self.vid.release()

    @property
    def frame(self):
        #_, frame = self.stream.read()
        if self.queue:
            return self.q.get()
        else:
            return self._frame

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


class Camera_Spin(object):
    """
    A camera that uses the Spinnaker SDK + PySpin (eg. FLIR cameras)

    .. todo::

        should implement attribute setting like in https://github.com/justinblaber/multi_pyspin/blob/master/multi_pyspin.py

        and have prefs loaded from .json like they do rather than making a bunch of config profiles


    """

    trigger = False

    def __init__(self, serial=None, bin=(4, 4), fps=None, exposure=None):
        """


        Args:
            serial (str): Serial number of the camera to be initialized
            bin (tuple): How many pixels to bin (Horizontally, Vertically).
            fps (int): frames per second. If None, automatic exposure and continuous acquisition are used.
            exposure (int, float): Either a float from 0-1 to set the proportion of the frame interval (0.9 is default) or absolute time in us
        """

        # FIXME: Hardcoding just for testing
        #serial = '19269891'
        self.serial = serial

        # find our camera!
        # get the spinnaker system handle
        self.system = PySpin.System.GetInstance()
        # need to hang on to camera list for some reason, could be cargo cult code
        self.cam_list = self.system.GetCameras()

        if self.serial:
            self.cam = self.cam_list.GetBySerial(self.serial)
        else:
            Warning(
                'No camera serial number provided, trying to get the first camera.\nAddressing cameras by serial number is STRONGLY recommended to avoid randomly using the wrong one')
            self.serial = 'noserial'
            self.cam = self.cam_list.GetByIndex(0)

        # initialize the cam - need to do this before messing w the values
        self.cam.Init()

        # get nodemap
        # TODO: Document what a nodemap is...
        self.nmap = self.cam.GetTLDeviceNodeMap()

        # Set Default parameters
        # FIXME: Should rely on params file
        self.cam.PixelFormat.SetValue(PySpin.PixelFormat_Mono8)
        #self.cam.AdcBitDepth.SetValue(PySpin.AdcBitDepth_Bit8)
        self.cam.AcquisitionMode.SetValue(PySpin.AcquisitionMode_Continuous)

        # configure binning - should come before fps because fps is dependent on binning
        if bin:
            self.cam.BinningSelector.SetValue(PySpin.BinningSelector_All)
            try:
                self.cam.BinningHorizontalMode.SetValue(PySpin.BinningHorizontalMode_Average)
                self.cam.BinningVerticalMode.SetValue(PySpin.BinningVerticalMode_Average)
            except PySpin.SpinnakerException:
                Warning('Average binning not supported, using sum')

            self.cam.BinningHorizontal.SetValue(int(bin[0]))
            self.cam.BinningVertical.SetValue(int(bin[1]))

        # exposure time is in microseconds, can be not given (90% fps interval used)
        # given as a proportion (0-1) or given as an absolute value
        if not exposure:
            # exposure = (1.0/fps)*.9*1e6
            self.cam.ExposureAuto.SetValue(PySpin.ExposureAuto_Continuous)
        else:
            if exposure < 1:
                # proportional
                exposure = (1.0 / fps) * exposure * 1e6

            self.cam.ExposureAuto.SetValue(PySpin.ExposureAuto_Off)
            self.cam.ExposureMode.SetValue(PySpin.ExposureMode_Timed)
            self.cam.ExposureTime.SetValue(exposure)

        # if fps is set, change to fixed fps mode
        if fps:
            self.cam.AcquisitionFrameRateEnable.SetValue(True)
            self.cam.AcquisitionFrameRate.SetValue(fps)
        self.fps = fps

        # used to quit the stream thread
        self.quitting = threading.Event()
        self.quitting.clear()

        # if created, thread that streams frames
        self.stream_thread = None

        # if we are in capture mode, we allow frames to be grabbed from our .frame attribute
        self.capturing = False
        self._frame = None



    @property
    def bin(self):
        return (self.cam.BinningHorizontal.GetValue(), self.cam.BinningHorizontal.GetValue())

    @bin.setter
    def bin(self, new_bin):
        # TODO: Check if acquiring yno
        self.cam.BinningHorizontal.SetValue(int(new_bin[0]))
        self.cam.BinningVertical.SetValue(int(new_bin[1]))


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

    @property
    def frame(self):
        if not self.capturing:
            return (False, False)

        try:
            img = self._frame.GetNDArray()
            ts = self._frame.GetTimeStamp()
        except AttributeError:
            return (False, False)

        return (img, ts)


    def fps_test(self, n_frames=1000, writer=True):
        """
        Try to acquire frames, return mean fps and inter-frame intervals


        Returns:
            mean_fps (float): mean fps
            sd_fps (float): standard deviation of fps
            ifi (list): list of inter-frame intervals

        """

        # start acquitision
        self.cam.BeginAcquisition()

        # keep track of how many frames captured
        frame = 0

        # list of inter-frame intervals
        ifi = []

        # start a writer to stash frames
        try:
            if writer:
                self.write_q = Queue()
                self.writer = threading.Thread(target=self._writer, args=(self.write_q,))
                self.writer.start()
        except Exception as e:
            print(e)

        while frame < n_frames:
            img = self.cam.GetNextImage()
            ifi.append(img.GetTimeStamp() / float(1e9))
            if writer:
                self.write_q.put_nowait(img)
            #img.Release()
            frame += 1


        if writer:
            self.write_q.put_nowait('END')

        # compute returns
        # ifi is in nanoseconds...
        fps = 1./(np.diff(ifi))
        mean_fps = np.mean(fps)
        sd_fps = np.std(fps)

        if writer:
            print('Waiting on video writer...')

            self.writer.join()

        self.cam.EndAcquisition()

        return mean_fps, sd_fps, ifi

    def tmp_dir(self, new=False):
        if new or not hasattr(self, '_tmp_dir'):
            self._tmp_dir = os.path.join(os.path.expanduser('~'),
                                    '.tmp_capture_{}_{}'.format(self.serial, datetime.now().strftime("%y%m%d-%H%M%S")))
            os.mkdir(self._tmp_dir)

        return self._tmp_dir

    def capture(self):
        self.capture_thread = threading.Thread(target=self._capture)
        self.capture_thread.setDaemon(True)
        self.capture_thread.start()
        self.capturing = True

    def _capture(self):
        self.quitting.clear()


        # start acquitision
        self.cam.BeginAcquisition()
        while not self.quitting.is_set():
            self._frame = self.cam.GetNextImage()

        self.cam.EndAcquisition()

        self.capturing = False




    def stream(self, target):
        """

        Args:
            target (:class:`~Queue.Queue`, str): Either a Queue to dump frames into, or a network address to stream to.

        Returns:

        """

        self.stream_thread = threading.Thread(target=self._stream, args=(target,))
        self.stream_thread.setDaemon(True)
        self.stream_thread.start()




    def _stream(self, target):
        self.quitting.clear()

        stream_type = None
        if isinstance(target, Queue):
            stream_type = "queue"


        # start acquitision
        self.cam.BeginAcquisition()
        while not self.quitting.is_set():
            img = self.cam.GetNextImage()

            if stream_type == "queue":
                target.put_nowait((img.GetNDArray(), img.GetTimeStamp()))

            img.Release()

        self.cam.EndAcquisition()

        if stream_type == "queue":
            target.put_nowait('END')



    def _writer(self, q):
        """
        Thread to write frames to file, then compress to video.

        Todo:
            need to wrap this all up in capture method

        Returns:

        """
        out_dir = self.tmp_dir(new=True)
        frame_n = 0
        # TODO: Get this from prefs, just testing this
        out_vid_fn = os.path.join(os.path.expanduser('~'), "{}_{}.mp4".format(self.serial, datetime.now().strftime("%y%m%d-%H%M%S")))

        vid_out = io.FFmpegWriter(out_vid_fn,
            inputdict={
                '-r': str(self.fps),
        },
            outputdict={
                '-vcodec': 'libx264',
                '-pix_fmt': 'yuv420p',
                '-r': str(self.fps),
                '-preset': 'fast'
            },
            verbosity=1
        )


        for img in iter(q.get, 'END'):
            try:
                #fname = os.path.join(out_dir, "{}_{:06d}.tif".format(self.serial, frame_n))
                #img.Save(fname)
                img_arr = img.GetNDArray()
                #print(img_arr.shape)
                vid_out.writeFrame(img_arr)
                img.Release()
            except:
                # TODO: do this better
                pass


        vid_out.close()
        # convert to video




    def stop(self):
        """
        just stop acquisition or streaming, but don't release all resources
        Returns:

        """

        self.quitting.set()


    def __del__(self):
        self.release()


    def release(self):
        # FIXME: Should check if finished writing to video before deleting tmp dir
        #os.rmdir(self.tmp_dir)
        # set quit flag to end stream thread if any.
        self.quitting.set()

        try:
            self.cam.DeInit()
            del self.cam
        except AttributeError:
            pass

        try:
            self.cam_list.Clear()
            del self.cam_list
        except AttributeError:
            pass

        self.system.ReleaseInstance()
