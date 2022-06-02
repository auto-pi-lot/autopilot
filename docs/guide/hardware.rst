.. _guide_hardware:

.. important::

    This guide and :ref:`guide_task` are lightly out of date with v0.4.0 of autopilot, but still largely reflect the
    program design and its operation. This guide in particular became obsolete because most extensions to
    hardware objects are now done by subclassing generic hardware classes like :class:`.hardware.gpio.GPIO`
    and their descendents, which make it relatively clear what parts of the object need to be modified.

    As such, this part of the docs was deprecated in v0.3.0 and has been mostly removed in v0.4.0 pending a fuller rewrite.

    For now, see the API documentation section for :mod:`~autopilot.hardware` for more details
    on how to extend hardware classes :)

    Sorry for the inconvenience, we
    are a very small team and can only do so much work between releases! We'd be happy to get
    `documentation requests <https://github.com/auto-pi-lot/autopilot/issues/32>`_ or even a pull request or two to help
    us out until we can get to it :)

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

GPIO with pigpio
=====================

Autopilot uses `pigpio <http://abyz.me.uk/rpi/pigpio/>`_ to interface with the Raspberry Pi's GPIO pins.
All `pigpio <http://abyz.me.uk/rpi/pigpio/>`_ objects require that a pigpiod daemon is running as a background
process. This used to be done by a launch script that started the pilots, but is now typically launched by
:func:`autopilot.external.start_pigpiod`, which is called by :meth:`.GPIO.init_pigpio` so in general you shouldn't
need to worry about it. If ``pigpiod`` is open in a separate process, or left open from a previous crashed run of Autopilot,
you will likely need to kill that process before you can use more GPIO-based autopilot objects.

When instantiating a piece of hardware, it must connect to pigpiod by creating a `pigpio.pi <http://abyz.me.uk/rpi/pigpio/python.html#pigpio.pi>`_ object,
which allows communication with the GPIO. This is provided by the :attr:`.GPIO.pig` property. The rest of the methods of
GPIO-based objects are built around abstractions of commands to the ``pig``. See :class:`.gpio.LED_RGB` for an example of
a subclass that overrides some methods from the :class:`.gpio.GPIO` metaclass to be able to control three PWM objects
with a similar syntax as other GPIO outputs.

