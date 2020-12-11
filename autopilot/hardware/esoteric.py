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

    output = True # type: bool
    type="PARALLAX_PLATFORM" # type: str
    pigs_function = b"w" # type: bytes

    PINS = {
    "COL" : [3, 5, 24],
    "ROW" : [11, 12, 13, 15, 16, 18],
    "ROW_LATCH" : 31,
    "MOVE" : 33,
    "DIRECTION" : 35
    } # type: typing.Dict[str, typing.Union[typing.List[int], int]]
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
    } # type: typing.Dict[str, typing.Union[typing.List[int], int]]
    """
    :attr:`.PINS` but in BCM numbering system for pigpio
    """

    GRID_DIM = (6, 6)

    init_pigpio = GPIO.init_pigpio

    # --------------------------------------------------
    # control of height
    # --------------------------------------------------
    STEPS_VAR = 2 #: Variable for storing remaining steps in pigpio
    PULSE_VAR = 0 #: Variable for storing pulse duration in pigpio (in microseconds)
    DELAY_VAR = 1 #: Variable for storing duration between pulses in pigpio (in microseconds)
    # pulse_dur = 100 #: Duration of step pulse (in microseconds)
    # delay_dur = 100 #: Duration of delay between pulses (in microseconds)



    def __init__(self, pulse_dur: int = 10, delay_dur: int = 90, *args, **kwargs):
        super(Parallax_Platform, self).__init__(*args, **kwargs)

        self.pig = None # type: typing.Optional[pigpio.pi]
        self.pigpiod = None
        self.CONNECTED = False # type: bool
        self.CONNECTED = self.init_pigpio()

        self._direction = False # type: bool
        self._mask = np.zeros(self.GRID_DIM,
                              dtype=np.bool) # current binary mask
        self._hardware = {} # type: typing.Dict[str, Digital_Out]
        """
        container for :class:`.Digital_Out` objects (for move, direction, etc)
        """
        self._cmd_mask = np.zeros((32), dtype=np.bool) # type: np.ndarray
        """32-bit boolean array to store the binary mask to the gpio pinsv"""
        #self._powers = 2**np.arange(32)[::-1]
        self._powers = 2 ** np.arange(32)
        """powers to take dot product of _cmd_mask to get integer from bool array"""

        self.init_pins()
        
        self._pulse_dur = int(pulse_dur) # type: int
        self._delay_dur = int(delay_dur) # type: int

        self._height = 0 # type: typing.Optional[int]
        self._move_script_id = None # type: typing.Optional[int]
        self.start_move_script()

        # flip mask to initialize all columns as zero
        self.mask = np.ones(self.GRID_DIM, dtype=np.bool)
        self.mask = np.zeros(self.GRID_DIM, dtype=np.bool)



    def init_pins(self):
        """
        Initialize control over GPIO pins

        * init :attr:`.COL_PINS` and :attr:`.ROW_PINS` as output, they will be controlled with ``set_bank``
        * init :attr:`.WORD_LATCH`, :attr:`.MOVE_PIN`, and :attr:`DIRECTION_PIN` as :class:`.hardware.gpio.Digital_Out` objects
        """

        for pin in self.BCM['COL'] + self.BCM['ROW']:
            self.pig.set_mode(pin, pigpio.OUTPUT)
            self.pig.set_pull_up_down(pin, pigpio.PUD_DOWN)
            self.pig.write(pin, 0)

        for pin_name in ('ROW_LATCH', 'MOVE', 'DIRECTION'):
            pin = self.PINS[pin_name] # use board pin bc digital out automatically changes
            self._hardware[pin_name] = Digital_Out(pin=pin, pull=0, name=pin_name)

    def start_move_script(self):
        """
        Create and start a pigpio script to control pulses to the movement pin

        * Create tag 999 to jump back to beginning of script
        * wait for :attr:`.DELAY_VAR` microseconds
        * compare :attr:`.STEPS_VAR` to accumulator (always left at zero)
        * if :attr:`.STEPS_VAR` is zero, jump back to ``999``
        * otherwise flip ``BCM['MOVE']`` on and off for :attr:`.PULSE_VAR` microseconds
        * decrement :attr:`.STEPS_VAR` and jumpy back to ``999``

        Movement parameters can be changed with calls to `pig.update_script <http://abyz.me.uk/rpi/pigpio/python.html#update_script>`_
        for example::

            pulse_dur = 50
            delay_dur = 100
            N_STEPS = 100

            self.pig.update_script(script_id, (N_STEPS, pulse_dur, delay_dur))
        """

        # script explained in docstring
        SCRIPT = f"tag 999 mics p{self.DELAY_VAR} cmp p{self.STEPS_VAR} jz 999 w {self.BCM['MOVE']} 1 mics p{self.PULSE_VAR} w {self.BCM['MOVE']} 0 dcr p{self.STEPS_VAR} jmp 999".encode('utf-8')
        self._move_script_id = self.pig.store_script(SCRIPT)
        self.pig.run_script(self._move_script_id, (self.pulse_dur, self.delay_dur, 0))

    def _update_script(self, steps=None):
        """update the running movement script
        if steps is None, don't fuck with them, just update the other params"""
        if self._move_script_id is None:
            self.logger.warning('attempted to update script, but script not initialized')
            return

        if steps is None:
            cmd = [0, 0]
            for cmd_ind, cmd_val in zip((self.PULSE_VAR, self.DELAY_VAR),
                                        (self.pulse_dur, self.delay_dur)):
                cmd[cmd_ind] = cmd_val

        else:
            cmd = [0, 0, 0]
            for cmd_ind, cmd_val in zip((self.STEPS_VAR, self.PULSE_VAR, self.DELAY_VAR),
                                        (steps, self.pulse_dur, self.delay_dur)):
                cmd[cmd_ind] = cmd_val

        self.pig.update_script(self._move_script_id, cmd)

    @property
    def direction(self) -> bool:
        """Direction of movement of platforms

        Property reads pin state directly, setter changes pin state and updates :attr:`._cmd_mask`
         
        Returns:
            bool: ``True`` = Up, ``False`` = Down
        """
        return bool(self.pig.read(self.BCM['DIRECTION']))

    @direction.setter
    def direction(self, direction: bool):
        self._hardware['DIRECTION'].set(direction)
        self._cmd_mask[self.BCM['DIRECTION']] = direction

    @property
    def mask(self) -> np.ndarray:
        """
        Control the mask of active columns

        On Assignment, checks if any cells have been changed, then iterates through changed columns and
        sets row bits with :meth:`._latch_col`

        Args:
            mask (:class:`numpy.ndarray`):  New boolean ``[rows x columns]`` array to set

        Returns:
            :class:`numpy.ndarray` : boolean array of active/inactive columns
        """
        return self._mask

    @mask.setter
    def mask(self, mask: np.ndarray):

        if mask.shape != self._mask.shape:
            self.logger.exception(f"Mask cannot change shape! old mask: {self._mask.shape}, new mask: {mask.shape}")
            return

        # find columns that have changed, if any
        changed_cols = np.unique(np.nonzero(self._mask != mask)[1])

        # if nothing has changed, just return
        if len(changed_cols) == 0:
            return

        # iterate through changed columns, setting row pins, then latch
        for col in changed_cols:
            # set the column pins according to the base-two representation of the col
            self._cmd_mask[self.BCM['COL']] = np.fromiter(
                map(int, np.binary_repr(col, width=3)),
                dtype=np.bool
            )[::-1]

            # row pins are just binary
            self._cmd_mask[self.BCM['ROW']] = mask[:, col]

            # flush column
            self._latch_col()

        np.copyto(self._mask, mask)

    def _latch_col(self):
        """
        Latch the current active ``rows`` for the current active ``col``

        Write the current :attr:`._cmd_mask` to the pins and then flip ``PINS['ROW_LATCH']`` to store

        Create an integer representation of :attr:`._cmd_mask` by taking the dot product of it and :attr:`._powers` and sending to
        :meth:`pigpio.pi.set_bank_1` .

        If permission error for GPIO pins raised, log and return quietly. Otherwise raise exception from :meth:`pigpio.pi.set_bank_1`

        thanks https://stackoverflow.com/a/42058173/13113166 for the like omg how didn't i think of this idea for base conversion with dot products.
        """

        # ensure that the latch bit is currently low
        # self._cmd_mask[self.BCM['ROW_LATCH']] = False

        # create 32-bit int from _cmd_mask by multiplying by powers
        # cmd_int = np.dot(self._cmd_mask, self._powers)
        # try:
        #     self.pig.set_bank_1(cmd_int)
        # except Exception as e:
        #     # unhelpfully pigpio doesn't actually make error subtypes, so have to string detect
        #     # if it's the permission thing, just log it and return without raising exception
        #     if "no permission to update one or more GPIO" == str(e):
        #         self.logger.exception(str(e) + "in _latch_col")
        #         return
        #     else:
        #         raise e
        for pin in self.BCM['ROW'] + self.BCM['COL']:
            self.pig.write(pin, self._cmd_mask[pin])

        # latch the rows
        # self._hardware['ROW_LATCH'].pulse()
        self.pig.write(self.BCM['ROW_LATCH'], 1)
        self.pig.write(self.BCM['ROW_LATCH'], 0)

    @property
    def height(self) -> int:
        """
        Set the height!

        Returns:

        """
        return self._height

    @height.setter
    def height(self, height: int):
        if height < 0:
            height = 0

        steps = height - self._height
        if steps == 0:
            return
        elif steps > 0:
            self.direction = True
            self._update_script(steps)
        else:
            self.direction = False
            self._update_script(abs(steps))

        self._height = height
        
    @property
    def pulse_dur(self):
        return self._pulse_dur
    
    @pulse_dur.setter
    def pulse_dur(self, pulse_dur):
        self._pulse_dur = pulse_dur
        if self.movement_started:
            self._update_script()
        
    @property
    def delay_dur(self):
        return self._delay_dur
    
    @delay_dur.setter
    def delay_dur(self, delay_dur):
        self._delay_dur = delay_dur
        if self.movement_started:
            self._update_script()
        
    @property
    def movement_started(self) -> bool:
        """
        Whether the movement script has been started
        
        Returns:
            bool
        """

        if self._move_script_id is None:
            return False
        else:
            status = self.pig.script_status(self._move_script_id)
            if status == pigpio.PI_SCRIPT_RUNNING:
                return True
            else:
                return False