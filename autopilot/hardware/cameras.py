import threading
from subprocess import Popen, PIPE
import sys
import os
import csv
from skvideo import io
from datetime import datetime
import multiprocessing as mp
from tqdm.auto import tqdm
import inspect
import typing
import shutil

import time
import traceback
import blosc2 as blosc
import warnings
import subprocess

from queue import Queue, Empty, Full
import logging
from ctypes import c_char_p
import numpy as np

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

try:
    import picamera
    PICAMERA = True
except:
    PICAMERA = False

from autopilot import prefs
from autopilot.hardware import Hardware

OPENCV_LAST_INIT_TIME = mp.Value('d', 0.0)
"""
Time the last OpenCV camera was initialized (seconds, from time.time()).

v4l2 has an extraordinarily obnoxious ...feature -- 
if you try to initialize two cameras at ~the same time,
you will get a neverending stream of informative error messages: ``VIDIOC_QBUF: Invalid argument``

The workaround seems to be relatively simple, we just wait ~2 seconds if another camera was just initialized.
"""
LAST_INIT_LOCK = mp.Lock()

class Camera(Hardware):
    """
    Metaclass for Camera objects. Should not be instantiated on its own.

    Arguments:
        fps (int): Framerate of video capture
        timed (bool, int, float): If False (default), camera captures indefinitely. If int or float, captures for this many seconds
        rotate (int): Number of times to rotate image clockwise (default 0). Note that
            image rotation should happen in :meth:`._grab` or be otherwise implemented
            in each camera subclass, because it's a common enough operation many
            cameras have some optimized way of doing it.
        **kwargs: Arguments to :meth:`~Camera.stream`, :meth:`~Camera.write`, and :meth:`~Camera.queue` can be passed as dictionaries, eg.::

            stream={'to':'T', 'ip':'localhost'}

    When the camera is instantiated and :meth:`~.Camera.capture` is called,
    the class uses a series of methods that should be overwritten in subclasses.
    Further details for each can be found in the relevant method documentation.

    It is highly recommended to instantiate Cameras with a :attr:`.Hardware.name`,
    as it is used in :attr:`.output_filename` and to identify the network stream

    Three methods are required to be overwritten by all subclasses:

        * :meth:`~.Camera.init_cam` - **required** - used by :attr:`~.Camera.cam`, instantiating the camera object so that it can be queried and configured
        * :meth:`~.Camera._grab` - **required** - grab a frame from the :attr:`~.Camera.cam`
        * :meth:`~.Camera._timestamp` - **required** - get a timestamp for the frame

    The other methods are optional and depend on the particular camera:

        * :meth:`~.Camera.capture_init` - *optional* - any required routine to prepare the camera after it is instantiated but before it begins to capture
        * :meth:`~.Camera._process` - *optional* - the wrapper around a full acquisition cycle, including streaming, writing, and queueing frames
        * :meth:`~.Camera._write_frame` - *optional* - how to write an individual frame to disk
        * :meth:`~.Camera._write_deinit` - *optional* - any required routine to finish writing to disk after acquisition
        * :meth:`~.Camera.capture_deinit` - *optional* - any required routine to stop acquisition but not release the camera instance.

    Attributes:
        frame (tuple): The current captured frame as a tuple (timestamp, frame).
        shape (tuple): Shape of captured frames (height, width, channels)
        blosc (bool): If True (default), use blosc compression when
        cam: The object used to interact with the camera
        fps (int): Framerate of video capture
        timed (bool, int, float): If False (default), camera captures indefinitely. If int or float, captures for this many seconds
        q (Queue): Queue that allows frames to be pulled by other objects
        queue_size (int): How many frames should be buffered in the queue.
        initialized (threading.Event): Called in :meth:`~.init_cam` to indicate the camera has been initialized
        stopping (threading.Event): Called to signal that capturing should stop. when set, ends the threaded capture loop
        capturing (threading.Event): Set when camera is actively capturing
        streaming (threading.Event): Set to indicate that the camera is streaming data over the network
        writing (threading.Event): Set to indicate that the camera is writing video locally
        queueing (threading.Event): Indicates whether frames are being put into :attr:`~.Camera.q`
        indicating (threading.Event): Set to indicate that capture progress is being indicated in stdout by :class:`~tqdm.tqdm`


    """
    input = True #: test documenting input
    type = "CAMERA" #: (str): what are we anyway?
    trigger = False

    def __init__(self, fps=None, timed=False, crop=None, rotate:int=0, **kwargs):
        """

        Args:
            fps:
            timed:
            crop (tuple): (x, y of top left corner, width, height)
            **kwargs:
        """
        super(Camera, self).__init__(**kwargs)

        # internal attributes
        self._cam = None #: camera subobject test
        self._fps = None
        self._output_filename = None
        self._capture_thread = None
        self._writer = None
        self._write_q = None
        self._stream_q = None
        self._indicator = None
        self._resolution = None

        self.frame = None
        self.shape = None
        self.frame_n = 0
        self.crop = crop
        self.rotate = rotate

        self.blosc = True

        #self.fps = fps
        self.timed = timed

        self.q = None
        self.queue_size = None

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

        self.queueing = threading.Event()
        self.queueing.clear()

        self.indicating = threading.Event()
        self.indicating.clear()

        # initialize args passed by kwargs
        if 'stream' in kwargs.keys():
            self.stream(**kwargs['stream'])

        if 'write' in kwargs.keys():
            self.write(**kwargs['write'])

        if 'queue' in kwargs.keys():
            self.queue(**kwargs['queue'])

    def capture(self, timed = None):
        """
        Spawn a thread to begin capturing.

        Args:
            timed (None, int, float): if None, record according to :attr:`.timed` (default). If numeric, record for ``timed`` seconds.
        """


        if self.capturing.is_set():
            self.logger.warning("Already Capturing!")
            return

        if timed:
            self.timed = timed

        self.frame_n = 0

        self._capture_thread = threading.Thread(target=self._capture)
        self._capture_thread.setDaemon(True)
        self._capture_thread.start()

    def _capture(self):
        """
        Threaded capture method started by :meth:`.capture`.

        Captures until :attr:`.stopping` is set.

        Calls capture methods, in order:

        * :meth:`~.Camera.capture_init` - any required routine to prepare the camera after it is instantiated but before it begins to capture
        * :meth:`~.Camera._process`  - the wrapper around a full acquisition cycle, including streaming, writing, and queueing frames
        * :meth:`~.Camera._grab`  - grab a frame from the :attr:`~.Camera.cam`
        * :meth:`~.Camera._timestamp`  - get a timestamp for the frame
        * :meth:`~.Camera._write_frame`  - how to write an individual frame to disk
        * :meth:`~.Camera._write_deinit` - any required routine to finish writing to disk after acquisition
        * :meth:`~.Camera.capture_deinit` - any required routine to stop acquisition but not release the camera instance.
        """

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

                self.frame_n += 1

        finally:
            self.logger.info('Capture Ending')

            try:
                if self.streaming.is_set():
                    self.node.send(key='STATE', value='STOPPING')
                    self._stream_q.append('END')
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
        """
        A full frame capture cycle.

        :meth:`~Camera._grab`s the :attr:`.frame`, then handles streaming, writing, queueing, and indicating
        according to :meth:`~Camera.stream`, :meth:`~Camera.write`, :meth:`~Camera.queue`, and :attr:`~Camera.indicating`, respectively.

        """

        try:
            self.frame = self._grab()
        except Exception as e:
            self.logger.exception(e)

        if self.streaming.is_set():
            try:
                self._stream_q.append({'timestamp': self.frame[0],
                                           self.name  : self.frame[1]})
            except Full:
                self.logger.exception(f"queue was full for frame captured at {self.frame[0]}")

        if self.writing.is_set():
            self._write_frame()

        if self.queueing.is_set():
            self.q.put_nowait(self.frame)

        if self.indicating.is_set():
            if not self._indicator:
                self._indicator = tqdm()
            self._indicator.update()

    def stream(self, to='T', ip=None, port=None, min_size=5, **kwargs):
        """
        Enable streaming frames on capture.

        Spawns a :class:`~.networking.Net_Node` with :meth:`.Hardware.init_networking`,
        and creates a streaming queue with :meth:`.Net_Node.get_stream` according to args.

        Sets :attr:`.Camera.streaming`

        Args:
            to (str): ID of the recipient. Default 'T' for Terminal.
            ip (str): IP of recipient. If None (default), 'localhost'. If None and ``to`` is 'T', ``prefs.get('TERMINALIP')``
            port (int, str): Port of recipient socket. If None (default), ``prefs.get('MSGPORT')``. If None and ``to`` is 'T', ``prefs.get('TERMINALPORT')``.
            min_size (int): Number of frames to collect before sending (default: 5). use 1 to send frames as soon as they are available,
                sacrificing the efficiency from compressing multiple frames together
            **kwargs: passed to :meth:`.Hardware.init_networking` and thus to :class:`.Net_Node`

        """


        if to=='T':
            if not ip:
                ip = prefs.get('TERMINALIP')
            if not port:
                port = prefs.get('TERMINALPORT')

        else:

            if not ip:
                self.logger.warning('ip not passed, using localhost as default')
                ip = 'localhost'
            if not port:
                self.logger.warning('port not passed, using prefs.get(\'MSGPORT\')')
                port = prefs.get('MSGPORT')


        self.listens = {
            'START': self.l_start,
            'STOP': self.l_stop
        }

        self.init_networking(listens=self.listens, **kwargs)

        if prefs.get( 'SUBJECT'):
            subject = prefs.get('SUBJECT')
        else:
            self.logger.warning('nothing found for prefs.get(\'SUBJECT\'), probably running outside of task context')
            subject = None

        self._stream_q = self.node.get_stream(
            'stream', 'CONTINUOUS', upstream=to,
            ip=ip, port=port, subject=subject,
            min_size=min_size
        )

        self.streaming.set()

    def l_start(self, val):
        """
        Begin capturing by calling :meth:`Camera.capture`

        Args:
            val: unused
        """
        self.capture()

    def l_stop(self, val):
        """
        Stop capture by calling :meth:`Camera.release`

        Args:
            val: unused
        """
        self.release()



    def write(self, output_filename = None, timestamps=True, blosc=True):
        """
        Enable writing frames locally on capture

        Spawns a :class:`.Video_Writer` to encode video, sets :attr:`.writing`

        Args:
            output_filename (str): path and filename of the output video. extension should be ``.mp4``,
                as videos are encoded with libx264 by default.
            timestamps (bool): if True, (timestamp, frame) tuples will be put in the :attr:`._write_q`.
                if False, timestamps will be generated by :class:`.Video_Writer` (not recommended at all).
            blosc (bool): if true, compress frames with :func:`blosc.pack_array` before putting in :attr:`._write_q`.
        """
        if output_filename is None:
            output_filename = self.output_filename
        else:
            self._output_filename = output_filename

        self.blosc = blosc
        self._write_q = mp.Queue()
        self.writer = Video_Writer(self._write_q, output_filename, self.fps, timestamps=timestamps, blosc=blosc)
        self.writer.start()
        self.writing.set()
        self.logger.info('Writing initialized, writing to {}'.format(output_filename))

    def _write_frame(self):
        """
        Put :attr:`.frame` into the :attr:`._write_q`, optionally compressing it with :func:`blosc.pack_array`
        """
        try:
            if self.blosc:
                self._write_q.put_nowait((self.frame[0], blosc.pack_array(self.frame[1])))
            else:
                self._write_q.put_nowait(self.frame)
        except Full:
            self.logger.exception('Frame {} could not be written, queue full'.format(self.frame_n))



    def _write_deinit(self):
        """
        End the :class:`.Video_Writer`.

        Blocks until the :attr:`._write_q` is empty, holding the release of the object.
        """
        self._write_q.put_nowait('END')
        checked_empty = False
        while not self._write_q.empty():
            if not checked_empty:
                self.logger.warning(
                    'Writer still has ~{} frames, waiting on it to finish'.format(self._write_q.qsize()))
                checked_empty = True
            time.sleep(0.1)
        self.logger.info('Writer finished, closing')

    def queue(self, queue_size = 128):
        """
        Enable stashing frames in a queue for a local consumer.

        Other objects can get frames as they are acquired from :attr:`.q`

        Args:
            queue_size (int): max number of frames that can be held in :attr:`~Camera.q`
        """
        self.queue_size = queue_size
        self.q = Queue(maxsize=self.queue_size)
        self.queueing.set()
        self.logger.info('Queueing initialized, queue size {}'.format(queue_size))


    @property
    def cam(self):
        """
        Camera object.

        If :attr:`._cam` hasn't been initialized yet, use :meth:`.init_cam` to do so

        Returns:
            Camera object, different for each camera.
        """
        if not self._cam:
            self._cam = self.init_cam()
        return self._cam

    @property
    def output_filename(self):
        """
        Filename given to video writer.

        If explicitly set, returns as expected.

        If None, or path already exists while the camera isn't capturing,
        a new filename is generated in the user directory.

        Returns:
            (str) :attr:`._output_filename`

        """
        # TODO: choose output directory

        new = False
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

    @output_filename.setter
    def output_filename(self, output_filename):
        self._output_filename = output_filename

    @property
    def resolution(self):
        return self._resolution

    @resolution.setter
    def resolution(self, resolution):
        self._resolution = resolution

    @property
    def fps(self):
        return self._fps

    @fps.setter
    def fps(self, fps):
        self._fps = fps

    def _grab(self):
        """
        Capture a frame and timestamp.

        Method must be overridden by subclass

        Returns:
            (str, :class:`numpy.ndarray`) Tuple of isoformatted (str) or numeric timestamp returned by :meth:`._timestamp`,
                and captured frame
        """
        raise Exception("internal _grab method must be overwritten by camera subclass!!")

    def _timestamp(self, frame=None):
        """
        Generate a timestamp for each :meth:`~Camera._grab`

        Must be overridden by subclass

        Args:
            frame: If needed by camera subclass, pass the frame or image object to get timestamp

        Returns:
            (str, int, float) Either an isoformatted (str) or numeric timestamp

        """
        raise Exception("internal _timestamp method must be overwritten by camera subclass!!")


    def init_cam(self):
        """
        Method to initialize camera object

        Must be overridden by camera subclass

        Returns:
            camera object

        """
        raise Exception('init_cam must be overwritten by camera subclass!!')

    def capture_init(self):
        """
        Optional: Prepare :attr:`.cam` after initialization, but before capture

        Returns:
            None
        """
        pass

    def capture_deinit(self):
        """
        Optional: Return :attr:`.cam` to an idle state after capturing, but before releasing

        Returns:
            None
        """

    def stop(self):
        """
        Stop capture by setting  :attr:`.stopping`
        """
        self.stopping.set()

    def release(self):
        """
        Release resources held by Camera.

        Must be overridden by subclass.

        Does not raise exception in case some general camera release logic should be put here...
        """

        pass
        # raise Exception('release must be overwritten by camera subclass!!')


class PiCamera(Camera):
    """
    Interface to the `Raspberry Pi Camera Module <https://www.raspberrypi.org/products/camera-module-v2/>`_
    via `picamera <https://picamera.readthedocs.io/en/latest/>`_

    Parameters of the :class:`picamera.PiCamera` class can be set after initialization by modifying the
    :attr:`PiCamera.cam` attribute, eg ``PiCamera().cam.exposure_mode = 'fixedfps'`` -- see the
    :class:`picamera.PiCamera` documentation for full documentation.

    Note that some parameters, like resolution, can't be changed after starting :meth:`~PiCamera.capture` .

    The Camera Module is a slippery little thing, and ``fps`` and ``resolution`` are just requests
    to the camera, and aren't necessarily followed with 100% fidelity. The possible framerates and resolutions
    are determined by the ``sensor_mode`` parameter, which by default tries to guess the best
    sensor mode based on the fps and resolution. See the :ref:`picamera:camera_modes` documentation for
    more details.

    This wrapper uses a subclass, :class:`PiCamera.PiCamera_Writer` to capture frames decoded by the
    gpu directly from the preallocated buffer object. Currently the restoration from the buffer
    assumes that RGB, or generally ``shape[2] == 3``, images are being captured. See
    `this stackexchange post <https://raspberrypi.stackexchange.com/a/58941/112948>`_ by Dave Jones, author
    of the picamera module, for a strategy for capturing grayscale images quickly.

    This class also currently uses the default :class:`Video_Writer` object, but it could be
    more performant to use the :meth:`picamera.PiCamera.start_recording` method's built-in ability
    to record video to a file --- try it out!

    .. todo::

        Currently timestamps are constructed with :meth:`datetime.datetime.now.isoformat`, which is
        not altogether accurate. Timestamps should be gotten from the :attr:`~picamera.PiCamera.frame` attribute,
        which depends on the :attr:`~picamera.PiCamera.clock_mode`


    References:
        - https://blog.robertelder.org/recording-660-fps-on-raspberry-pi-camera/
        - Fast capture from the author of picamera - https://raspberrypi.stackexchange.com/a/58941/112948
        - More on fast capture and processing, see last example in section - https://picamera.readthedocs.io/en/release-1.12/recipes2.html#rapid-capture
    """

    def __init__(self, camera_idx:int=0, sensor_mode:int=0,
                 resolution:typing.Tuple[int,int] = (1280,720),
                 fps:int=30,
                 format:str='rgb',
                 *args, **kwargs):
        """
        Args:
            camera_idx (int): Index of picamera (default: 0, >=1 only supported on compute module)
            sensor_mode (int): Sensor mode, default 0 detects automatically from resolution and fps,
                note that sensor_mode will affect the available resolutions and framerates,
                see :ref:`picamera:camera_modes` for more information
            resolution (tuple): a tuple of (width, height) integers, but mind the note in the above documentation
                regarding the sensor_mode property and resolution
            fps (int): frames per second, but again mind the note on sensor_mode
            format (str): Format passed to :class`picamera.PiCamera.start_recording` one of ``('rgb' (default), 'grayscale')``
                The ``'grayscale'`` format uses the ``'yuv'`` format, and extracts the luminance channel
            *args (): passed to superclass
            **kwargs (): passed to superclass
        """
        super(PiCamera, self).__init__(*args, **kwargs)

        if not globals()['PICAMERA']:
            nopicam = 'the picamera package could not be imported, install it before use!'
            self.logger.exception(nopicam)
            raise ImportError(nopicam)

        self._sensor_mode = None
        self._cam = None
        self._picam_writer = None

        self.camera_idx = camera_idx
        self.sensor_mode = sensor_mode
        self.resolution = resolution
        self.fps = fps
        self.format = format
        self.rotation = self.rotate * 90

    @property
    def sensor_mode(self) -> int:
        """
        Sensor mode, default 0 detects automatically from resolution and fps,
        note that sensor_mode will affect the available resolutions and framerates,
        see :ref:`picamera:camera_modes` for more information.

        When set, if the camera has been initialized, will change the attribute in :attr:`PiCamera.cam`

        Returns:
            int
        """
        return self._sensor_mode

    @sensor_mode.setter
    def sensor_mode(self, sensor_mode: int):
        self._sensor_mode = sensor_mode
        if self.initialized.is_set():
            self.cam.sensor_mode = self._sensor_mode

    @property
    def resolution(self) -> typing.Tuple[int, int]:
        """
        A tuple of ints, (width, height).

        Resolution can't be changed while the camera is capturing.

        See :ref:`picamera:camera_modes` for more information re: how resolution relates to
        :attr:`picamera.PiCamera.sensor_mode`

        Returns:
            tuple of ints, (width, height)
        """
        return self._resolution

    @resolution.setter
    def resolution(self, resolution: typing.Tuple[int, int]):
        self._resolution = resolution
        if self._picam_writer is not None:
            self._picam_writer.resolution = self._resolution
        if self.initialized.is_set() and not self.capturing.is_set():
            self.cam.resolution = self._resolution
        elif self.capturing.is_set():
            self.logger.warning('cant set resolution while camera is capturing!')

    @property
    def fps(self) -> int:
        """
        Frames per second

        See :ref:`picamera:camera_modes` for more information re: how fps relates to
        :attr:`picamera.PiCamera.sensor_mode`

        Returns:
            int - fps
        """
        return self._fps

    @fps.setter
    def fps(self, fps):
        self._fps = fps
        if self.initialized.is_set():
            self.cam.framerate = self._fps

    @property
    def rotation(self) -> int:
        """
        Rotation of the captured image, derived from :attr:`.Camera.rotate` * 90.

        Must be one of ``(0, 90, 180, 270)``

        Rotation can be changed during capture

        Returns:
            int - Current rotation
        """
        return self._rotation

    @rotation.setter
    def rotation(self, rotation:int):
        rotation = int(round(rotation))
        if rotation not in (0, 90, 180, 270):
            errmsg = f"rotation must be 0, 90, 180, or 270, got {rotation}"
            self.logger.exception(errmsg)
            raise ValueError(errmsg)

        self._rotation = rotation
        if self.initialized.is_set():
            self.cam.rotation = self._rotation

    def init_cam(self) -> 'picamera.PiCamera':
        """
        Initialize and return the :class:`picamera.PiCamera` object.

        Uses the stored :attr:`~PiCamera.camera_idx`, :attr:`~PiCamera.resolution`,
        :attr:`~PiCamera.fps`, and :attr:`~PiCamera.sensor_mode` attributes on init.

        Returns:
            :class:`picamera.PiCamera`
        """

        cam = picamera.PiCamera(
            camera_num=self.camera_idx,
            resolution=self.resolution,
            framerate=self.fps,
            sensor_mode=self.sensor_mode,
        )
        cam.rotation = self._rotation

        self.initialized.set()

        return cam

    def capture_init(self):
        """
        Spawn a :class:`PiCamera.PiCamera_Writer` object to :attr:`PiCamera._picam_writer`
        and :meth:`~picamera.PiCamera.start_recording` in the set :attr:`~PiCamera.format`
        """
        self._picam_writer = self.PiCamera_Writer(self.resolution, self.format)
        format = self.format
        if format == "grayscale":
            format = 'yuv'

        self.cam.start_recording(self._picam_writer, format)

    def _grab(self) -> typing.Tuple[str, np.ndarray]:
        """
        Wait on the :attr:`~PiCamera.PiCamera_Writer.grab_event` to be set,
        then clear it before returning the frame.

        Returns:
            (timestamp, frame) tuple
        """
        # wait until a new frame is captured
        self._picam_writer.grab_event.wait()
        ret = (self._picam_writer.timestamp, self._picam_writer.frame)
        self._picam_writer.grab_event.clear()
        return ret

    def capture_deinit(self):
        """
        :meth:`~picamera.PiCamera.stop_recording` and :meth:`~picamera.PiCamera.close` the camera,
        releasing its resources.
        """
        self.cam.stop_recording()
        # self.cam.close()

    def release(self):
        self._picam_writer.grab_event.clear()
        super(PiCamera, self).release()
        self._picam_writer.grab_event.clear()
        try:
            self.cam.close()
        except KeyError as e:
            self.logger.debug(f"Exception closing picamera: {e}")

        self._cam = None

    class PiCamera_Writer(object):
        """
        Writer object for processing individual frames,
        see: https://raspberrypi.stackexchange.com/a/58941/112948
        """
        def __init__(self, resolution:typing.Tuple[int, int], format:str="rgb"):
            """
            Args:
                resolution (tuple): (width, height) tuple used when making numpy array from buffer

            Attributes:
                grab_event (:class:`threading.Event`): Event set whenever a new frame is captured,
                    cleared by the parent class when the frame is consumed.
                frame (:class:`numpy.ndarray`): Captured frame
                timestamp (str): Isoformatted timestamp of time of capture.

            """
            self.resolution = resolution
            self._block_resolution = (
                self.resolution[0]+ 31 // 32 * 32,
                self.resolution[1] + 15 // 16 * 16
            )
            self.format = format
            self.grab_event = threading.Event()
            self.grab_event.clear()
            self.frame = None
            self.timestamp = None

        def write(self, buf):
            """
            Reconstutute the buffer into a numpy array in :attr:`PiCamera_Writer.frame` and
            make a timestamp in :attr:`PiCamera_Writer.timestamp`, then set the :attr:`PiCamera_Writer.grab_event`

            Args:
                buf (): Buffer given by PiCamera
            """
            if self.format == 'grayscale':
                # just capture the luminance channel. see
                # https://raspberrypi.stackexchange.com/a/58941/112948
                # and
                # https://raspberrypi.stackexchange.com/a/58941/112948
                self.frame = np.frombuffer(
                    buf, dtype=np.uint8,
                    count=self._block_resolution[0]*self._block_resolution[1]
                ).reshape((self._block_resolution[1],self._block_resolution[0]))[:self.resolution[1], :self.resolution[0]]
            else:
                self.frame = np.frombuffer(
                    buf, dtype=np.uint8,
                    count=self.resolution[0]*self.resolution[1]*3
                ).reshape((self.resolution[1], self.resolution[0], 3))
            self.timestamp = datetime.now().isoformat()
            self.grab_event.set()








class Camera_CV(Camera):
    def __init__(self, camera_idx = 0, **kwargs):
        """
        Capture Video from a webcam with OpenCV

        By default, OpenCV will select a suitable backend for the indicated camera. Some backends have difficulty
        operating multiple cameras at once, so the performance of this class will be variable depending on camera
        type.

        .. note::

            OpenCV must be installed to use this class! A Prebuilt opencv binary is available for the raspberry pi,
            but it doesn't take advantage of some performance-enhancements available to OpenCV. Use
            ``autopilot.setup.run_script opencv`` to compile OpenCV with these enhancements.

        If your camera isn't working and you're using v4l2, to print debugging information you can run::

            # set the debug log level
            echo 3 > /sys/class/video4linux/videox/dev_debug

            # check logs
            dmesg

        Args:
            camera_idx (int): The index of the desired camera
            **kwargs: Passed to the :class:`.Camera` metaclass.

        Attributes:
            camera_idx (int): The index of the desired camera
            last_opencv_init (float): See :data:`~cameras.OPENCV_LAST_INIT_TIME`
            last_init_lock (:class:`threading.Lock`): Lock for setting :attr:`.last_opencv_init`
        """
        if not globals()['OPENCV']:
            ImportError('opencv was not imported, and is required for Camera_CV')

        super(Camera_CV, self).__init__(**kwargs)

        self._v4l_info = None

        self.last_opencv_init = globals()['OPENCV_LAST_INIT_TIME']
        self.last_init_lock = globals()['LAST_INIT_LOCK']

        self.camera_idx = camera_idx

    @property
    def fps(self):
        """
        Attempts to get FPS with ``cv2.CAP_PROP_FPS``, uses 30fps as a default

        Returns:
            int: framerate
        """
        fps = self.cam.get(cv2.CAP_PROP_FPS)
        if fps == 0:
            fps = 30
            warnings.warn('Couldnt get fps from camera, using {} as default'.format(fps))
        return fps

    @property
    def shape(self):
        """
        Attempts to get image shape from ``cv2.CAP_PROP_FRAME_WIDTH`` and ``HEIGHT``
        Returns:
            tuple: (width, height)
        """
        if self.crop:
            return (self.crop[2], self.crop[3])
        else:
            return (self.cam.get(cv2.CAP_PROP_FRAME_WIDTH),
                    self.cam.get(cv2.CAP_PROP_FRAME_HEIGHT))

    @shape.setter
    def shape(self, shape):
        """
        Do nothing
        """
        pass

    def _grab(self):
        """
        Reads a frame with :meth:`.cam.read`

        Returns:
            tuple: (timestamp, frame)
        """
        ret, frame = self.cam.read()
        if not ret:
            return False, False
        ts = self._timestamp()
        if self.crop:
            frame = frame[self.crop[1]:self.crop[1]+self.crop[3], self.crop[0]:self.crop[0]+self.crop[2]]

        return (ts, np.rot90(frame, axes=(1,0), k=self.rotate))

    def _timestamp(self, frame=None):
        """
        Attempts to get timestamp with ``cv2.CAP_PROP_POS_MSEC``.
        Frame does not need to be passed to this method, as
        timestamps are retrieved from :attr:`.cam`

        .. todo::

            Convert this float timestamp to an isoformatted system timestamp

        Returns:
            float: milliseconds since capture start
        """
        return self.cam.get(cv2.CAP_PROP_POS_MSEC)

    @property
    def backend(self):
        """
        capture backend used by OpenCV for this camera

        Returns:
            str: name of capture backend used by OpenCV for this camera
        """
        return self.cam.getBackendName()

    def init_cam(self):
        """
        Initializes OpenCV Camera

        To avoid overlapping resource allocation requests,
        checks the last time any :class:`.Camera_CV` object was instantiated
        and makes sure it has been at least 2 seconds since then.

        Returns:
            :class:`cv2.VideoCapture`: camera object
        """
        self.initialized.set()

        with self.last_init_lock:
            time_since_last_init = time.time() - self.last_opencv_init.value
            if time_since_last_init < 2.:
                time.sleep(2.0 - time_since_last_init)
            vid = cv2.VideoCapture(self.camera_idx)
            self.last_opencv_init.value = time.time()

        self.logger.info("Camera Initialized")

        return vid

    def release(self):
        self.stop()
        self.cam.release()
        self._cam = None
        self.initialized.clear()
        super(Camera_CV, self).release()


    @property
    def v4l_info(self):
        """
        Device information from ``v4l2-ctl``

        Returns:
            dict: Information for all devices available through v4l2
        """
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

    type="CAMERA_SPIN"

    # only create class attributes if pyspin is detected,
    # otherwise can't import this module without having pyspin


    ATTR_TYPES = {} #: Conversion from data types to pointer types
    ATTR_TYPE_NAMES = {} #: Conversion from data types to human-readable names
    RW_MODES = {} #: Conversion from read/write mode to {'read':bool, 'write':bool} descriptor

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


    def __init__(self, serial=None, camera_idx=None, **kwargs):
        """
        Capture video from a FLIR brand camera with the Spinnaker SDK.

        Args:
            serial (str): Serial number of desired camera
            camera_idx (int): If no serial provided, select camera by index. Using ``serial`` is HIGHLY RECOMMENDED.
            **kwargs: passed to :class:`.Camera` metaclass

        .. note::

            PySpin and the Spinnaker SDK must be installed to use this class. Please use the
            ``install_pyspin.sh`` script in ``setup``

        See the documentation for the Spinnaker SDK and PySpin here:

        `<https://www.flir.com/products/spinnaker-sdk/>`_



        Attributes:
            serial (str): Serial number of desired camera
            camera_idx (int): If no serial provided, select camera by index. Using ``serial`` is HIGHLY RECOMMENDED.
            system (:class:`PySpin.System`): The PySpin System object
            cam_list (:class:`PySpin.CameraList`): The list of PySpin Cameras available to the system
            nmap: A reference to the nodemap from the GenICam XML description of the device
            base_path (str): The directory and base filename that images will be written to if object is :attr:`.writing`. eg::

                base_path = '/home/user/capture_directory/capture_'
                image_path = base_path + 'image1.png'

            img_opts (:class:`PySpin.PNGOption`): Options for saving .png images, made by :meth:`~Camera_Spinnaker.write`
        """

        if not PYSPIN:
            raise ImportError('PySpin was not imported, and is required for Camera_Spinnaker')



        self.system = None #spinnaker system
        self.cam_list = None
        self.nmap = None

        self.base_path = None
        self.img_opts = None

        # internal variables
        self._bin = None
        self._exposure = None
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

        if serial and camera_idx:
            self.logger.warning("serial and camera_idx were both passed, defaulting to serial")
            camera_idx = None

        if isinstance(serial, float) or isinstance(serial, int):
            serial = str(serial)
        self.serial = serial
        self.camera_idx = camera_idx



        # set passed parameters
        # has to be done in a specific order, as they are mutually dependent.
        # eg. exposure depends on fps, which depends on bin, etc.
        if 'pixel_format' in kwargs.keys():
            self.set('PixelFormat', kwargs['pixel_format'])
        else:
            try:
                self.set('PixelFormat', PySpin.PixelFormat_Mono8)
            except:
                pass

        if 'bin' in kwargs.keys():
            self.bin = kwargs['bin']
        if 'fps' in kwargs.keys():
            self.fps = kwargs['fps']

        if 'acquisition_mode' in kwargs.keys():
            self.set('AcquisitionMode', kwargs['acquisition_mode'])
        else:
            self.acquisition_mode = 'continuous'



    def init_cam(self):
        """
        Initialize the Spinnaker Camera

        Initializes the camera, system, cam_list, node map, and the camera methods and
        attributes used by :meth:`~Camera_Spinnaker.get` and :meth:`~Camera_Spinnaker.set`

        Returns:
            :class:`PySpin.Camera`: The Spinnaker camera object
        """

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
        """
        Prepare the camera for acquisition

        calls the camera's ``BeginAcquisition`` method and populate :attr:`.shape`
        """


        self.cam.BeginAcquisition()
        self.frame = self._grab()
        # FIXME: I think this will break single-shot or multishot modes.
        self.shape = self.frame[1].GetNDArray().shape


    def capture_deinit(self):
        """
        De-initializes the camera after acquisition
        """
        self.cam.EndAcquisition()

    def _process(self):
        """
        Modification of the :meth:`.Camera._process` method for Spinnaker cameras

        Because the objects returned from the :meth:`~Camera_Spinnaker._grab` method are image *pointers*
        rather than :class:`numpy.ndarray`s, they need to be handled differently.

        More details on the differences are given in the :meth:`_write_frame`,
        """
        frame_array = None
        try:
            self.frame = self._grab()
        except Exception as e:
            self.logger.exception(e)

        #self._frame[:] = self.frame[1].GetNDArray()

        if self.writing.is_set():
            self._write_frame()

        if self.streaming.is_set():
            if not frame_array:
                frame_array = np.rot90(self.frame[1].GetNDArray(), axes=(1,0), k=self.rotate)
            self._stream_q.append({'timestamp': self.frame[0],
                                       self.name  : frame_array})

        if self.queueing.is_set():
            if not frame_array:
                frame_array = np.rot90(self.frame[1].GetNDArray(), axes=(1,0), k=self.rotate)
            self.q.put_nowait((self.frame[0], frame_array))

        if self.indicating.is_set():
            if self._indicator is None:
                self._indicator = tqdm()
            self._indicator.update()


        self.frame[1].Release()

    def _grab(self):
        """
        Get next timestamp and PySpin Image

        Returns:
            tuple: (timestamp, :class:`PySpin.Image`)
        """
        img = self.cam.GetNextImage()
        return (self._timestamp(img), img)

    def _timestamp(self, frame=None):
        """
        Get the timestamp from the passed image

        Args:
            frame (:class:`PySpin.Image`): Currently grabbed image

        Returns:
            float: PySpin timestamp
        """
        return frame.GetTimeStamp()


    def write(self, output_filename = None, timestamps=True, blosc=True):
        """
        Sets camera to save acquired images to a directory for later encoding.

        For performance, rather than encoding during acquisition, save each image as
        a (lossless) .png image in a directory generated by :attr:`.output_filename`.

        After capturing is complete, a :class:`.Directory_Writer` encodes the images to an
        x264 encoded .mp4 video.

        Args:
            output_filename (str): Directory to write images to. If None (default), generated by :attr:`.output_filename`
            timestamps (bool): Not used, timestamps are always appended to filenames.
            blosc (bool): Not used, images are directly saved.
        """
        if not output_filename:
            output_filename = self.output_filename
        else:
            self.output_filename = output_filename


        # PNG images are losslessly compressed
        self.img_opts = PySpin.PNGOption()
        self.img_opts.compressionLevel = 1

        # make directory
        output_dir = os.path.splitext(self.output_filename)[0]
        os.makedirs(output_dir)

        # create base_path for output images
        self.base_path = os.path.join(output_dir, "capture_{}__".format(self.name))

        self.writing.set()


    def _write_frame(self):
        """
        Write frame to :attr:`.base_path` + timestamp + '.png' with :meth:`PySpin.Image.Save`
        """
        self.frame[1].Save(self.base_path+str(self.frame[0])+'.png', self.img_opts)


    def _write_deinit(self):
        """
        After capture, write images in :attr:`.base_path` to video with :class:`.Directory_Writer`

        Camera object will remain open until writer has finished.
        """
        self.logger.info('Writing images in {} to {}'.format(self.base_path, self.base_path + '.mp4'))
        self.writer = Directory_Writer(self.base_path, fps=self.fps)
        self.writer.encode()

    @property
    def bin(self):
        """
        Camera Binning.

        Attempts to bin on-device, and use averaging if possible. If averaging not available,
        uses summation.

        Args:
            tuple: tuple of integers, (Horizontal, Vertical binning)

        Returns:
            tuple: (Horizontal, Vertical binning)
        """
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
        """
        Set Exposure of camera

        Can be set with

        * ``'auto'`` - automatic exposure control. note that this will limit framerate
        * ``float`` from 0-1 - exposure duration proportional to fps. eg. if fps = 10, setting exposure = 0.5 means exposure will be set as 50ms
        * ``float`` or ``int``  >1 - absolute exposure time in microseconds

        Returns:
            str, float: If exposure has been set, return set value. Otherwise return ``.get('ExposureTime')``
        """
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

            try:
                self.set('GainAuto', 'Off')
                self.set('Gain', 1)
            except Exception as e:
                self.logger.exception(e)


            self.cam.ExposureAuto.SetValue(PySpin.ExposureAuto_Off)
            # self.cam.ExposureMode.SetValue(PySpin.ExposureMode_Timed)
            self.cam.ExposureTime.SetValue(exposure)
            self._exposure = exposure
        else:
            self.logger.exception('Dont know how to set exposure {}'.format(exposure))


    @property
    def fps(self):
        """
        Acquisition Framerate

        Set with integer. If set with None, ignored (superclass sets FPS to None on init)

        Returns:
            int: from ``cam.AcquisitionFrameRate.GetValue()``
        """
        return self.cam.AcquisitionFrameRate.GetValue()

    @fps.setter
    def fps(self, fps):
        if isinstance(fps, int):
            #self.cam.AcquisitionFrameRateEnable.SetValue(True)
            #self.cam.AcquisitionFrameRate.SetValue(fps)
            self.set('AcquisitionFrameRateAuto', 'Off')
            self.set('AcquisitionFrameRateEnable',True)
            self.set('AcquisitionFrameRate',fps)

        elif fps is None:
            # initially set to None on superclass init
            pass
        else:
            self.logger.exception('Need to set FPS with an integer')

    @property
    def frame_trigger(self):
        """
        Set camera to lead or follow hardware triggers

        If ``'lead'``, Camera will send TTL pulses from Line 2.

        If ``'follow'``, Camera will follow triggers from Line 3.

        .. seealso::

            * `<https://www.flir.com/support-center/iis/machine-vision/application-note/configuring-synchronized-capture-with-multiple-cameras>`_
            * `<https://www.flir.com/support-center/iis/machine-vision/knowledge-base/what-external-iidc-trigger-modes-are-supported-by-my-camera/>`_
        """

        return self._frame_trigger

    @frame_trigger.setter
    def frame_trigger(self, frame_trigger):

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

        self._frame_trigger = frame_trigger

    @property
    def acquisition_mode(self):
        """
        Image acquisition mode

        One of

        * ``'continuous'`` - continuously acquire frame camera
        * ``'single'`` - acquire a single frame
        * ``'multi'`` - acquire a finite number of frames.

        .. warning::

            Only ``'continuous'`` has been tested.
        """
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
        """
        All device attributes that are currently readable with :meth:`~Camera_Spinnaker.get`

        Returns:
            dict: A dictionary of attributes that are readable and their current values
        """
        if not self._readable_attributes:

            for k, v in self._camera_attributes.items():
                if '_' in k:
                    continue
                if PySpin.IsReadable(v):
                    self._readable_attributes[k] = self.get(k)

        return self._readable_attributes

    @property
    def writable_attributes(self):
        """
        All device attributes that are currently writeable wth :meth:`~Camera_Spinnaker.set`

        Returns:
            dict: A dictionary of attributes that are writeable and their current values
        """
        if not self._writable_attributes:
            for k, v in self._camera_attributes.items():
                if '_' in k:
                    continue
                if PySpin.IsWritable(v):
                    self._writable_attributes[k] = self.get(k)

        return self._writable_attributes


    def get(self, attr):
        """
        Get a camera attribute.

        Any value in :attr:`.readable_attributes` can be read. Attempts to get numeric values
        with ``.GetValue``, otherwise gets a string with ``.ToString``, so be cautious with types.

        If ``attr`` is a method (ie. in ``._camera_methods``, execute the method and return the value

        Args:
            attr (str): Name of a readable attribute or executable method

        Returns:
            float, int, str: Value of ``attr``
        """
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
        """
        Set a camera attribute

        Any value in :attr:`.writeable_attributes` can be set. If attribute has a ``.SetValue`` method,
        (ie. accepts numeric values), attempt to use it, otherwise use ``.FromString``.

        Args:
            attr (str): Name of attribute to be set
            val (str, int, float): Value to set attribute
        """
        if self.cam:
            # checking ensures we have camera initialized
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
                self.logger.exception('Not sure what to do with attr: {}, value: {}'.format(attr, val))

        # else:
        #
        #     self.__setattr__(attr, val)


    def list_options(self, name):
        """
        List the possible values of a camera attribute.

        Args:
            name (str): name of attribute to query

        Returns:
            dict: Dictionary with {available options: descriptions}
        """
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
        Get all information about the camera

        Note that this is distinct from camera *attributes* like fps, instead
        this is information like serial number, version, firmware revision, etc.

        Returns:
            dict: {feature name: feature value}
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
        """
        Release all PySpin objects and wait on writer, if still active.
        """

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




#
# class Camera_Picam(Camera):
#     """
#     also can be used w/ picapture
#     https://lintestsystems.com/wp-content/uploads/2016/09/PiCapture-SD1-Documentation.pdf
#     """
#     pass

#
# class FastWriter(io.FFmpegWriter):
#     def __init__(self, *args, **kwargs):
#         super(FastWriter, self).__init__(*args, **kwargs)
#
#
#     def writeFrame(self, im):
#         """Sends ndarray frames to FFmpeg
#         """
#         vid = vshape(im)
#
#         if not self.warmStarted:
#             T, M, N, C = vid.shape
#             self._warmStart(M, N, C, im.dtype)
#
#         #vid = vid.clip(0, (1 << (self.dtype.itemsize << 3)) - 1).astype(self.dtype)
#
#         try:
#             self._proc.stdin.write(vid.tostring())
#         except IOError as e:
#             # Show the command and stderr from pipe
#             msg = '{0:}\n\nFFMPEG COMMAND:\n{1:}\n\nFFMPEG STDERR ' \
#                   'OUTPUT:\n'.format(e, self._cmd)
#             raise IOError(msg)


class Directory_Writer(object):
    IMG_EXTS = ('.png', '.jpg')
    def __init__(self, dir, fps, ext='.png', ffmpeg_bin='ffmpeg'):
        """
        Encode a directory of images to video with ffmpeg

        Images should be named such that they are machine-orderable, eg.::

            # this
            img-001.png, img-002.png, ... img-010.png

            # not this
            img-1.png, img-2.png, ... img-10.png

        Encoding settings are:

        * ``pix_fmt``: ``yuv420p``
        * ``vcodec`` : ``libx264``
        * ``preset``: ``veryfast``

        .. note::

            ffmpeg must be installed to use this object

        Args:
            dir (str): directory of images to encode
            fps (int): framerate of output video
            ext (str): extension of input images
            ffmpeg_bin (str): ffmpeg binary to use, default is to use ffmpeg in ``$PATH``,
                otherwise specific binary can be specified.
        """

        _check_ffmpeg()

        self.dir = dir
        self.fps = fps
        self.ext = ext
        self.ffmpeg_bin = ffmpeg_bin

        self.encode_thread = None

    def encode(self):
        """
        Begin encoding.

        calls :meth:`._encode` in a thread.

        Encoding calls ffmpeg with a glob string like::

            self.dir + '*' + self.ext
        """
        self.encode_thread = threading.Thread(target=self._encode)
        self.encode_thread.start()

    def _encode(self):

        glob_str = os.path.join(self.dir.rstrip(os.sep)+ '*'+self.ext)

        ffmpeg_cmd = [self.ffmpeg_bin, "-y", '-r', str(self.fps),
                      '-pattern_type', 'glob', '-i', glob_str,
                      '-pix_fmt', 'yuv420p', '-r', str(self.fps),
                      '-vcodec', 'libx264', '-preset', 'veryfast',
                      self.dir.rstrip(os.sep).rstrip('__')+'.mp4']

        result = subprocess.call(ffmpeg_cmd)
        return result

    def wait(self):
        """
        ``.join`` the encoding thread.
        """
        if self.encode_thread:
            self.encode_thread.join()



class Video_Writer(mp.Process):
    def __init__(self, q, path, fps=None, timestamps=True, blosc=True):
        """
        Encode frames as they are acquired in a separate process.

        Must call :meth:`~Video_Writer.start` after initialization to begin encoding.

        Encoding continues until 'END' is put in :attr:`~Video_Writer.q`.

        Timestamps are saved in a .csv file with the same path as the video.

        Args:
            q (:class:`~queue.Queue`): Queue into which frames will be dumped
            path (str): output path of video
            fps (int): framerate of output video
            timestamps (bool): if True (default), input will be of form (timestamp, frame). if False,
                input will just be frames and timestamps will be generated as the frame is encoded (**not recommended**)
            blosc (bool): if True, frames in the :attr:`~Video_Writer.q` will be compresed with blosc. if False, uncompressed

        Attributes:
            timestamps (list): Timestamps for frames, written to .csv on completion of encoding

        """

        super(Video_Writer, self).__init__()

        _check_ffmpeg()


        self.q = q
        self.path = path
        self.fps = fps
        self.given_timestamps = timestamps
        self.timestamps = []
        self.blosc = blosc


        if fps is None:
            warnings.warn('No FPS given, using 30fps by default')
            self.fps = 30

    def run(self):
        """
        Open a :class:`skvideo.io.FFmpegWriter` and begin processing frames from :attr:`~Video_Writer.q`

        Should not be called by itself, overwrites the :meth:`multiprocessing.Process.run` method,
        so should call :meth:`Video_Writer.start`

        Continue encoding until 'END' put in queue.
        """

        self.timestamps = []


        out_vid_fn = self.path
        vid_out = io.FFmpegWriter(out_vid_fn,
        #vid_out = FastWriter(out_vid_fn,
            inputdict={
                '-r': str(self.fps),
        },
            outputdict={
                '-vcodec': 'libx264',
                '-pix_fmt': 'yuv420p',
                '-r': str(self.fps),
                '-preset': 'ultrafast',
            },
            verbosity=1
        )

        try:

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
            vid_out.close()

            # save timestamps as .csv
            ts_path = os.path.splitext(self.path)[0] + '.csv'
            with open(ts_path, 'w') as ts_file:
                csv_writer = csv.writer(ts_file)
                for ts in self.timestamps:
                    csv_writer.writerow([ts])



def list_spinnaker_cameras():
    """
    List all available Spinnaker cameras and their ``DeviceInformation``

    Returns:
        list: list of dictionaries of device information for each camera.
    """
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


def _check_ffmpeg() -> bool:
    if shutil.which('ffmpeg') is None:
        raise ImportError(
            'ffmpeg could not be found on the system, and it is needed in order to write videos. install it with apt (sudo apt update && sudo apt install ffmpeg)')
    else:
        return True