import pigpio
import struct

class I2C_9DOF(object):
    """
    A `Sparkfun 9DOF<https://www.sparkfun.com/products/13944>`_ combined accelerometer, magnetometer, and gyroscope.

    This device uses I2C, so must be connected accordingly:

    - VCC: 3.3V (pin 2)
    - Ground: (any ground pin
    - SDA: I2C.1 SDA (pin 3)
    - SCL: I2C.1 SCL (pin 5)

    This class uses code from the `Adafruit Circuitfun <https://github.com/adafruit/Adafruit_CircuitPython_LSM9DS1>`_ library
    """

    _ADDRESS_ACCELGYRO = 0x6B
    _ADDRESS_MAG = 0x1E
    _XG_ID = 0b01101000
    _MAG_ID = 0b00111101
    _ACCEL_MG_LSB_2G = 0.061
    _ACCEL_MG_LSB_4G = 0.122
    _ACCEL_MG_LSB_8G = 0.244
    _ACCEL_MG_LSB_16G = 0.732
    _MAG_MGAUSS_4GAUSS = 0.14
    _MAG_MGAUSS_8GAUSS = 0.29
    _MAG_MGAUSS_12GAUSS = 0.43
    _MAG_MGAUSS_16GAUSS = 0.58
    _GYRO_DPS_DIGIT_245DPS = 0.00875
    _GYRO_DPS_DIGIT_500DPS = 0.01750
    _GYRO_DPS_DIGIT_2000DPS = 0.07000
    _TEMP_LSB_DEGREE_CELSIUS = 8  # 1C = 8, 25 = 200, etc.
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

    def __init__(self):

        # Initialize the pigpio connection
        self.pig = pigpio.pi()

        # Open I2C buses
        self.accel = self.pig.i2c_open(1, self._ADDRESS_ACCELGYRO)
        self.magnet = self.pig.i2c_open(1, self._ADDRESS_MAG)

        # soft reset & reboot accel/gyro and magnet
        self.pig.i2c_write_byte_data(self.accel, self._REGISTER_CTRL_REG8, 0x05)
        self.pig.i2c_write_byte_data(self.magnet, self._REGISTER_CTRL_REG2_M, 0x0C)

        # enable continuous collection
        # gyro
        self.pig.i2c_write_byte_data(self.accel, self._REGISTER_CTRL_REG1_G, 0xC0)
        # accelerometer
        self.pig.i2c_write_byte_data(self.accel, self._REGISTER_CTRL_REG5_XL, 0x38)
        self.pig.i2c_write_byte_data(self.accel, self._REGISTER_CTRL_REG6_XL, 0xC0)
        # magnetometer
        self.pig.i2c_write_byte_data(self.magnet, self._REGISTER_CTRL_REG3_M, 0x00)

        # set accelerometer range
        self.accel_range = self.ACCELRANGE_2G

    @property
    def accel_range(self):
        """The accelerometer range.  Must be a value of:
          - ACCELRANGE_2G
          - ACCELRANGE_4G
          - ACCELRANGE_8G
          - ACCELRANGE_16G
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

    def read_accel(self):
        """
        Read the raw (unscaled) accelerometer data

        Returns:
            accel (tuple): x, y, z acceleration
        """

        # taking some code from the pigpio examples
        # http://abyz.me.uk/rpi/pigpio/code/i2c_ADXL345_py.zip
        # and adapting with the sparkfun code in main docstring
        (s, b) = self.pig.i2c_read_i2c_block_data(self.accel, 0x80 | self._REGISTER_OUT_X_L_XL, 6)
        if s >= 0:
            return struct.unpack('<3h', buffer(b))

    @property
    def acceleration(self):
        """
        The calibrated  x, y, z acceleration in m/s^2

        Returns:
            accel (tuple): x, y, z acceleration

        """
        raw = self.read_accel()
        return map(lambda x: x * self._accel_mg_lsb / 1000.0 * self._SENSORS_GRAVITY_STANDARD, raw)

