# Classes that house hardware logic

try:
    import RPi.GPIO as GPIO # TODO: Redo Beambreak class with pigpio, it just is better in every way
except:
    pass

try:
    import pigpio
except:
    pass

import threading
import time

# pigpio only uses BCM numbers, we need to translate them
# See https://www.element14.com/community/servlet/JiveServlet/previewBody/73950-102-11-339300/pi3_gpio.png
BOARD_TO_BCM = {
     3: 2,   5: 3,   7: 4,   8: 14, 10: 15,
    11: 17, 12: 18, 13: 27, 15: 22, 16: 23,
    18: 24, 19: 10, 21: 9,  22: 25, 23: 11,
    24: 8,  26: 7,  29: 5,  31: 6,  32: 12,
    33: 13, 35: 19, 36: 16, 37: 26, 38: 20,
    40: 21
}
BCM_TO_BOARD = dict([reversed(i) for i in BOARD_TO_BCM.items()])

# TODO: Subclass nosepoke that knows about waiting for mouse leaving
class Beambreak:
    # IR Beambreak sensor
    def __init__(self, pin, pull_ud='U', trigger_ud='D', event=None):
        # Make pigpio instance
        self.pig = pigpio.pi()

        # Convert pin from board to bcm numbering
        self.pin = BOARD_TO_BCM[int(pin)]

        # TODO: Wrap pull_ud and trigger_ud as 'types' so can be set in prefs
        self.pull_ud = None
        if pull_ud == 'U':
            self.pull_ud = pigpio.PUD_UP
        elif pull_ud == 'D':
            self.pull_ud = pigpio.PUD_DOWN

        # TODO: Make dependent on pull_ud, instead of rising, falling, etc. have user input be "in" "out"
        self.TRIGGER_MAP = {
            'U': pigpio.RISING_EDGE,
            'D': pigpio.FALLING_EDGE,
            'B': pigpio.EITHER_EDGE
        }
        self.trigger_ud = self.TRIGGER_MAP[trigger_ud]

        # We can be passed a threading.Event object if we want to handle stage logic here
        # rather than in the parent as is typical.
        self.event = event

        # List to store callback handles
        self.callbacks = []

        # Setup pin
        self.pig.set_mode(self.pin, pigpio.INPUT)
        self.pig.set_pull_up_down(self.pin, self.pull_ud)

    def assign_cb(self, callback_fn, add=False, evented=False, manual_trigger=None):
        # If we aren't adding, we clear any existing callbacks
        if not add:
            self.clear_cb()

        # We can set the direction of the trigger manually,
        # for example if we want to set 'BOTH' only sometimes
        if not manual_trigger:
            trigger_ud = self.trigger_ud
        else:
            trigger_ud = self.TRIGGER_MAP[manual_trigger]

        # We can handle eventing (blocking) here if we want (usually this is handled in the parent)
        # This won't work if we weren't init'd with an event.
        if evented:
            cb = self.pig.callback(self.pin, trigger_ud, self.event.set)
            self.callbacks.append(cb)

        cb = self.pig.callback(self.pin, trigger_ud, callback_fn)
        self.callbacks.append(cb)

    def clear_cb(self):
        for cb in self.callbacks:
            try:
                cb.cancel()
            except:
                pass
        self.callbacks = []

    # TODO: Add cleanup so task can be closed and another opened

class LED_RGB:
    def __init__(self, pins = None, r = None, g=None, b=None, common = 'anode'):
        # Can pass RGB pins as list or as kwargs "r", "g", "b"
        # Can be configured for common anode (low turns LED on) or cathode (low turns LED off)
        self.common = common

        # Initialize connection to pigpio daemon
        self.pig = pigpio.pi()
        if not self.pig.connected:
            Exception('No connection to pigpio daemon could be made')

        # Unpack input
        self.pins = {}
        if r and g and b:
            self.pins['r'] = int(r)
            self.pins['g'] = int(g)
            self.pins['b'] = int(b)
        elif isinstance(pins, list):
            self.pins['r'] = int(pins[0])
            self.pins['g'] = int(pins[1])
            self.pins['b'] = int(pins[2])
        else:
            Exception('Dont know how to handle input to LED_RGB')

        # Convert to BCM numbers
        self.pins = {k: BOARD_TO_BCM[v] for k, v in self.pins.items()}

        # set pin mode to output and make sure they're turned off
        for pin in self.pins.values():
            self.pig.set_mode(pin, pigpio.OUTPUT)
            if self.common == 'anode':
                self.pig.set_PWM_dutycycle(pin, 255)
            elif self.common == 'cathode':
                self.pig.set_PWM_dutycycle(pin, 0)
            else:
                Exception('Common passed to LED_RGB not anode or cathode')

        # Blink to show we're alive
        self.color_series([[255,0,0],[0,255,0],[0,0,255],[0,0,0]], 250)

        # Event to wait on setting colors if we're flashing
        self.flash_block = threading.Event()
        self.flash_block.set()

    def set_color(self, col=None, r=None, g=None, b=None, timed=None):
        # Unpack input
        if r and g and b:
            color = {'r':int(r), 'g':int(g), 'b':int(b)}
        elif isinstance(col, list):
            color = {'r':int(col[0]), 'g':int(col[1]), 'b':int(col[2])}
        else:
            Warning('Color improperly formatted')
            return

        # Wait to set if we're currently flashing or doing a color series
        self.flash_block.wait()

        # Set PWM dutycycle
        if self.common == 'anode':
            for k, v in color.items():
                self.pig.set_PWM_dutycycle(self.pins[k], 255-v)
        elif self.common == 'cathode':
            for k, v in color.items():
                self.pig.set_PWM_dutycycle(self.pins[k], v)

        # If this is is a timed blink, start thread to turn led off
        if timed:
            # timed should be a float or int specifying the delay in ms
            offtimer = threading.Timer(float(timed)/1000, self.set_color, kwargs={'col':[0,0,0]})
            offtimer.start()

    def flash(self, duration, frequency=20, colors=[[255,255,255],[0,0,0]]):
        # Duration is total in ms, frequency in Hz
        # Get number of flashes in duration rounded down
        n_rep = int(float(duration/1000)*frequency)
        flashes = colors*n_rep

        # Invert frequency to duration for single flash
        single_dur = (1./frequency)*1000
        self.color_series(flashes, single_dur)

    def color_series(self, colors, duration):
        # Colors needs to be a list of a list of integers
        # Duration (ms) can be an int (same duration of all colors) or a list

        # Just a wrapper to make threaded
        series_thread = threading.Thread(target=self.threaded_color_series, kwargs={'colors':colors, 'duration':duration})
        series_thread.start()

    def threaded_color_series(self, colors, duration):
        self.flash_block.clear()
        if isinstance(duration, int) or isinstance(duration, float):
            for c in colors:
                self.set_color(c)
                time.sleep(float(duration)/1000)
        elif isinstance(duration, list) and (len(colors) == len(duration)):
            for i, c in enumerate(colors):
                self.set_color(c)
                time.sleep(float(duration[i])/1000)
        else:
            Exception("Dont know how to handle your color series")
            return
        self.flash_block.set()

class Solenoid:
    # Solenoid valves for water delivery
    def __init__(self, pin, duration=100):
        # Initialize connection to pigpio daemon
        self.pig = pigpio.pi()
        if not self.pig.connected:
            Exception('No connection to pigpio daemon could be made')

        # Setup port
        self.pin = BOARD_TO_BCM[int(pin)]
        self.pig.set_mode(self.pin, pigpio.OUTPUT)

        # Pigpio has us create waves to deliver timed output
        # Since we typically only use one duration,
        # we make the wave once and only make it again when asked to
        # We start with passed or default duration (ms)
        self.duration = int(duration)
        self.wave_id = None
        self.make_wave()

    def make_wave(self, duration=None):
        # TODO: Is there any point in storing multiple waves?
        # Typically duration is stored as an attribute, but if we are passed one...
        if duration:
            self.duration = int(duration)

        self.pig.wave_clear()
        # Make a pulse (duration is in microseconds for pigpio, ours is in milliseconds
        reward_pulse = [pigpio.pulse(1<<self.pin, 0, self.duration*1000)]
        self.pig.wave_add_generic(reward_pulse)
        self.wave_id = self.pig.wave_create()


    def open_valve(self, duration=None):
        # If we are passed a duration, check if we have a wave for it
        if duration:
            # If not, make one
            if int(duration) != self.duration:
                self.duration = int(duration)
                self.make_wave()

        self.pig.wave_send_once(self.wave_id)


