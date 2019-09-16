.. _setup_terminal:

Terminal Setup
*********************

The Terminal is the user-facing Agent in Autopilot.

It provides a GUI used to control task operation on a set of Pilots, as well as a few calibration and maintenance routines.

We have found that locally compiling Qt4 and PySide increases stability, but using precompiled binaries shouldn't be qualitatively different.

Prerequisites
=============

The terminal requires:

* libzmq - the zeromq messaging library
* Qt4 - the GUI library

and the Python packages:

* tables>=3.4.2
* numpy>=1.12.1
* pyzmq>=17.1.2
* pandas>=0.19.2
* npyscreen
* scipy
* tornado
* inputs

**macOS:**::
    brew install hdf5 zmq
    pip install tables numpy pyzmq pandas npyscreen scipy tornado inputs



Scripted Terminal Setup
=======================

1. The :any:`~autopilot.setup.presetup_terminal.sh` script automates the manual presetup below. It..
    * Downloads, compiles, and installs Qt4
    * Downloads, compiled, and installs PySide
2. The :any:`~autopilot.setup.setup_terminal` script sets two configuration options
    * **BASE_DIR:** The base directory used by Autopilot to store data, configuration, etc.
    * **MSGPORT:** The port used by the Terminal to send and receive messages.

    It then creates the basic directory structure used by the Terminal and creates a launch script (ie. ``<BASE_DIR>/launch_terminal.sh``).

The Terminal does not run as a systemd service, and must be launched each time it is used (typically from ``/usr/autopilot/launch_terminal.sh``)

Manual Terminal Presetup
========================

Both of these steps take an enormous amount of time, so plan to start the compilation and go get a cup of coffee.

Compiling & Installing Qt4 - Linux
----------------------------------

Note:
    Since Autopilot was developed, `PySide 2 <https://pypi.org/project/PySide2/>`_ which uses Qt5 has been released. We will be upgrading Autopilot to use it in the next minor release.

1. Download `Qt4.8.7 <https://download.qt.io/archive/qt/4.8/4.8.7/qt-everywhere-opensource-src-4.8.7.zip>`_
2. Unzip with the -a flag::

    unzip -a ./<qt archive>.zip

3. Optionally, to speed compilation, building the ``examples`` and ``demos`` can be disabled by commenting the following lines in ``projects.pro``::

    #       SUBDIRS += examples
    } else:isEqual(PROJECT, demos) {
    #       SUBDIRS += demos

4. Configure, make and install as usual. Use ``./configure -h`` to see all configuration options.::

    ./configure \
        -debug \
        -opensource \
        -optimized-qmake \
        -separate-debug-info \
        -no-webkit \
        -opengl

    make -j10
    sudo -H make install

Installing Qt4 - MacOS
----------------------

MacOS's g++ is pretty whacky, it's easier to install from the Mac Package (with debug libs):

* `Download Qt4 for Mac <https://download.qt.io/archive/qt/4.8/4.8.5/qt-mac-opensource-4.8.5.dmg>`_
* Mount image, run setup

Compiling & Installing PySide - Linux
-----------------------------

1. Clone the PySide repository::

    git clone https://github.com/PySide/pyside-setup.git

2. Run the ``setup.py`` script to build the wheel and then install. Note that you need to provide the location of ``qmake`` from Qt4 manually, which can usually be found with ``which qmake``::

    cd pyside-setup
    python setup.py bdist_wheel --qmake=</location/of/qt4/qmake> --standalone
    sudo -H pip install dist/<name-of-pyside-wheel>.whl


Installing PySide - Mac
-----------------------

Mac has PySide
