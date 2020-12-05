from autopilot.hardware import Hardware, BOARD_TO_BCM
from autopilot.hardware.gpio import GPIO, Digital_Out
import numpy as np

DEFAULT_OFFSET = np.array((
    (26, 25, 25, 22, 26, 24),
    (26, 29, 27, 25, 25, 26),
    (24, 25, 25, 30, 25, 26),
    (27, 26, 27, 24, 29, 28),
    (26, 26, 28, 27, 26, 29),
    (26, 27, 28, 27, 20, 19)
))

class Parallax_Platform(Hardware):
    """
    Transcription of Cliff Dax's BASIC program

    * One column, but all rows can be controlled at once --

        * loop through columns, set outputs corresponding to rows, flip 22 at each 'row' setting

    * wait for some undefined small time between each flip of 23
    * to reset/rehome, some hardcoded offset from zero that needs to be stepped for each column.


    Pins:

    Column Control:

        * 8 = col & 1
        * 9 = col & 2
        * 10 = col & 4

    Row control:

        * 0 = word & 1
        * 1 = word & 2
        * 2 = word & 4
        * 3 = word & 8
        * 4 = word & 16
        * 5 = word & 32

    Others:

        * 22 - flipped on and off to store status of row "word" for a given column
        * 23 - flipped on and off to execute a movement command
        * 24 - if 0, go down, if 1, go up

    """

    output = True
    type="PARALLAX_PLATFORM"
    pigs_function = b"w"

    PINS = {
    "COL" : [3, 5, 24],
    "ROW" : [11, 12, 13, 15, 16, 18],
    "ROW_LATCH" : 31,
    "MOVE" : 33,
    "DIRECTION" : 35
    }
    """
    Default Pin Numbers for Parallax Machine
    
    ``COL`` and ``ROW`` are bitwise-anded with powers of 2 to select pins, ie.::
    
        on_rows = '0b010' # the center, or first row is on
        col[0] = '0b010' && 1
        col[1] = '0b010' && 2
        col[2] = '0b010' && 4 
    
    * ``COL`` : Pins to control active columns
    * ``ROW`` : Pins to control active rows
    * ``ROW_LATCH`` : To set active rows, power appropriate ``ROW`` pins and flip ``ROW_LATCH`` on and off
    * ``MOVE`` : Pulse to make active columns move in active ``DIRECTION``
    * ``DIRECTION`` : When high, move up. when low, move down.
    """

    BCM = {
        group: [BOARD_TO_BCM[pin] for pin in pins] if isinstance(pins, list) else
                BOARD_TO_BCM[pins]
                for group, pins in PINS.items()
    }
    """
    :attr:`.PINS` but in BCM numbering system for pigpio
    """

    init_pigpio = GPIO.init_pigpio

    def __init__(self, *args, **kwargs):
        super(Parallax_Platform, self).__init__(*args, **kwargs)

        self.pig = None
        self.pigpiod = None
        self.CONNECTED = False
        self.CONNECTED = self.init_pigpio()

        self._direction = False # false for down, true for up
        self._mask = np.zeros((len(self.PINS['ROW']), len(self.PINS['COL'])),
                              dtype=np.bool) # current binary mask



    def init_pins(self):
        """
        Initialize control over GPIO pins

        * init :attr:`.COL_PINS` and :attr:`.ROW_PINS` as output, they will be controlled with ``set_bank``
        * init :attr:`.WORD_LATCH`, :attr:`.MOVE_PIN`, and :attr:`DIRECTION_PIN` as :class:`.hardware.gpio.Digital_Out` objects
        *

        Returns:

        """
        pass






    @property
    def pin(self):
        pass

    @pin.setter
    def pin(self, pin):
        pass

    @property
    def pull(self):
        pass

    @pull.setter
    def pull(self, pull):
        pass

