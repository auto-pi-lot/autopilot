import os
import sys
from autopilot import prefs
from autopilot.core.networking import Net_Node
from autopilot.hardware import Hardware
from autopilot.hardware.cameras import Camera

import threading
import time
import struct
from datetime import datetime
import numpy as np
from itertools import product
from scipy.interpolate import griddata

if sys.version_info >= (3,0):
    from queue import Queue, Empty
else:
    from Queue import Queue, Empty

if prefs.AGENT in ['pilot']:
    import pigpio

try:
    import MLX90640 as mlx_cam
    MLX90640_LIB = True
except ImportError:
    MLX90640_LIB = False



class I2C_9DOF(Hardware):
    """
    A `Sparkfun 9DOF<https://www.sparkfun.com/products/13944>`_ combined accelerometer, magnetometer, and gyroscope.

    This device uses I2C, so must be connected accordingly:

    - VCC: 3.3V (pin 2)
    - Ground: (any ground pin
    - SDA: I2C.1 SDA (pin 3)
    - SCL: I2C.1 SCL (pin 5)

    This class uses code from the `Adafruit Circuitfun <https://github.com/adafruit/Adafruit_CircuitPython_LSM9DS1>`_ library,
    modified to use pigpio
    """

    # Internal constants and register values:
    _ADDRESS_ACCELGYRO = 0x6B
    _ADDRESS_MAG = 0x1E
    _XG_ID = 0b01101000
    _MAG_ID = 0b00111101

    # Linear Acceleration: mg per LSB
    _ACCEL_MG_LSB_2G = 0.061
    _ACCEL_MG_LSB_4G = 0.122
    _ACCEL_MG_LSB_8G = 0.244
    _ACCEL_MG_LSB_16G = 0.732

    # Magnetic Field Strength: gauss range
    _MAG_MGAUSS_4GAUSS = 0.14
    _MAG_MGAUSS_8GAUSS = 0.29
    _MAG_MGAUSS_12GAUSS = 0.43
    _MAG_MGAUSS_16GAUSS = 0.58

    # Angular Rate: dps per LSB
    _GYRO_DPS_DIGIT_245DPS = 0.00875
    _GYRO_DPS_DIGIT_500DPS = 0.01750
    _GYRO_DPS_DIGIT_2000DPS = 0.07000

    # Temperature: LSB per degree celsius
    _TEMP_LSB_DEGREE_CELSIUS = 8  # 1C = 8, 25 = 200, etc.

    # Register mapping for accelerometer/gyroscope component
    _REGISTER_WHO_AM_I_XG = 0x0F
    _REGISTER_CTRL_REG1_G = 0x10
    _REGISTER_CTRL_REG2_G = 0x11
    _REGISTER_CTRL_REG3_G = 0x12
    _REGISTER_TEMP_OUT_L = 0x15
    _REGISTER_TEMP_OUT_H = 0x16
    _REGISTER_STATUS_REG = 0x17
    _REGISTER_OUT_X_L_G = 0x18
    _REGISTER_OUT_X_H_G = 0x19
    _REGISTER_OUT_Y_L_G = 0x1A
    _REGISTER_OUT_Y_H_G = 0x1B
    _REGISTER_OUT_Z_L_G = 0x1C
    _REGISTER_OUT_Z_H_G = 0x1D
    _REGISTER_CTRL_REG4 = 0x1E
    _REGISTER_CTRL_REG5_XL = 0x1F
    _REGISTER_CTRL_REG6_XL = 0x20
    _REGISTER_CTRL_REG7_XL = 0x21
    _REGISTER_CTRL_REG8 = 0x22
    _REGISTER_CTRL_REG9 = 0x23
    _REGISTER_CTRL_REG10 = 0x24
    _REGISTER_OUT_X_L_XL = 0x28
    _REGISTER_OUT_X_H_XL = 0x29
    _REGISTER_OUT_Y_L_XL = 0x2A
    _REGISTER_OUT_Y_H_XL = 0x2B
    _REGISTER_OUT_Z_L_XL = 0x2C
    _REGISTER_OUT_Z_H_XL = 0x2D

    _REGISTER_WHO_AM_I_M = 0x0F
    _REGISTER_CTRL_REG1_M = 0x20
    _REGISTER_CTRL_REG2_M = 0x21
    _REGISTER_CTRL_REG3_M = 0x22
    _REGISTER_CTRL_REG4_M = 0x23
    _REGISTER_CTRL_REG5_M = 0x24
    _REGISTER_STATUS_REG_M = 0x27
    _REGISTER_OUT_X_L_M = 0x28
    _REGISTER_OUT_X_H_M = 0x29
    _REGISTER_OUT_Y_L_M = 0x2A
    _REGISTER_OUT_Y_H_M = 0x2B
    _REGISTER_OUT_Z_L_M = 0x2C
    _REGISTER_OUT_Z_H_M = 0x2D

    _REGISTER_CFG_M = 0x30
    _REGISTER_INT_SRC_M = 0x31

    _MAGTYPE = True
    _XGTYPE = False
    _SENSORS_GRAVITY_STANDARD = 9.80665

    # User facing constants/module globals.
    ACCELRANGE_2G = (0b00 << 3)
    ACCELRANGE_16G = (0b01 << 3)
    ACCELRANGE_4G = (0b10 << 3)
    ACCELRANGE_8G = (0b11 << 3)
    MAGGAIN_4GAUSS = (0b00 << 5)  # +/- 4 gauss
    MAGGAIN_8GAUSS = (0b01 << 5)  # +/- 8 gauss
    MAGGAIN_12GAUSS = (0b10 << 5)  # +/- 12 gauss
    MAGGAIN_16GAUSS = (0b11 << 5)  # +/- 16 gauss
    GYROSCALE_245DPS = (0b00 << 3)  # +/- 245 degrees/s rotation
    GYROSCALE_500DPS = (0b01 << 3)  # +/- 500 degrees/s rotation
    GYROSCALE_2000DPS = (0b11 << 3)  # +/- 2000 degrees/s rotation

    def __init__(self, *args, **kwargs):
        super(I2C_9DOF, self).__init__(*args, **kwargs)

        # Initialize the pigpio connection
        self.pig = pigpio.pi()

        # Open I2C buses
        self.accel = self.pig.i2c_open(1, self._ADDRESS_ACCELGYRO)
        self.magnet = self.pig.i2c_open(1, self._ADDRESS_MAG)

        # soft reset & reboot accel/gyro and magnet
        self.pig.i2c_write_byte_data(self.accel, self._REGISTER_CTRL_REG8, 0x05)
        self.pig.i2c_write_byte_data(self.magnet, self._REGISTER_CTRL_REG2_M, 0x0C)

        ## enable continuous collection
        # gyro
        self.pig.i2c_write_byte_data(self.accel, self._REGISTER_CTRL_REG1_G, 0xC0)
        # accelerometer
        self.pig.i2c_write_byte_data(self.accel, self._REGISTER_CTRL_REG5_XL, 0x38)
        self.pig.i2c_write_byte_data(self.accel, self._REGISTER_CTRL_REG6_XL, 0xC0)
        # magnetometer
        self.pig.i2c_write_byte_data(self.magnet, self._REGISTER_CTRL_REG3_M, 0x00)

        # set default ranges for sensors
        self.accel_range = self.ACCELRANGE_2G

        self._accel_mg_lsb = None
        self._mag_mgauss_lsb = None
        self._gyro_dps_digit = None

    @property
    def accel_range(self):
        """The accelerometer range.  Must be one of:
          - :attr:`I2C_9DOF.ACCELRANGE_2G`
          - :attr:`I2C_9DOF.ACCELRANGE_4G`
          - :attr:`I2C_9DOF.ACCELRANGE_8G`
          - :attr:`I2C_9DOF.ACCELRANGE_16G`
        """
        reg = self.pig.i2c_read_byte_data(self.accel, self._REGISTER_CTRL_REG6_XL)
        return (reg & 0b00011000) & 0xFF

    @accel_range.setter
    def accel_range(self, val):
        assert val in (self.ACCELRANGE_2G, self.ACCELRANGE_4G,
                       self.ACCELRANGE_8G, self.ACCELRANGE_16G)
        reg = self.pig.i2c_read_byte_data(self.accel, self._REGISTER_CTRL_REG6_XL)

        reg = (reg & ~(0b00011000)) & 0xFF
        reg |= val

        self.pig.i2c_write_byte_data(self.accel, self._REGISTER_CTRL_REG6_XL, reg)
        if val == self.ACCELRANGE_2G:
            self._accel_mg_lsb = self._ACCEL_MG_LSB_2G
        elif val == self.ACCELRANGE_4G:
            self._accel_mg_lsb = self._ACCEL_MG_LSB_4G
        elif val == self.ACCELRANGE_8G:
            self._accel_mg_lsb = self._ACCEL_MG_LSB_8G
        elif val == self.ACCELRANGE_16G:
            self._accel_mg_lsb = self._ACCEL_MG_LSB_16G


    @property
    def mag_gain(self):
        """The magnetometer gain.  Must be a value of:
          - :attr:`I2C_9DOF.MAGGAIN_4GAUSS`
          - :attr:`I2C_9DOF.MAGGAIN_8GAUSS`
          - :attr:`I2C_9DOF.MAGGAIN_12GAUSS`
          - :attr:`I2C_9DOF.MAGGAIN_16GAUSS`
        """
        reg = self.pig.i2c_read_byte_data(self.magnet, self._REGISTER_CTRL_REG2_M)
        return (reg & 0b01100000) & 0xFF

    @mag_gain.setter
    def mag_gain(self, val):
        assert val in (self.MAGGAIN_4GAUSS, self.MAGGAIN_8GAUSS, self.MAGGAIN_12GAUSS,
                       self.MAGGAIN_16GAUSS)
        reg = self.pig.i2c_read_byte_data(self.magnet, self._REGISTER_CTRL_REG2_M)
        reg = (reg & ~(0b01100000)) & 0xFF
        reg |= val
        self.pig.i2c_write_byte_data(self.magnet, self._REGISTER_CTRL_REG2_M, reg)
        if val == self.MAGGAIN_4GAUSS:
            self._mag_mgauss_lsb = self._MAG_MGAUSS_4GAUSS
        elif val == self.MAGGAIN_8GAUSS:
            self._mag_mgauss_lsb = self._MAG_MGAUSS_8GAUSS
        elif val == self.MAGGAIN_12GAUSS:
            self._mag_mgauss_lsb = self._MAG_MGAUSS_12GAUSS
        elif val == self.MAGGAIN_16GAUSS:
            self._mag_mgauss_lsb = self._MAG_MGAUSS_16GAUSS


    @property
    def gyro_scale(self):
        """The gyroscope scale.  Must be a value of:
          - :attr:`I2C_9DOF.GYROSCALE_245DPS`
          - :attr:`I2C_9DOF.GYROSCALE_500DPS`
          - :attr:`I2C_9DOF.GYROSCALE_2000DPS`
        """
        reg = self.pig.i2c_read_byte_data(self.accel, self._REGISTER_CTRL_REG1_G)
        return (reg & 0b00011000) & 0xFF

    @gyro_scale.setter
    def gyro_scale(self, val):
        assert val in (self.GYROSCALE_245DPS, self.GYROSCALE_500DPS, self.GYROSCALE_2000DPS)
        reg = self.pig.i2c_read_byte_data(self.accel, self._REGISTER_CTRL_REG1_G)

        reg = (reg & ~(0b00011000)) & 0xFF
        reg |= val

        self.pig.i2c_write_byte_data(self.accel, self._REGISTER_CTRL_REG1_G, reg)
        if val == self.GYROSCALE_245DPS:
            self._gyro_dps_digit = self._GYRO_DPS_DIGIT_245DPS
        elif val == self.GYROSCALE_500DPS:
            self._gyro_dps_digit = self._GYRO_DPS_DIGIT_500DPS
        elif val == self.GYROSCALE_2000DPS:
            self._gyro_dps_digit = self._GYRO_DPS_DIGIT_2000DPS


    @property
    def acceleration(self):
        """
        The calibrated  x, y, z acceleration in m/s^2

        Returns:
            accel (tuple): x, y, z acceleration

        """
        # taking some code from the pigpio examples
        # http://abyz.me.uk/rpi/pigpio/code/i2c_ADXL345_py.zip
        # and adapting with the sparkfun code in main docstring
        (s, b) = self.pig.i2c_read_i2c_block_data(self.accel, 0x80 | self._REGISTER_OUT_X_L_XL, 6)
        if s >= 0:
            raw =  struct.unpack('<3h', buffer(b))
            return map(lambda x: x*self._accel_mg_lsb / 1000.0 * self._SENSORS_GRAVITY_STANDARD, raw)

    @property
    def magnetic(self):
        """
        The magnetometer X, Y, Z axis values as a 3-tuple of gauss values.

        Returns:
            (tuple): x, y, z gauss values

        """
        (s, b) = self.pig.i2c_read_i2c_block_data(self.magnet, 0x80 | self._REGISTER_OUT_X_L_M, 6)

        if s >= 0:
            raw = struct.unpack('<3h', buffer(b))
            return map(lambda x: x * self._mag_mgauss_lsb / 1000.0, raw)

    @property
    def gyro(self):
        """
        The gyroscope X, Y, Z axis values as a 3-tuple of
        degrees/second values.
        """
        (s, b) = self.pig.i2c_read_i2c_block_data(self.accel, 0x80 | self._REGISTER_OUT_X_L_G, 6)

        if s>=0:
            raw = struct.unpack('<3h', buffer(b))
            return map(lambda x: x * self._gyro_dps_digit, raw)

    @property
    def temperature(self):
        """
        Returns:
            float: Temperature in Degrees C
        """
        (s, b) = self.pig.i2c_read_i2c_block_data(self.accel, 0x80 | self._REGISTER_TEMP_OUT_L, 2)
        buf = buffer(b)
        temp = ((buf[1] << 8) | buf[0]) >> 4
        temp = self._twos_comp(temp, 12)
        return 27.5 + temp/16

    def _twos_comp(self, val, bits):
        # Convert an unsigned integer in 2's compliment form of the specified bit
        # length to its signed integer value and return it.
        if val & (1 << (bits - 1)) != 0:
            return val - (1 << bits)
        return val

class MLX90640(Camera):
    """
    A MLX90640 Temperature sensor.

    Args:
        fps (int): Acquisition framerate, must be one of :attr:`MLX90640.ALLOWED_FPS`
        integrate_frames (int): Number of frames to average over
        interpolate (int): Interpolation multiplier -- 3 "increases the resolution" 3x
        **kwargs: passed to :class:`.Camera`

    Attributes:
        shape (tuple): :attr:`~MLX90640.SHAPE_SENSOR
        integrate_frames (int): Number of frames to average over
        interpolate (int): Interpolation multiplier -- 3 "increases the resolution" 3x
        _grab_event (:class:`threading.Event`): capture thread sets every time it gets a frame,
            _grab waits every time, keeps us from returning same frame twice

    This device uses I2C, so must be connected accordingly:

    - VCC: 3.3V (pin 2)
    - Ground: (any ground pin
    - SDA: I2C.1 SDA (pin 3)
    - SCL: I2C.1 SCL (pin 5)

    Uses a modified version of the `MLX90640 Library <https://github.com/sneakers-the-rat/mlx90640-library>`_
    that is capable of outputting 64fps. You must install the library separately, see the
    ``setup_mlx90640.sh`` script.

    Capture works a bit differently from other Cameras -- the :meth:`~MLX90640.capture_init` method spawns a
    :meth:`~MLX90640._threaded_capture` thread, which continually puts frames in the :attr:`~MLX90640._frames` array
    which serves as a ring buffer. The :meth:`~MLX90640._grab` method then awaits the :attr:`~MLX90640._grab_event` to
    be set by the capture thread, and when it is set returns the mean across frames of the ring buffer.

    .. note::
        The setup script modifies the systemwide i2c baudrate to 1MHz, which may interfere with other
        I2C devices. It can be returned to 400kHz (default) by editing ``/config/boot.txt`` to read
        ``dtparam=i2c_arm_baudrate=400000``

    """
    type='MLX90640'

    ALLOWED_FPS = (1, 2, 4, 8, 16, 32, 64) #: FPS must be one of these
    SHAPE_SENSOR = (32,24) #: (H, W) Output shape of this sensor is always the same. May differ from :attr:`MLX90640.shape` if interpolate >1

    def __init__(self, fps=64, integrate_frames = 64, interpolate = 3, **kwargs):
        """


        """
        if not MLX90640_LIB:
            ImportError('the MLX90640 library was not found, please use the setup_mlx90640.sh script or install manually')

        super(MLX90640, self).__init__(fps, **kwargs)

        # frame shape from the sensor is always the same
        self.shape_sensor = (32, 24)
        # but output shape is dependent on interpolation
        self.shape = (self.SHAPE_SENSOR[0]*interpolate, self.SHAPE_SENSOR[1]*interpolate)


        self._frame_idx = 0
        self._frames = None
        self._integrate_frames = None
        self._interpolate = None
        self._cap_thread = None

        # capture thread sets every time it gets a frame,
        # _grab waits every time.
        # keeps us from returning same frame twice
        self._grab_event = threading.Event()

        # interpolation properties
        self._grid_x = None
        self._grid_y = None
        self._points = list(product(range(self.shape_sensor[0]),
                                    range(self.shape_sensor[1])))

        # set attributes
        self.integrate_frames = integrate_frames
        self.interpolate = interpolate




    @property
    def fps(self):
        return self._fps

    @fps.setter
    def fps(self, fps):
        if fps not in self.ALLOWED_FPS:
            ValueError('fps must be one of {}, got {}'.format(self.ALLOWED_FPS, fps))

        self._fps = fps
        # resets cam attribute, next time it's called for the fps will be set.
        self.cam.cleanup()
        self._cam = None

    @property
    def integrate_frames(self):
        return self._integrate_frames

    @integrate_frames.setter
    def integrate_frames(self, integrate_frames):
        self._frames = np.zeros((self.shape_sensor[0], self.shape_sensor[1], integrate_frames))
        self._integrate_frames = integrate_frames

    @property
    def interpolate(self):
        return self._interpolate

    @interpolate.setter
    def interpolate(self, interpolate):
        if interpolate is not None:
            self._grid_y, self._grid_x = np.meshgrid(np.linspace(0, 24, 24 * interpolate),
                                                   np.linspace(0, 32, 32 * interpolate))
        self._interpolate = interpolate


    def init_cam(self):
        """
        Set the camera object to use our :attr:`MLX90640.fps`
        """
        return mlx_cam.setup(self.fps)

    def capture_init(self):
        """
        Spawn a :meth:`~MLX90640._threaded_capture` thread
        """
        self._cap_thread = threading.Thread(target=self._threaded_capture)
        self._cap_thread.setDaemon(True)
        self._cap_thread.start()


    def _threaded_capture(self):
        """
        Continually capture frames into the :attr:`~MLX90640._frames` ring buffer

        Stops when :attr:`~MLX90640.stopping` is set.
        """
        while not self.stopping.is_set():

            # store the frame in the ringbuffer
            # image comes in all wonky and this is a weird combo of instance and module methods...
            # in order:
            # get frame, cast as array
            # reshape using fortran order and transpose
            # rotate 90 degrees to get normal orientation.
            self._frames[:, :, self._frame_idx] = np.rot90(
                np.array(
                    self.cam.get_frame()
                ).reshape(
                    (self.shape_sensor[0], self.shape_sensor[1]),
                    order="F").T
            )
            self._grab_event.set()
            self._frame_idx = (self._frame_idx + 1) % self.integrate_frames

    def _grab(self):
        """
        Await the :attr:`~MLX90640._grab_event` and then average over the frames stored in
        :attr:`~MLX90640._frames`

        Returns:
            (:class:`~numpy.ndarray`) Averaged and interpolated frame
        """
        ret = self._grab_event.wait(1)
        if not ret:
            return None

        frame = np.mean(self._frames, axis=2)
        self._grab_event.clear()

        if self.interpolate is not None:
            frame = self.interpolate_frame(frame)

        return self._timestamp(), frame

    def _timestamp(self, frame=None):
        """
        Just gets Python timestamps for now...

        Returns:
            str: Isoformatted timestamp from datetime
        """
        return datetime.now().isoformat()

    def interpolate_frame(self, frame):
        """
        Interpolate frame according to :attr:`~MLX90640.interpolate` using :meth:`scipy.interpolate.griddata`

        Args:
            frame (:class:`numpy.ndarray`): Frame to interpolate

        Returns:
            (:class:`numpy.ndarray`): Interpolated Frame
        """
        return griddata(self._points,
                        frame.flatten(),
                        (self._grid_x, self._grid_y),
                        method='cubic')

    def release(self):
        """
        Stops the capture thread, cleans up the camera, and calls the superclass release method.
        """
        self.stopping.set()
        self.cam.cleanup()
        self._cam = None
        super(MLX90640, self).release()









