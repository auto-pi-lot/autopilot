.. _quickstart:

Quickstart
***********

Autopilot is an integrated system for coordinating all parts of an experiment, but it is also designed to be permissive
about how it is used and to make transitioning from existing lab tooling gentler -- so its modules can be used independently.

To get a sample of autopilot, you can check out some of its modules without doing a fully configured :ref:`installation` .
As you get more comfortable using Autopilot, adopting more of its modules and usage patterns makes integrating each of the
separate modules simpler and more powerful, but we'll get there in time.

Minimal Installation
====================

Say you have a Raspberry Pi with `Raspbian installed <https://www.raspberrypi.org/documentation/installation/installing-images/README.md>`_ .
Install autopilot and its basic system dependencies & configuration like this::

    pip3 install auto-pi-lot
    python3 -m autopilot.setup.run_script env_pilot pigpiod

Blink an LED
============

Say you connect an LED to one of the :mod:`~.hardware.gpio` pins - let's say (board numbered) pin 7. Love 7. Great pin.

Control the LED by using the :class:`.gpio.Digital_Out` class::

    from autopilot.hardware.gpio import Digital_Out
    led = Digital_Out(pin=7)

    # turn it on!
    led.set(1)

    # turn if off!
    led.set(0)

Or, blink "hello" in morse code!

::

    letters = [
        ['dot', 'dot', 'dot', 'dot'],  # h
        ['dot'],                       # e
        ['dot', 'dash', 'dot', 'dot'], # l
        ['dot', 'dash', 'dot', 'dot'], # l
        ['dash', 'dash', 'dash']       # o
    ]
    # make a series of 1's and 0's, which will last for the time_unit
    times = {'dot': [1, 0], 'dash': [1, 1, 1, 0], 'space':[0]*3}
    binary_letters = []
    for letter in letters:
        binary_letters.extend([value for char in letter for value in times[char]])
        binary_letters.extend(times['space'])

    time_unit = 100 #ms
    led.series(id='hello', values=binary_letters, durations=time_unit)

Capture Video
=============

Say you have a `Raspberry Pi Camera Module <https://www.raspberrypi.org/products/camera-module-v2/>`_ , capture some
video! First make sure the camera is enabled::

    python3 -m autopilot.setup.run_script picamera

and then capture a video with :class:`.cameras.PiCamera` and write it to ``test_video.mp4``::

    from autopilot.hardware.cameras import PiCamera
    cam = PiCamera()
    cam.write('test_video.mp4')
    cam.capture(timed=10)

.. note::

    Since every hardware object in autopilot is by default nonblocking (eg. work happens in multiple threads, you can
    make other calls while the camera is capturing, etc.), this will work in an interactive python session but would require
    that you ``sleep`` or call ``cam.stoppping.join()`` or some other means of keeping the process open.

While the camera is capturing, you can access its current frame in its ``frame`` attribute, or to make sure you get
every frame, by calling :meth:`~.cameras.Camera.queue` .

Communicate Between Computers
=============================

Synchronization and coordination of code across multiple computers is a very general problem, and an increasingly
common one for neuroscientists as we try to combine many hardware components to do complex experiments.

Say our first raspi has an IP address ``192.168.0.101`` and we get another raspi whose IP is ``192.168.0.102`` . We can
send messages between the two using two :class:`.networking.Net_Node` s. :class:`.networking.Net_Node` s send messages with
a ``key`` and ``value`` , such that the ``key`` is used to determine which of its ``listens`` methods/functions it should
call to handle ``value`` .

For this example, how about we make pilot 1 ping pilot 2 and have it respond with the current time?

On pilot 2, we make a node that listens for messages on port 5000. The ``upstream`` and ``port`` arguments here
don't matter since this node doesn't initiate any connection, just received them (we'll use a global variable here and hardcode
the return id since we're in scripting mode, but there are better ways to do this in autopilot proper)::

    from autopilot.networking import Net_Node
    from datetime import datetime
    global node_2

    def thetime(value):
        global node_2
        node_2.send(
            to='pilot_1', key='THETIME',
            value=datetime.now().isoformat()
        )

    node_2 = Net_Node(
        id='pilot_2', router_port=5000, upstream='', port=9999,
        listens={'WHATIS':thetime}
    )

On pilot 1, we can then make a node that connects to pilot 2 and prints the time when it receives a response::

    from autopilot.networking import Net_Node

    node_1 = Net_Node(
        id='pilot_1', upstream='pilot_2',
        port=5000, upstream_ip = '192.168.0.102',
        listens = {'THETIME':print}
    )

    node_1.send(to='pilot_1', key='WHATIS')

Realtime DeepLabCut
======================

Autopilot integrates `DeepLabCut-Live <https://github.com/DeepLabCut/DeepLabCut-live/>`_ :cite:`kaneRealtimeLowlatencyClosedloop2020` !
You can use your own pretrained models (stored in your autopilot user directory under `/dlc` ) or models from the
`Model Zoo <http://www.mackenziemathislab.org/dlc-modelzoo>`_ .

Now let's say we have a desktop linux machine with DeepLabCut and dlc-live installed. DeepLabCut-Live is implemented
in Autopilot with the :class:`.transform.image.DLC` object, part of the :mod:`.transform` module.

First, assuming we have some image ``img`` (as a numpy array), we can process the image to get a pandas dataframe of
each of the tracked points::

    from autopilot import transform as t
    import numpy as np

    dlc = t.image.DLC(model_zoo='full_human')
    points = dlc.process(img)

Autopilot's transform module lets us compose multiple data transformations together with ``+`` to make deploying chains of computation
to other computers. How about we process an image and determine whether the left hand in the image is raised above the head?::

    # select the two body parts, which will return a 2x2 array
    dlc += t.selection.DLCSlice(select=('wrist1', 'forehead'))

    # slice out the 1st column (y) with a tuple of slice objects
    dlc += t.selection.Slice(select=(
        slice(start=0,stop=2),
        slice(start=1,stop=2)
    ))

    # compare the first (wrist) y position to the second (forehead)
    dlc += t.logical.Compare(np.greater)

    # use it!
    dlc.process(img)

Put it Together - Close a Loop!
===============================

We've tried a few things, why not put them together? 


