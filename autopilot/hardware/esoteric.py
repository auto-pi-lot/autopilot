import itertools
import typing

from autopilot.hardware import Hardware, BOARD_TO_BCM
from autopilot.hardware.gpio import GPIO, Digital_Out

import numpy as np

ENABLED = False
try:
    import pigpio
    ENABLED = True
except ImportError:
    pass


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

        self.pig = None # type: typing.Optional[pigpio.pi]
        self.pigpiod = None
        self.CONNECTED = False
        self.CONNECTED = self.init_pigpio()

        self._direction = False # false for down, true for up
        self._mask = np.zeros((len(self.PINS['ROW']), len(self.PINS['COL'])),
                              dtype=np.bool) # current binary mask
        self._hardware = {} # container for :class:`.Digital_Out` objects (for move, direction, etc)
        self._cmd_mask = np.zeros((32), dtype=np.bool) # type: np.ndarray
        """32-bit boolean array to store the binary mask to the gpio pinsv"""


    def init_pins(self):
        """
        Initialize control over GPIO pins

        * init :attr:`.COL_PINS` and :attr:`.ROW_PINS` as output, they will be controlled with ``set_bank``
        * init :attr:`.WORD_LATCH`, :attr:`.MOVE_PIN`, and :attr:`DIRECTION_PIN` as :class:`.hardware.gpio.Digital_Out` objects
        *

        Returns:

        """

        for pin in self.BCM['COL'] + self.BCM['ROW']:
            self.pig.set_mode(pin, pigpio.OUTPUT)
            self.pig.set_pull_up_down(pin, pigpio.PUD_DOWN)

        for pin_name in ('ROW_LATCH', 'MOVE', 'DIRECTION'):
            pin = self.BCM[pin_name]
            self._hardware[pin_name] = Digital_Out(pin=pin, pull=0, name=pin_name)

    @property
    def mask(self) -> np.ndarray:
        """
        Control the mask of active columns
        Returns:
            np.ndarray: boolean array of active/inactive columns
        """
        return self._mask

    @mask.setter
    def mask(self, mask: np.ndarray):
        # check that, for rows and columns that are active,
        # all permutations of those rows and columns are active.
        # (aka for now assume that there is no control logic that happens between movement steps)
        row_inds, col_inds = np.nonzero(mask)

        # make full product of all row and columns to test against
        test_product = tuple(itertools.product(np.unique(row_inds), np.unique(col_inds)))
        coords = tuple((row, col) for row, col in zip(row_inds, col_inds))
        if test_product != coords:
            raise NotImplementedError('Dynamic masks not supported -- all masks need to be the product of active rows * active columns')

        # check if need to flip row mask bit
        FLIP_LATCH = False
        if row_inds != np.nonzero(self._mask)[0]:
            FLIP_LATCH = True

        # construct rest of binary mask
        #self._cmd_mask[self.BCM['ROW']] =


        # TODO: ACTUALLY I THINK IT FLIPS FOR EVERY ROW COLUMN COMBINATION




        self._mask = mask




    @property
    def direction(self) -> bool:
        return bool(self.pig.read(self.BCM['DIRECTION']))

    @direction.setter
    def direction(self, direction: bool):
        self._hardware['DIRECTION'].set(direction)
        self._cmd_mask[self.BCM['DIRECTION']] = direction







    def _write_bank(self, binary_string):
        pass








test_mask = np.zeros((6,3),dtype=np.bool)