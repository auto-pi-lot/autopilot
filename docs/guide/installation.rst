.. _installation:

Installation
************

Autopilot must be installed on the devices running the Terminal and the Pilot agents. The Pilot runs on a Raspberry Pi (remember: Pi for "Pilot") and the Terminal runs on a regular desktop computer. So Autopilot must be installed on both. This document will show you how to do that.

Supported Systems
===================

+----------------+-----------------------------------------------+
| OS             | * Pilot: raspiOS >=Buster (lite recommended)  |
|                | * Terminal: Ubuntu >=16.04                    |
+----------------+-----------------------------------------------+
| Python Version | >=3.7,<3.10                                   |
+----------------+-----------------------------------------------+
| Raspberry Pi   | >=3b (4b recommended)                         |
+----------------+-----------------------------------------------+

Autopilot is **linux/mac** only, and supports **Python 3.7 - 3.9** (3.10 will be supported after
updating the terminal to use PySide 6).
Some parts might accidentally work in Windows but we make no guarantees.

We have tried to take care to make certain platform-specific dependencies not break the entire package,
so if you have some difficulty installing autopilot on a non-raspberry-pi linux machine please submit an issue!

Pre-installation
=====================

On the Pilot device
-------------------

For Pilots, we recommend starting with a fresh `Raspbian Lite <https://downloads.raspberrypi.org/raspios_lite_armhf_latest.torrent>`_ image
(see `the raspi installation documentation <https://www.raspberrypi.org/documentation/installation/installing-images/README.md>`_ ).
Note that the Lite image doesn't include a desktop environment or GUI, just a command-line interface,
but that's all we need for the Pilot. It's easiest to connect a monitor and keyboard directly to the Pi while configuring it.
Once it's configured, you won't need to leave the monitor and keyboard attached, and/or you can choose to connect to it with ssh --
see the `headless setup <https://wiki.auto-pi-lot.com/index.php/Headless_Setup>`_ wiki page.

After the Pi has been started up for the first time, run `sudo raspi-config` to do things like connect to a wifi network, set the time zone, and so on. It's very important to change the password for the `pi` user account to a new one of your choice so that you don't get hacked, especially if you're opening up ssh access.

It's also best to update the Pi's operating system at this time::

    sudo apt update
    sudo apt upgrade -y

Now install the system packages that are required by Autopilot.
You can do this by running this command, or it's also available as a setup script
in the guided installation of Autopilot. (``python -m autopilot.setup.run_script env_pilot``) ::

    sudo apt install -y \
        python3-dev \
        python3-pip \
        git \
        libatlas-base-dev \
        libsamplerate0-dev \
        libsndfile1-dev \
        libreadline-dev \
        libasound-dev \
        i2c-tools \
        libportmidi-dev \
        liblo-dev \
        libhdf5-dev \
        libzmq3-dev \
        libffi-dev


On the Terminal device
----------------------

The following system packages are required by ``PySide2`` (which no longer packages ``xcb``)::

    sudo apt-get update && \
    sudo apt-get install -y \
      libxcb-icccm4 \
      libxcb-image0 \
      libxcb-keysyms1 \
      libxcb-randr0 \
      libxcb-render-util0 \
      libxcb-xinerama0 \
      libxcb-xfixes0

Installing Autopilot
====================
Now we're ready to install Autopilot on both the Pilot and Terminal devices. Follow the same instructions on both the Pi and the computer.

We recommend using autopilot within a virtual environment. Since v0.5.0 autopilot has been packaged
with `poetry <https://python-poetry.org/>`_ , which manages its own environment, but instructions for
using ``virtualenv`` and ``conda`` are in the guide page :ref:`guide_venvs` .

Optional dependencies
----------------------

Since autopilot is intended to be deployed as differentiable agents, we have separated the requirements
into different groups of optional dependencies. In each of the following commands, use the appropriate
package specifier like ``pip install auto-pi-lot[pilot]`` or ``poetry install -E pilot``

* **pilot** - includes ``pigpio`` to control GPIO pins and other pi-specific requirements
* **terminal** - includes ``PySide2`` and other terminal-specific requirements
* **docs** - includes ``Sphinx`` et al.
* **tests** - includes ``pytest`` et al.

Method 1: Installation from PyPI
--------------------------------

If you're just taking a look at Autopilot, the easiest way to get started is to install it from PyPI! ::

    pip3 install auto-pi-lot

Method 2: Installation from source
----------------------------------

If you want to start writing your own experiments and tinkering with Autopilot,
suggest you clone or fork `the repository <https://github.com/auto-pi-lot/autopilot/>`_ .
One of the design goals of autopilot is to minimize the distinction between "developer" and "user,"
so we like to encourage people to get their hands dirty with the source so your wonderful
work can be integrated later.

First clone the repository::

    git clone https://github.com/auto-pi-lot/autopilot.git
    cd autopilot

**Install with poetry** - if you have poetry installed (``pip install poetry``), it is easiest to use it
to manage your autopilot environment::

    poetry shell
    poetry install
    # or if installing optional dependencies
    # poetry install -E <optional>

**Install with pip** - install an "editable" version with `-e`, this makes it so python uses the source code in your
cloned repository, rather than from the system/venv libraries::

    pip3 install -e .[<optional>]

.. note::

    Depending on your permissions, eg. if you are not installing to a virtual environment, you may get a permissions error and need to install with the ``--user`` flag

.. note::

    Development work is done on the ``dev`` branch, which may have additional features/bugfixes but is much less stable!
    To use it just ``git checkout dev`` from your repository directory.
