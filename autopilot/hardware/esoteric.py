import itertools
import typing
from time import sleep, time
from enum import IntEnum, Enum, auto

from autopilot.hardware import Hardware, BOARD_TO_BCM
from autopilot.hardware.gpio import GPIO, Digital_Out

import numpy as np

ENABLED = False
try:
    import pigpio
    ENABLED = True
except ImportError:
    pass

class Parallax_Platform(Hardware):
    """
    Control an array of stepper motors

    Pinout is detailed in :attr:`.PINS` - for this array, individual motors are controlled with a latch system, so
    all active rows within a specified column are specified by a pattern of GPIO pin logic, and then the ``ROW_LATCH`` pin
    is flipped to store them. 2d patterns are virtualized in software in :attr:`.mask` and :attr:`.height` .

    Height can be set in 3 ways:

    1. By setting a :attr:`.mask` of active columns and passing an integer to :attr:`.height` -- this doesn't require manipulating the latching
    logic, and so is non-blocking.

    2. By passing an array of heights to :attr:`.height` - this must manipulate the latching logic for every different
    height and so blocks out of necessity

    3. By slicing and assigning to the object -- this also blocks

    Examples:

        >>> import numpy as np
        >>> from autopilot.hardware.esoteric import Parallax_Platform

        instantiate the platform

        >>> plat = Parallax_Platform()

        **1) Control pillars with a mask and an integer**

        set all columns in row 2 to be active

        >>> mask = np.zeros((6,6), dtype=np.bool)
        >>> mask[2,:] = True
        >>> mask
        array([[False, False, False, False, False, False],
               [False, False, False, False, False, False],
               [ True,  True,  True,  True,  True,  True],
               [False, False, False, False, False, False],
               [False, False, False, False, False, False],
               [False, False, False, False, False, False]])
        >>> plat.mask = mask

        set height with an integer (number of steps) -- all activated pillars move to same height

        >>> plat.height = 1000

        **2) set height with an array of heights for each pillar**

        eg. a sine wave

        >>> height = np.round((np.sin(np.linspace(-np.pi, np.pi, 6))+1)*5000).astype(np.int32)
        >>> height = np.repeat(height[np.newaxis,:], 6, axis=0)
        >>> height
        array([[5000,  245, 2061, 7939, 9755, 5000],
               [5000,  245, 2061, 7939, 9755, 5000],
               [5000,  245, 2061, 7939, 9755, 5000],
               [5000,  245, 2061, 7939, 9755, 5000],
               [5000,  245, 2061, 7939, 9755, 5000],
               [5000,  245, 2061, 7939, 9755, 5000]], dtype=int32)

        >>> plat.height = height

        **3) Set height by slicing the object**

        all slices compatible with np.array should work :)

        >>> plat[0,1] = 500
        >>> plat[:,2] = 1000


    Todo:

        The platform is intended to have two modes -- position and velocity (see :attr:`.Move_Modes` and
        :attr:`.move_mode`), where the user can either set a position or set a velocity. The velocity mode has been
        implemented in :meth:`.start_move_script` but has not yet been exposed to the object.

    Args:
        pulse_dur (int): duration of stepper pulse used while in 'position' mode (see :attr:`.move_mode`) in  microseconds
        delay_dur (int): duration of delay between stepper pulses used while in 'position' mode in microseconds, so frequency of stepper
            pulses is ``1/(pulse_dur+delay_dur)``
        join_delay (float): duration (in ms) to wait between checking the status of the movement script when using :meth:`.join`
        unit_mode (:attr:`Parallax_Platform.Unit_Modes`): Whether :attr:`.height` accepts/returns heights in ``STEPS`` or ``MM`` (default)
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
    
    * ``COL`` : bitwise-anded with powers of 2 to select pins, ie.::
    
        on_rows = 0b010 # the center, or first row is on
        col[0] =  on_rows & 0b001 # 1
        col[1] =  on_rows & 0b010 # 2
        col[2] =  on_rows & 0b100 # 4
        
    * ``ROW`` : binary flags for each row in the specified ``COL``, ie.::
    
        PINS['ROW'] = np.array([0,0,1,0,0,1], dtype=np.bool)
        
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
    MAX_HEIGHT = 10000 # type: int
    """max height of pillars, in steps"""

    init_pigpio = GPIO.init_pigpio

    # --------------------------------------------------
    # Movement Script Parameterization
    # --------------------------------------------------
    HEIGHT_VAR = 2 #: Variable for storing height for POSITION mode
    PULSE_VAR = 0 #: Variable for storing pulse duration in pigpio (in microseconds)
    DELAY_VAR = 1 #: Variable for storing duration between pulses in pigpio (in microseconds)
    # pulse_dur = 100 #: Duration of step pulse (in microseconds)
    # delay_dur = 100 #: Duration of delay between pulses (in microseconds)
    MOVE_MODE_VAR = 3 #: Variable to set movement mode
    STEPS_VAR = 4 #: Variable to store cumulative steps taken (the "real" height tracked during position or velocity mode)



    class Move_Modes(IntEnum):
        POSITION = 1 #: Move to a specified position at velocity determined by :attr:`pulse_dur` + :attr:`.delay_dur`
        VELOCITY = 0 #: Move continuously at at velocity determined by :attr:`pulse_dur` + :attr:`.delay_dur`

    class Unit_Modes(Enum):
        """Whether :attr:`.height` returns/accepts heights in steps or mm"""
        STEPS = auto()
        MM = auto()




    # DEFAULT_OFFSET = np.array((
    #     (26, 25, 25, 22, 26, 24),
    #     (26, 29, 27, 25, 25, 26),
    #     (24, 25, 25, 30, 25, 26),
    #     (27, 26, 27, 24, 29, 28),
    #     (26, 26, 28, 27, 26, 29),
    #     (26, 27, 28, 27, 20, 19)
    # ))*20 # type: np.ndarray
    DEFAULT_OFFSET = np.array([
       [250, 250, 200, 250, 250, 250],
       [250, 300, 300, 300, 250, 250],
       [250, 250, 200, 250, 250, 250],
       [250, 250, 300, 250, 250, 350],
       [250, 250, 200, 350, 200,   0],
       [100, 250, 250, 250, 300,   0]]
    ) # type: np.ndarray
    """
    Offset for each pillar for use with :meth:`.level`
    """

    STEPS_PER_REV = 800 # type: int
    """
    Set by the DIP-switches on the stepper driver, how many steps are there per revolution of the linear actuator rod?
    """

    REV_HEIGHT = 8.0 # type: float
    """
    How much do the platforms move for one revolution of the linear actuator? (in  mm, determined empirically)
    """

    MM_PER_STEP = REV_HEIGHT/STEPS_PER_REV # type: float
    """
    How many mm do the platforms move for every step? (in mm)
    """



    def __init__(self,
                 pulse_dur: int = 10,
                 delay_dur: int = 190,
                 join_delay: float = .001,
                 unit_mode: Unit_Modes = Unit_Modes.MM,
                 *args, **kwargs):
        super(Parallax_Platform, self).__init__(*args, **kwargs)

        # --------------------------------------------------
        # attribute init
        # --------------------------------------------------

        self.pig = None # type: typing.Optional[pigpio.pi]
        self.pigpiod = None
        
        self._direction = False # type: bool
        self._mask = np.zeros(self.GRID_DIM,
                              dtype=np.bool) # current binary mask
        self._hardware = {} # type: typing.Dict[str, Digital_Out]
        """
        container for :class:`.Digital_Out` objects (for move, direction, etc)
        """
        self._cmd_mask = np.zeros((32), dtype=np.bool) # type: np.ndarray
        """32-bit boolean array to store the binary mask to the gpio pinsv"""
        self._powers = 2 ** np.arange(32)
        """powers to take dot product of _cmd_mask to get integer from bool array
        
        Examples:
            self.pi.set_bank_1(np.dot(self._cmd_mask, self._powers))"""
        
        self._pulse_dur = int(pulse_dur) # type: int
        self._delay_dur = int(delay_dur) # type: int
        # store the given delay_dur to restore when returning from velocity mode
        self._delay_dur_store = int(delay_dur) # type: int
        self.join_delay = int(join_delay) # type: float
        self.unit_mode = unit_mode

        # _height used for controlling stepper motor, but
        # _height_arr stores heights of all columns
        self._height = 0 # type: typing.Optional[int]
        self._height_arr = np.zeros(self.GRID_DIM, dtype=np.int32) # type: np.ndarray
        self._move_script_id = None # type: typing.Optional[int]
        self._move_mode = self.Move_Modes.POSITION # type: Parallax_Platform.Move_Modes

        # store current velocity when in velocity mode
        self._velocity = 0 # type: float

        # --------------------------------------------------
        # gpio initialization
        # --------------------------------------------------
        self.CONNECTED = False # type: bool
        self.CONNECTED = self.init_pigpio()

        self.init_pins()

        # --------------------------------------------------
        # movement init
        # --------------------------------------------------
        self.start_move_script()
        
        
        # --------------------------------------------------
        # zeroing
        # --------------------------------------------------
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
        * compare :attr:`.HEIGHT_VAR` to accumulator (always left at zero)
        * if :attr:`.HEIGHT_VAR` is zero, jump back to ``999``
        * otherwise flip ``BCM['MOVE']`` on and off for :attr:`.PULSE_VAR` microseconds
        * decrement :attr:`.HEIGHT_VAR` and jumpy back to ``999``

        Movement parameters can be changed with calls to `pig.update_script <http://abyz.me.uk/rpi/pigpio/python.html#update_script>`_
        for example::

            pulse_dur = 50
            delay_dur = 100
            N_STEPS = 100

            self.pig.update_script(script_id, (N_STEPS, pulse_dur, delay_dur))

        Which is wrapped in the private method :meth:`.Parallax_Platform._update_script`

        """

        tags = {
            'init': '999',
            'mode_velocity': '998',
            'mode_position': '997',
            'move': '996',
            'increment_steps': '995',
            'decrement_steps': '994'
        }

        # script explained in docstring
        init = f"tag {tags['init']}" # load variable 0 with 0, used as position storage
        # do the delay we promise to control velocity
        # if DELAY_VAR is 0, continue to wait (special case -- for velocity == 0)
        wait = f"mics p{self.DELAY_VAR} lda 0 cmp p{self.DELAY_VAR} jz {tags['init']}"
        # load the accumulator with 0, compare the move mode variable
        # jump to step tag if in velocity mode (always move), or to position check
        # if in position mode
        # NOTE -- while POSITION == 1 and VELOCITY == 0, the test for moving to position mode is
        # positive because cmp does accumulator-variable, so 0-1==-1.
        # otherwise if zero jump to move
        # if u know of a better way of 'loading' a parameter for use with script
        select_mode = f"lda 0 cmp p{self.MOVE_MODE_VAR} jz {tags['move']}"
        # compare the set height to the current steps
        # if they're the same, then jump back to wait
        # for now assume direction has been set correctly
        check_position = f"lda p{self.STEPS_VAR} cmp p{self.HEIGHT_VAR} jz {tags['init']}"
        move_steppers = f"tag {tags['move']} w {self.BCM['MOVE']} 1 mics p{self.PULSE_VAR} w {self.BCM['MOVE']} 0"
        increment_steps = f"r {self.BCM['DIRECTION']} jz {tags['decrement_steps']} inr p{self.STEPS_VAR} jmp {tags['init']}"
        decrement_steps = f"tag {tags['decrement_steps']} dcr p{self.STEPS_VAR} jmp {tags['init']}"

        script = ' '.join((init, wait, select_mode, check_position, move_steppers, increment_steps, decrement_steps))
        script = script.encode('utf-8')

        # gather params and default in order given by class attrs
        params = {
            self.PULSE_VAR: self.pulse_dur,
            self.DELAY_VAR: self.delay_dur,
            self.HEIGHT_VAR: 0,
            self.MOVE_MODE_VAR: int(self.move_mode),
            self.STEPS_VAR: 0
        }
        param_tup = tuple(param for ind, param in sorted(params.items()))

        # initialize and run script
        self._move_script_id = self.pig.store_script(script)
        self.pig.run_script(self._move_script_id, param_tup)

    def _update_script(self, steps=None):
        """update the running movement script
        if steps is None, don't fuck with them, just update the other params"""
        if self._move_script_id is None:
            self.logger.warning('attempted to update script, but script not initialized')
            return

        if steps is None:
            params = {
                self.PULSE_VAR: self.pulse_dur,
                self.DELAY_VAR: self.delay_dur,
                self.HEIGHT_VAR: self.height,
                self.MOVE_MODE_VAR: int(self.move_mode)
            }
        else:
            params = {
                self.PULSE_VAR: self.pulse_dur,
                self.DELAY_VAR: self.delay_dur,
                self.HEIGHT_VAR: self.height,
                self.MOVE_MODE_VAR: int(self.move_mode),
                self.STEPS_VAR: int(steps)
            }

        param_tup = tuple(param for ind, param in sorted(params.items()))
        self.pig.update_script(self._move_script_id, param_tup)

    @property
    def direction(self) -> bool:
        """Direction of movement of platforms

        Property reads pin state directly, setter changes pin state and updates :attr:`._cmd_mask`

        direction is stored in ``_direction`` for fast, internal access.

        Returns:
            bool: ``True`` = Up, ``False`` = Down
        """
        self._direction = bool(self.pig.read(self.BCM['DIRECTION']))
        return self._direction

    @direction.setter
    def direction(self, direction: bool):
        self._direction = direction
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
            self._cmd_mask[self.BCM['ROW']] = np.invert(mask[:, col])

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
        return self._height

    @height.setter
    def height(self, height: typing.Union[int, np.ndarray]):
        """
        Set the height!

        Note:
            Passing an array will always block, as the method has to coordinate each column flip

        Args:
            height (int, :class:`numpy.ndarray`): If given an ``int`` , move all active pillars to that height
                if given a :class:`numpy.ndarray` of dimensions :attr:`.GRID_DIM` , set every pillar to the specified height

        Returns:
            int: the internal :attr:`._height` counter used with the pigpio script
        """

        if self.move_mode is not self.Move_Modes.POSITION:
            self.move_mode = self.Move_Modes.POSITION

        if isinstance(height, int):


            height = np.full(self.GRID_DIM, height, dtype=np.int32)

            try:
                # if all platforms active are same height, do quick move without blocking
                if np.all(self.height_arr[self.mask] == self.height_arr[self.mask][0]):

                    self.direction = bool((height[0,0] - self.height)>0)
                    self._height = int(height[0,0])
                    self._height_arr = height
                    self._update_script()
                    return
            except IndexError as e:
                # if mask is all off, return with a warning
                if not np.any(self.mask):
                    self.logger.warning('attempted to set height with integer, but no pillars are activated. make sure some pillars are activated in .mask, or set height with an array')
                    return
                else:
                    # otherwise it's some other exception and we should raise it
                    raise e

        # clip array
        height = np.clip(height, 0, self.MAX_HEIGHT)

        # keep a copy of the mask to restore it afterwards
        _mask = np.copy(self.mask)

        # first move pillars up that need to go up
        moveme = height-self.height_arr
        self.direction = True
        while (moveme > 0).any():
            moveme_mask = moveme>0
            self.mask = moveme_mask
            # move up by the minimum difference
            steps = np.min(moveme[moveme_mask])
            self._height_arr[moveme_mask] += steps
            self._height += steps
            self._update_script()
            self.join()
            moveme = height - self.height_arr

        self.direction = False
        while (moveme < 0).any():
            moveme_mask = moveme < 0
            self.mask = moveme_mask

            steps = np.max(moveme[moveme_mask])
            self._height_arr[moveme_mask] += steps
            self._height += steps
            self._update_script()
            self.join()
            moveme = height - self.height_arr

        # restore mask
        self.mask = _mask

    @property
    def height_arr(self) -> np.ndarray:
        """
        Array of all pillar heights

        Note:
            Don't set height here! use :attr:`.height`

        Returns:
            np.ndarray: heights of each pillar (in steps)
        """
        return self._height_arr

    def __getitem__(self, key) -> int:
        """
        Control pillar height like a numpy array

        Returns:
            (int, :class:`numpy.ndarray`): Current height of single or sliced pillar
        """
        return self.height_arr[key]

    def __setitem__(self, key, value):
        height = np.copy(self.height_arr)
        height[key] = value
        self.height = height

        
    @property
    def pulse_dur(self):
        return self._pulse_dur
    
    @pulse_dur.setter
    def pulse_dur(self, pulse_dur):
        if self._pulse_dur != pulse_dur:
            self._pulse_dur = pulse_dur
            if self.movement_started:
                self._update_script()
        
    @property
    def delay_dur(self):
        return self._delay_dur
    
    @delay_dur.setter
    def delay_dur(self, delay_dur: int):
        """
        Delay duration between pulses in microseconds

        Args:
            delay_dur (int): microseconds

        Returns:
            int: microseconds
        """
        if self._delay_dur != delay_dur:
            self._delay_dur = delay_dur
            if self.movement_started:
                self._update_script()
            
    @property
    def move_mode(self):
        return self._move_mode
    
    @move_mode.setter
    def move_mode(self, move_mode):
        # if switching into velocity mode, clear velocity
        if self._move_mode == self.Move_Modes.POSITION and move_mode == self.Move_Modes.VELOCITY:
            self._velocity = 0
        elif self._move_mode == self.Move_Modes.VELOCITY and move_mode == self.Move_Modes.POSITION:
            self._delay_dur = self._delay_dur_store
            # TODO: Get height from script and update our internal height variable

        self._move_mode = move_mode

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
            status, _ = self.pig.script_status(self._move_script_id)
            if status == pigpio.PI_SCRIPT_RUNNING:
                return True
            else:
                return False

    @property
    def velocity(self):
        return self._velocity

    @velocity.setter
    def velocity(self, velocity):
        """
        Set velocity when in velocity mode

        Converts velocity to a :attr:`.

        Args:
            Velocity (float): Velocity in mm/s

        Returns:
            (float) Velocity in mm/s
        """
        if self.move_mode != self.Move_Modes.VELOCITY:
            self.logger.warning('Tried to set velocity but in POSITION mode!')
            return

        # convert velocity to delay dur

        if velocity == 0:
            # special case -- rather than an infinite duration,
            # movement script keeps returning to init tag when delay dur is 0
            self.delay_dur = 0
        else:
            # (mm/s) / (mm/steps) = steps/s
            # 1/(steps/s) = (inter-step interval in s)*1000000 (to micros)
            # delay_dur = (inter-step interval) - (pulse_dur)
            # TODO: clip delay dur for asymptotically slow velocities
            delay_dur = round(((1/(velocity/self.MM_PER_STEP)*1000000) - self.pulse_dur))
            if delay_dur < 0:
                self.logger.warning(f"Could not set velocity to {velocity}, pulse dur {self.pulse_dur} is too long to go this fast!")
                return
            self.logger.debug(f"setting delay_dur to {delay_dur} for velocity {velocity}")
            self.delay_dur = delay_dur

        self._velocity = velocity

        # self._update_script()

    # --------------------------------------------------
    # methods
    # --------------------------------------------------

    def level(self, amount:int=MAX_HEIGHT):
        """
        Lower all the platforms down by :attr:`.MAX_HEIGHT` steps, then raises each by :attr:`.DEFAULT_OFFSET`

        Args:
            amount (int): amount to lower platforms (default is :attr:`.MAX_HEIGHT`)

        """

        # tell the movement script that all the pillars at MAX_HEIGHT and to bring them to zero
        self.mask = np.ones(self.GRID_DIM, dtype=np.bool)
        self._height = 0
        self._move_mode = self.Move_Modes.POSITION
        self.direction = False
        self._update_script(steps=amount)
        self.join()

        # now use height to raise them
        self._height_arr = np.zeros(self.GRID_DIM, dtype=np.int32)
        self.height = self.DEFAULT_OFFSET

        # then reset attrs
        self._height = 0
        self._height_arr = np.zeros(self.GRID_DIM, dtype=np.int32)
        self._update_script(steps = 0)



    def join(self, join_delay: typing.Optional[float] = None, timeout: float = 10):
        """
        Block until movement is completed.

        Args:
            join_delay (None, float): duration between checks of movement script in seconds.
                if None, use :attr:`.join_delay` .
            timeout (float): maximum number of seconds to block

        Note:
            Only relevant in ``POSITION`` mode.
        """
        if not self.movement_started or self.move_mode is not self.Move_Modes.POSITION:
            return

        start_wait = time()

        _, pars = self.pig.script_status(self._move_script_id)
        # steps = pars[self.HEIGHT_VAR]
        while pars[self.HEIGHT_VAR] != pars[self.STEPS_VAR]:
            sleep(self.join_delay)
            _, pars = self.pig.script_status(self._move_script_id)

            if time()-start_wait > timeout:
                break







    def release(self):
        if self.movement_started:
            self.pig.stop_script(self._move_script_id)
            self.pig.delete_script(self._move_script_id)

        for pin in self.BCM['ROW'] + self.BCM['COL'] + [self.BCM['MOVE'], self.BCM['ROW_LATCH'], self.BCM['DIRECTION']]:
            self.pig.write(pin, 0)

        self.pig.stop()



