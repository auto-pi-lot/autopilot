.. _guide_hardware:

Writing a Hardware Class
************************

There are precious few requirements for :class:`~autopilot.core.hardware.Hardware` objects in Autopilot.

* Each class should have a ``release()`` method that stops any running threads and releases any system resources -- especially those held by pigpio.
* Each class should define a handful of class attributes when relevant
    - ``trigger`` (bool) - whether the device is used to trigger an event. if ``True``, ``assign_cb()`` must be defined and the device will be given a callback function by the instantiating :class:`~autopilot.tasks.task.Task` class
    - ``type`` (str) - what this device should be known as in ``prefs``. Not enforced currently, but will be.
    - ``input`` and ``output`` (bool) - whether the device is an input or output device, if either
* When making threaded methods, care should be taken not to spawn an excessive number of running threads, but this is a performance rather than a structural limit.

To use a hardware object in a task, its parameters (especially the pin number for pigpio-based hardware) should be
stored in ``prefs.json``.

A few basic Hardware classes are dissected in this section to illustrate basic principles of their design,
but we expect Hardware objects to be extremely variable in their implementation and application.

.. to-do::

    In future versions of Autopilot, the structure of hardware ``prefs`` will be formalized similarly to
    the preamble of tasks to make establishing and maintaining parameterizations more transparent.

GPIO with pigpio
=====================

Autopilot uses `pigpio <http://abyz.me.uk/rpi/pigpio/>`_ to interface with the Raspberry Pi's GPIO pins.
All `pigpio <http://abyz.me.uk/rpi/pigpio/>`_ objects require that a pigpiod daemon is running as a background
process. Typically this is managed by systemd or the launch script generated for Pilots.

When instantiating a piece of hardware, it must connect to pigpiod by creating a `pigpio.pi <http://abyz.me.uk/rpi/pigpio/python.html#pigpio.pi>`_ object,
which allows communication with the GPIO.

Input - Beambreak
-----------------

The :class:`~autopilot.core.hardware.Beambreak` class is a digital input class that registers (by default)
a high-to-low logic transition and calls a callback function. When it is initialized, it
connects to a GPIO pin, configures it for input, and sets the pull-up (or down) resistor.

.. code-block:: python

    class Beambreak(Hardware):
        # this class description has been simplified for clarity

        trigger = True
        type    = 'POKES'
        input   = True


        def __init__(self, pin, pull_ud='U', trigger_ud='D', event=None):

            # Make pigpio instance
            self.pig = pigpio.pi()

            # Convert pin from board to bcm numbering
            self.pin = BOARD_TO_BCM[int(pin)]

            # save which direction our trigger should be
            # TRIGGER_MAP takes string directions - eg. 'D' for 'Down'
            # or falling edge detection - and converts them to
            # pigpio constants
            self.trigger_ud = TRIGGER_MAP[trigger_ud]

            # Setup pin
            self.pig.set_mode(self.pin, pigpio.INPUT)
            self.pig.set_pull_up_down(self.pin, self.pull_ud)

            # create empty list of callbacks
            # (to handle multiple callbacks, if needed)
            self.callbacks = []

Since ``trigger == True``, the instantiating task class will try to give it a method to call
to handle the trigger. We redefine ``assign_cb()`` to make use of pigpio's callback functionality.
Since pigpio can handle multiple callback functions, one can optionally specify ``add=True``
to prevent any previous callbacks from being cleared. This has been omitted in this example for clarity,
but can be inspected in the API documentation for the :class:`~autopilot.core.hardware.Beambreak` class.

.. code-block:: python

        def assign_cb(self, callback_fn):
            cb = self.pig.callback(self.pin, self.trigger_ud, callback_fn)
            self.callbacks.append(cb)

To clean up the connection to the pin made by this instance of the object, we must also redefine
the ``release`` method. We also redefine ``__del__`` to attempt cleanup if the object is garbage-collected
without explicitly calling ``release()``

.. code-block:: python

        def release(self):
            self.pig.stop()

        def __del__(self):
            self.release()

Output - LED_RGB
----------------

This :class:`~autopilot.core.hardware.LED_RGB` class is a bit different. It's an output device, yes, but it also manages
multiple pins, uses pulse-width modulation rather than strict binary logic, and
has a few extra tricks up its sleeve.

Its initialization is similar to :class:`~autopilot.core.hardware.Beambreak` except we add
a few :class:`threading.Event` s to handle threaded lighting routines. LEDs can either be
`common anode or common cathode <https://forum.digikey.com/t/common-anode-vs-common-cathode/808>`_
which affects the polarity of the pulse-width modulated signal, but handling different LED polarity
has been omitted for brevity.

.. code-block:: python

    class LED_RGB(Hardware):
        # this class has also been simplified for clarity

        output = True
        type="LEDS"

        def __init__(self, pins = None):

            # Dict to store color for after flash trains
            self.stored_color = {}

            # Event to wait on setting colors if we're flashing
            self.flash_block = threading.Event()
            self.flash_block.set()

            # Event to kill the flash thread if the object is deleted
            self.end_thread = threading.Event()
            self.end_thread.clear()

            # Initialize connection to pigpio daemon
            self.pig = pigpio.pi()

            # Convert to BCM numbers
            self.pins = {k: BOARD_TO_BCM[v] for k, v in self.pins.items()}

            # set pin mode to output and make sure they're turned off
            for pin in self.pins.values():
                self.pig.set_mode(pin, pigpio.OUTPUT)
                self.pig.set_PWM_dutycycle(pin, 0)

Setting colors is straightforward - we are given a length-3 tuple of 8-bit (0-255) RGB color values
and set the pulse-width modulated duty cycle accordingly. We use a recursive :class:`threading.Timer`
in order to manage timed light flashes -- after some duration, the `set_color()` method is called
turning the lights off.

.. code-block:: python

        def set_color(self, col, timed=False):

            # unpack color
            color = {'r':int(col[0]), 'g':int(col[1]), 'b':int(col[2])}

            for k, v in color.items():
                self.pig.set_PWM_dutycycle(self.pins[k], v)

            # If this is is a timed blink, start thread to turn led off
            if timed:
                # timed should be a float or int specifying the delay in ms
                offtimer = threading.Timer(float(timed)/1000,
                                           self.set_color,
                                           kwargs={'col':[0,0,0]})
                offtimer.start()

In order to implement flash trains or other rapid sequences of lights, we make a
``color_series`` method that takes a list of rgb tuples and either a single duration (which
is applied to all colors in the series) or a series of durations of equal length to the list of colors.

``color_series`` is a convenience function that spawns a thread to handle the color series without blocking.
The actual ``threaded_color_series`` method has a few extra bells and whistles to make sure
series don't overlap with one another, it is simplified here to illustrate the principle.

.. code-block:: python

        def color_series(self, colors, durations):
            series_thread = threading.Thread(target=self.threaded_color_series,
                                             kwargs={
                                                'colors'   : colors,
                                                'durations' : durations
                                             })
            series_thread.start()

        def threaded_color_series(self, colors, durations):
            # assume len(colors) == len(duration)
            # for this example. Iterate through both, setting colors
            for color, duration in zip(colors, durations):
                self.set_color(color)
                time.sleep(duration/1000.0)

With one more layer of abstraction we can create a ``flash`` method that lets us cycle through
colors with a specific frequency rather than by defining color and duration series by hand

.. code-block:: python

        def flash(self, duration, frequency=10, colors=((255,255,255), (0,0,0))):

            # Get number of flashes in duration rounded down
            n_rep = int(duration / 1000.0 * frequency)

            # Invert frequency to duration for single flash
            # divide by 2 b/c each 'color' is half the duration
            single_dur = ((1. / frequency) * 1000) / 2.

            # make tuples of flashes and durations
            flashes = colors * n_rep
            durations = [duration] * n_rep


            self.color_series(flashes, durations)

The ``release`` function is also the same, we just make sure to turn the LEDs off before we leave them

.. code-block:: python

        def release(self):
            self.set_color((0,0,0))
            self.pig.stop()


USB Hardware with inputs
========================

USB hardware logic is much more variable than GPIO-based hardware, so we'll wait for you to help
us with good examples!

For example, the :class:`~autopilot.core.hardware.Wheel` class
discussed previously in :ref:`wheel_guide_one` reads mouse events with the `inputs <https://inputs.readthedocs.io/en/latest/>`_
package like this:

.. code-block:: python

    from inputs import devices

    mouse = devices.mice[some_index_for_your_mouse]
    event = mouse.read()

the ``event`` object has three attributes of interest, ``event.state``, ``event.code``, and
``event.timestamp``. The ``code`` tells us if the event was a movement (ie. ``REL_X`` or ``REL_Y``
in the case of computer mice, as opposed to click events), and the ``state`` tells us how much.

The :class:`~autopilot.core.hardware.Wheel` class then creates a numpy array of movements like this:

.. code-block:: python

    # filter events
    events = [e for e in events if e.code in ('REL_X', 'REL_Y)]

    # extract tuples of attributes
    events = [(e.state, e.code, e.timestamp) for e in events]

    # convert to numpy array
    events = np.array(events, dtype=np.int)



















