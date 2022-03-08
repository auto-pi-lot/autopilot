"""
Adapted from the People's Ventilator Project tests: https://github.com/CohenLabPrinceton/pvp/blob/master/tests/pigpio_mocks.py
with work mostly from Rengo! https://github.com/CommReteris


"""

from collections import deque
from functools import wraps
from random import getrandbits, choice
from secrets import token_bytes
from socket import error as socket_error

import pigpio
import pytest

MAX_SCRIPTS = 256

@pytest.fixture()
def patch_pigpio_base(monkeypatch):
    """ monkeypatches the bare-minimum elements of pigpio to instantiate pigpio.pi() without communicating with the
    pigpio daemon (or hardware)"""

    class MockThread:
        def __init__(self, *args, **kwargs):
            pass

        def stop(self):
            pass

    class MockSocket:
        """ Bare-bones mock of socket.Socket with additional mocks of functions called by pigpio"""

        def __init__(self, *args, **kwargs):
            pass

        @staticmethod
        def close():
            pass

        def setsockopt(self, *args, **kwargs):
            pass

    class MockSockLock:
        """ Bare-bones mock of pigpio._socklock"""

        def __init__(self, *args, **kwargs):
            self.s = None
            self.l = None

    def mock_pigpio_command(*args, **kwargs):
        """ Make sure no commands get sent to the pigpio daemon"""
        pass

    def mock_create_connection(host, timeout):
        """ mock of socket.create_connection(). Returns a bare-bones mock socket"""
        return MockSocket

    def do_monkeypatch():
        monkeypatch.setattr("socket.create_connection", mock_create_connection)
        monkeypatch.setattr("pigpio._socklock", MockSockLock)
        monkeypatch.setattr("pigpio._callback_thread", MockThread)
        monkeypatch.setattr("pigpio._pigpio_command", mock_pigpio_command)
        monkeypatch.delattr("pigpio._pigpio_command_nolock")
        monkeypatch.delattr("pigpio._pigpio_command_ext")
        monkeypatch.delattr("pigpio._pigpio_command_ext_nolock")
       # monkeypatch.setattr("pigpio.pi.connected", 1, raising=False)

    do_monkeypatch()


@pytest.fixture()
def patch_bad_socket(monkeypatch):
    """ Monkeypatches socket.create_connection() to always throw an Exception as if things had gone poorly (instead of
            doing anything else)
    """
    def mock_create_bad_connection(host, timeout):
        """ mock of socket.create_connection(). Returns a bare-bones mock socket"""
        raise socket_error

    def do_monkeypatch():
        monkeypatch.setattr("socket.create_connection", mock_create_bad_connection)

    do_monkeypatch()


@pytest.fixture()
def patch_pigpio_i2c(patch_pigpio_base, monkeypatch):
    """ monkeypatches pigpio.pi() with a mock I2C interface that does not depend on the pigpio daemon"""

    def add_mock_hardware(self, device: MockHardwareDevice, i2c_address, i2c_bus):
        self.mock_i2c[i2c_bus][i2c_address] = device

    @mock_pigpio_errors
    def mock_i2c_open(self, i2c_bus, i2c_address):
        if i2c_bus in self.mock_i2c:
            handle = len(self.mock_handles)
            self.mock_handles[handle] = (i2c_bus, i2c_address)
            return handle
        else:
            return pigpio.PI_BAD_I2C_BUS

    @mock_pigpio_errors
    def mock_i2c_close(self, handle):
        if handle in self.mock_handles:
            (i2c_bus, i2c_address) = self.mock_handles[handle]
            del self.mock_i2c[i2c_bus][i2c_address]
            del self.mock_handles[handle]
            return 0
        else:
            return pigpio.PI_BAD_HANDLE

    @mock_pigpio_errors
    def mock_spi_open(self, channel, baudrate):
        """ Basically the same as I2C open except uses 'spi' as the i2c bus"""
        if channel in range(21):
            handle = len(self.mock_handles)
            self.mock_handles = {handle: ('spi', channel)}
            return handle
        else:
            return pigpio.PI_BAD_SPI_CHANNEL

    @mock_pigpio_errors
    def mock_spi_close(self, handle):
        """ Just calls I2C close."""
        result = self.i2c_close(handle)
        return result

    @mock_pigpio_errors
    def mock_i2c_read_device(self, handle, count):
        if handle in self.mock_handles:
            (bus, addr) = self.mock_handles[handle]
            return count, bytearray(self.mock_i2c[bus][addr].read_mock_hardware_device(count))
        else:
            return (pigpio.PI_BAD_HANDLE,)

    @mock_pigpio_errors
    def mock_i2c_read_i2c_block_data(self, handle, reg, count):
        if handle in self.mock_handles:
            (bus, addr) = self.mock_handles[handle]
            if count != 2:
                raise NotImplementedError
            return count, bytearray(self.mock_i2c[bus][addr].read_mock_hardware_register(reg, count))
        else:
            return (pigpio.PI_BAD_HANDLE,)

    @mock_pigpio_errors
    def mock_i2c_write_device(self, handle, data):
        if handle in self.mock_handles:
            (bus, addr) = self.mock_handles[handle]
            if type(data) is int:
                data = data.to_bytes(2, 'little')
            elif type(data) is bytes:
                pass
            else:
                raise NotImplementedError
            self.mock_i2c[bus][addr].write_mock_hardware_device(data)
            return 0
        else:
            return pigpio.PI_BAD_HANDLE

    @mock_pigpio_errors
    def mock_i2c_write_i2c_block_data(self, handle, reg, data):
        if handle in self.mock_handles:
            (bus, addr) = self.mock_handles[handle]
            if type(data) is int:
                data = data.to_bytes(2, 'little')
            elif type(data) is bytes:
                pass
            else:
                raise NotImplementedError
            self.mock_i2c[bus][addr].write_mock_hardware_register(reg, data)
            return 0
        else:
            return pigpio.PI_BAD_HANDLE

    def do_monkeypatch():
        monkeypatch.setattr("pigpio.pi.mock_i2c", {0: dict(), 1: dict(), 'spi': dict()}, raising=False)
        monkeypatch.setattr("pigpio.pi.mock_handles", dict(), raising=False)
        monkeypatch.setattr("pigpio.pi.add_mock_hardware", add_mock_hardware, raising=False)
        monkeypatch.setattr("pigpio.pi.i2c_open", mock_i2c_open)
        monkeypatch.setattr("pigpio.pi.i2c_close", mock_i2c_close)
        monkeypatch.setattr("pigpio.pi.i2c_read_device", mock_i2c_read_device)
        monkeypatch.setattr("pigpio.pi.i2c_read_i2c_block_data", mock_i2c_read_i2c_block_data)
        monkeypatch.setattr("pigpio.pi.i2c_write_device", mock_i2c_write_device)
        monkeypatch.setattr("pigpio.pi.i2c_write_i2c_block_data", mock_i2c_write_i2c_block_data)
        monkeypatch.setattr("pigpio.pi.spi_open", mock_spi_open)
        monkeypatch.setattr("pigpio.pi.spi_close", mock_spi_close)

    do_monkeypatch()


@pytest.fixture()
def patch_pigpio_gpio(patch_pigpio_base, monkeypatch):
    """ monkeypatches pigpio.pi with a mock GPIO interface.
    - Creates a new list "pigpio.pi.mock_pins" of MockPigpioPin objects, one for each RPi GPIO pin.
    - monkeypatches pigpio.pi.get_mode() to look at pigpio.pi.mock_pins for the mode of each pin instead of
        communicating with the pigpiod daemon.
    - monkeypatches pigpio.pi.set_mode() in a similar manner
    """

    class MockPigpioPin:
        def __init__(self, pin: int):
            """ A simple object to mock a pigpio GPIO pin interface without communicating with the pigpiod daemon. It can
            be determined whether PWM is in use on the pin by checking if self.pwm_duty_cycle is None.

            Note: PWM frequency is weird. Basically, starting a hardware PWM with some frequency does not change the
                underlying (soft) PWM frequency. If the mode on the pin changes, the PWM frequency will revert to that
                soft frequency. However, while the hardware PWM is active, the hardware PWM frequency can be modified by
                calling set_PWM_frequency without triggering a change in mode - this DOES change the underlying soft PWM
                frequency, and will behave as though only soft frequencies are allowed. You can only set a PWM frequency
                outside of those allowed by soft_frequencies via starting a hardware PWM.

            Args:
                gpio (int): A number between 0 and 53
            """
            self.errors = dict(pigpio._errors)
            assert pin in range(53)
            self._mode = choice(list(range(8)))

            self.pin = pin
            self.level = 0
            self.soft_pwm_frequency = 800
            self.hard_pwm_frequency = None
            self.pwm_duty_cycle = None

        @property
        def pwm_range(self):
            return 1000000 if self.mode == 4 else 255

        @property
        def pwm_frequency(self):
            return self.hard_pwm_frequency if self.mode == 4 else self.soft_pwm_frequency

        @pwm_frequency.setter
        def pwm_frequency(self, pwm_frequency):
            if self.mode == 4:
                self.hard_pwm_frequency = pwm_frequency
            self.soft_pwm_frequency = pwm_frequency

        @property
        def mode(self):
            return self._mode

        @mode.setter
        def mode(self, new_mode):
            """ Seems redundant with mock_pigpio_set_mode, but it isn't because mode can be set as a side effect of calling
            other methods, such as starting a PWM. Also, mode MUST be changed prior to setting a pwm_duty_cycle otherwise
            it will be unintentionally wiped
            """
            if new_mode != self.mode and self.pwm_duty_cycle is not None:
                self.pwm_duty_cycle = None
            self._mode = new_mode

    @mock_pigpio_bad_gpio_arg
    @mock_pigpio_errors
    def mock_pigpio_get_mode(self, gpio):
        """ Returns the mode if arg gpio is valid, otherwise mocks the pigpio errnum for PI_BAD_GPIO
        Args:
            self (pigpio.pi): A pigpio.pi or pvp.io.devices.PigpioConnection instance
            gpio (int): A number between 0 and 53

        Returns:
            int: A number between 0 and 7
        """
        return self.mock_pins[gpio].mode

    @mock_pigpio_bad_gpio_arg
    @mock_pigpio_errors
    def mock_pigpio_set_mode(self, gpio, mode):
        """ Will stop a PWM if new mode != mode (via property setter), but not if new mode is the same as set mode
        Args:
            mode (int): A number between 0 and 7 (See: pvp.io.devices.pins.Pin._PIGPIO_MODES)

        Returns:
            int: 0 if successful
        """
        if mode not in range(8):
            return self.mock_pins[gpio].errors[-4]
        else:
            self.mock_pins[gpio].mode = mode
            return 0

    @mock_pigpio_bad_gpio_arg
    @mock_pigpio_errors
    def mock_pigpio_read(self, gpio):
        """ Side effect: Will always set mode to 0 (which will always wipe a PWM)

        Returns:
            int: 0 if pin is pulled low, 1 if pin is pulled high
        """
        self.mock_pins[gpio].mode = 0
        return self.mock_pins[gpio].level

    @mock_pigpio_bad_gpio_arg
    @mock_pigpio_errors
    def mock_pigpio_write(self, gpio, level):
        """ Side effect: Will always wipe a PWM, and will set self.mode
        Args:
            level (int): 0 if pin is to be pulled low, 1 if pin is to be pulled high

        Returns:
            int: 0 if successful
        """
        if level not in range(2):
            return self.mock_pins[gpio].errors[-5]
        else:
            self.mock_pins[gpio].pwm_dutycycle = None
            self.mock_pins[gpio].mode = level
            self.mock_pins[gpio].level = level
            return 0

    @mock_pigpio_bad_user_gpio_arg
    @mock_pigpio_errors
    def mock_get_PWM_frequency(self, gpio):
        """ Note: Will return soft frequency if mode is not 4, regardless of whether a PWM is in use. If mode == 4, returns the
        hardware PWM frequency. This is handled via property getter for self.pwm_frequency

        Returns
            int: The frequency used for PWM on the GPIO, in Hz
        """
        result = self.mock_pins[gpio].pwm_frequency
        if result is not None:
            return result
        else:
            return self.mock_pins[gpio].errors[-92]

    @mock_pigpio_bad_user_gpio_arg
    @mock_pigpio_errors
    def mock_set_PWM_frequency(self, gpio, PWMfreq):
        """
        Args:
            PWMfreq (int): The frequency to be set on the pin.

        Returns:
            int: The frequency set on the GPIO. If PWMfreq not in soft_frequencies, it is the closest allowed frequency
        """
        if PWMfreq not in soft_frequencies:
            PWMfreq = min(soft_frequencies, key=lambda x: abs(x - PWMfreq))
        self.mock_pins[gpio].pwm_frequency = PWMfreq
        return PWMfreq

    @mock_pigpio_bad_user_gpio_arg
    @mock_pigpio_errors
    def mock_get_PWM_dutycycle(self, gpio):
        """
        Returns:
            int: The duty cycle used for the GPIO, out of the PWM range (default 255)
        """
        result = self.mock_pins[gpio].pwm_duty_cycle
        return result if result is not None else self.errors[-92]

    @mock_pigpio_bad_user_gpio_arg
    @mock_pigpio_errors
    def mock_set_PWM_dutycycle(self, gpio, PWMduty):
        """ Note: This will start a soft PWM and change pin mode if mode is not already 1. Must set self.mode prior
        to setting self.duty_cycle

        Args:
            PWMduty (int): the duty cycle to be use for the GPIO, must be in range(pwm_range+1)

        Returns:
            int: 0 if successful
        """

        if PWMduty in range(self.mock_pins[gpio].pwm_range + 1):
            self.mode = 1
            self.mock_pins[gpio].pwm_duty_cycle = PWMduty
            return 0
        else:
            return self.mock_pins[gpio].errors[-8]

    @mock_pigpio_bad_gpio_arg
    @mock_pigpio_errors
    def mock_get_PWM_range(self, gpio):
        """
        Returns:
            int: 255 unless hardware PWM then 1e6
        """
        return self.mock_pins[gpio].pwm_range

    @mock_pigpio_bad_gpio_arg
    @mock_pigpio_errors
    def mock_hardware_PWM(self, gpio, PWMfreq, PWMduty):
        """ Returns appropriate pigpio error if GPIO, PWMfreq, or PWMduty are not in their respective allowable ranges for
        pigpio hardware PWM.
        Note: must set self.pwm_duty_cycle prior to setting self.mode!

        Returns:
            int: 0 if successful
        """
        self.mock_pins[gpio].mode = 4
        if gpio not in (12, 13, 18, 19):
            return self.mock_pins[gpio].errors[-95]
        elif PWMfreq > 187500000 or PWMfreq < 0:
            return self.mock_pins[gpio].errors[-96]
        elif PWMduty not in range(self.mock_pins[gpio].pwm_range + 1):
            return self.mock_pins[gpio].errors[-97]
        else:
            self.mock_pins[gpio].hard_pwm_frequency = PWMfreq
            self.mock_pins[gpio].pwm_duty_cycle = PWMduty
            return 0

    @mock_pigpio_bad_gpio_arg
    @mock_pigpio_errors
    def mock_store_script(self, script) -> int:


        # check not too many scripts
        assert self.len(self.mock_scripts) < MAX_SCRIPTS

        # TODO: Check script validity
        # this long ass thing https://github.com/sneakers-the-rat/pigpio/blob/ad974f99925ae709ef3fd175f54899888b0c6785/command.c#L634-L1253
        # only need / w pwm wait ld tag dcr jp ... ? /
        # return status


        pass

    @mock_pigpio_bad_gpio_arg
    @mock_pigpio_errors
    def mock_script_status(self, script_id):
        pass



    def do_monkeypatch():
        monkeypatch.setattr("pigpio.pi.mock_pins", [MockPigpioPin(num) for num in range(40)], raising=False)
        monkeypatch.setattr("pigpio.pi.mock_scripts", {})
        monkeypatch.setattr("pigpio.pi.get_mode", mock_pigpio_get_mode)
        monkeypatch.setattr("pigpio.pi.set_mode", mock_pigpio_set_mode)
        monkeypatch.setattr("pigpio.pi.read", mock_pigpio_read)
        monkeypatch.setattr("pigpio.pi.write", mock_pigpio_write)
        monkeypatch.setattr("pigpio.pi.get_PWM_frequency", mock_get_PWM_frequency)
        monkeypatch.setattr("pigpio.pi.set_PWM_frequency", mock_set_PWM_frequency)
        monkeypatch.setattr("pigpio.pi.get_PWM_dutycycle", mock_get_PWM_dutycycle)
        monkeypatch.setattr("pigpio.pi.set_PWM_dutycycle", mock_set_PWM_dutycycle)
        monkeypatch.setattr("pigpio.pi.get_PWM_range", mock_get_PWM_range)
        monkeypatch.setattr("pigpio.pi.hardware_PWM", mock_hardware_PWM)

    do_monkeypatch()


@pytest.fixture()
def mock_i2c_hardware():
    """ Factory fixture for creating MockHardwareDevice objects
    """
    def make_mock_hardware(i2c_bus=None, i2c_address=None, n_registers=None, reg_values=None):
        """
        Args:
            i2c_bus (int): 0 or 1
            i2c_address: if None, will generate a random address. Otherwise, will pass through what it is given
            n_registers: If none, will be random.
            reg_values: #todo explain if n_registers > len(reg_values) remaining values filled in

        Returns:
            dict: keys = ('device', 'i2c_bus', 'i2c_address', 'expected') #todo explain what they are
        """
        i2c_bus = getrandbits(1) if i2c_bus is None else i2c_bus
        i2c_address = getrandbits(7) if i2c_address is None else i2c_address
        if reg_values is None:
            n_registers = getrandbits(5) if n_registers is None else n_registers
            reg_values = [token_bytes(2) for _ in range(n_registers)]
        else:
            if n_registers is None:
                pass
            elif n_registers > len(reg_values):
                for i in range(n_registers-len(reg_values)):
                    reg_values.append(token_bytes(2))
            elif n_registers < len(reg_values):
                raise ValueError("Cannot specify fewer registers than register values provided")
        device = MockHardwareDevice(*reg_values)
        return {'device': device, 'i2c_bus': i2c_bus, 'i2c_address': i2c_address, 'values': reg_values}
    return make_mock_hardware


def mock_pigpio_errors(func):
    @wraps(func)
    def mock_pigpio__u2i_exception(self, *args, **kwargs):
        value = func(self, *args, **kwargs)
        v = value if type(value) in (int, bool, float) else value[0]
        if v < 0:
            raise pigpio.error(pigpio.error_text(v))
        return value

    return mock_pigpio__u2i_exception


def mock_pigpio_bad_gpio_arg(func):
    @wraps(func)
    def check_args(self, gpio, *args, **kwargs):
        if gpio in range(53):
            result = func(self, gpio, *args, **kwargs)
        else:
            result = pigpio._errors[pigpio.PI_BAD_GPIO]
        return result

    return check_args


def mock_pigpio_bad_user_gpio_arg(func):
    @wraps(func)
    def check_args(self, gpio, *args, **kwargs):
        if gpio in range(31):
            result = func(self, gpio, *args, **kwargs)
        else:
            result = pigpio._errors[-2]
        return result

    return check_args


class MockHardwareDevice:
    def __init__(self, *args):
        """ A simple mock device with registers defined by kwargs. If only one register value is passed, device emulates
        a single register device that responds to read_device commands (such as the SFM3200). Retains past register
        values upon writing to a register for logging/assertion convenience.

        Register values are stored as raw bytes. Reading and writing to/from the registers simulates network-endian
            transactions by byteswapping.

        Args:
            *args: register_values of type bytes; one, per, register
        """
        self.last_register = None
        self.registers = []
        if args:
            for arg in args:
                if not isinstance(arg, bytes):
                    raise TypeError("Unknown register value of type {}".format(type(arg)))
                self.registers.append(deque())
                self.registers[-1].append(arg)
            if len(self.registers) == 1:
                self.last_register = 0
        else:
            TypeError("MockHardwareDevice needs at least one register to initialize")

    def read_mock_hardware_device(self, count=None):
        """Alias for read_mock_hardware_register(reg_num=None, count)"""
        return self.read_mock_hardware_register(reg_num=None, count=count)

    def write_mock_hardware_device(self, value):
        """ Alias for write_mock_hardware_register(reg_num=None, value)"""
        self.write_mock_hardware_register(reg_num=None, value=value)

    def read_mock_hardware_register(self, reg_num=None, count=None):
        """ Reads count bytes from a specific register

        Args:
            reg_num: The index of the register to read
            count (int): The number of bytes to read

        Returns:
            bytes: the register contents
        """
        if reg_num is None:
            if self.last_register is not None:
                reg_num = self.last_register
            else:
                raise RuntimeError("mock_i2c_device tried to access last register but none have been accessed yet")
        else:
            self.last_register = reg_num
        result = self.registers[reg_num][-1]
        return result if count is None else result[:count]

    def write_mock_hardware_register(self, reg_num, value):
        """ Writes value to register specified by reg_num

        Args:
            reg_num: The index of the register to write
            value (bytes): The stuff to write to the register
        """
        if type(value) is not bytes:
            raise TypeError("arg 'value' must be of type bytes")
        if reg_num is None:
            if self.last_register is not None:
                reg_num = self.last_register
            else:
                raise RuntimeError("mock_i2c_device tried to access last register but none have been accessed yet")
        else:
            self.last_register = reg_num
        self.last_register = reg_num
        self.registers[reg_num].append(value)


soft_frequencies = (8000, 4000, 2000, 1600, 1000, 800, 500, 400, 320, 250, 200, 160, 100, 80, 50, 40, 20, 10)