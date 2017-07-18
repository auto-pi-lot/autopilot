.. highlight:: python

Low-latency sound
=================

This document explains how we achieve sound delivery with low-latency.

Triggering sounds
-----------------
The state-machine running in the Arduino Due has the ability to send one output byte through a serial port (``native`` port on the board) when reaching a state. See ``enter_state()`` function in ``statemachine.ino``.
This serial output serves as a trigger for the computer to generate a sound.

On the computer end, the sound module (object ``soundclient.SoundPlayer``) is always waiting for serial inputs. Whenever a serial input arrives, the system will play the sound with index specified by the byte sent.

Note that currently only one sound can be triggered per state.

Sound generation
----------------
We use the Python module "`pyo`_"  to generate sounds. In addition to having many functions for sound generation, this module works with Jack for low-latency delivery of sounds (see below).
However, it is not clear if this module is still maintained, and documentation is limited.

.. _pyo: https://code.google.com/p/pyo/

Sound card
----------
To be able to generate sound above 20kHz, we use a `Xonar Essence STX`_ sound-card from ASUS.

.. _Xonar Essence STX: http://www.asus.com/Sound_Cards_and_DigitaltoAnalog_Converters/Xonar_Essence_STX/


Achieving low-latency
---------------------
In our experience, triggers through the serial port are very fast (<1ms). The delay bewteen the Arduino triggering a sound and the sound being produced by the sound-card is due mostly to the computer's sound system.

To achieve lower latencies, we use a combination of:

* Low-latency Linux kernel: package ``linux-lowlatency`` in Ubuntu.
* Jack: a low-latency sound server. Package ``jackd`` in Ubuntu.

We first run the Jack server (and keep it open), with the command:
``pasuspender -- /usr/bin/jackd -R -dalsa -dhw:STX -r192000 -p512 -n2``

In a paradigm, using the sound-client object (``soundclient.SoundClient``) will start ``pyo`` and generate all sounds through Jack.



