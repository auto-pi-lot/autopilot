.. _setup_terminal:

Terminal Setup
*********************

The Terminal is the user-facing Agent in Autopilot.

It provides a GUI used to control task operation on a set of Pilots, as well as a few calibration and maintenance routines.

.. versionchanged:: 0.3.0

    Autopilot now uses Python3, so we have upgraded PySide/Qt4 to PySide2/Qt5, which dramatically simplifies installation!!


Prerequisites
=============

The terminal requires:

* libzmq - the zeromq messaging library
* Qt5 - the GUI library

and the Python packages:

* tables>=3.4.2
* numpy>=1.12.1
* pyzmq>=17.1.2
* pandas>=0.19.2
* npyscreen
* scipy
* tornado
* inputs
* blosc
* scikit-video
* PySide2
* tqdm
* pyqtgraph>=0.11.0 - must be installed after Qt + pyside from git repo currently

**macOS:**::

    brew install hdf5 zmq
    pip3 install tables numpy pyzmq pandas npyscreen scipy tornado inputs blosc scikit-video PySide2 tqdm



Scripted Terminal Setup
=======================

1. The ``presetup_terminal.sh`` script automates the manual presetup below. It..

    * Installs system & python dependencies
    * Installs the development version of ``pyqtgraph``

2. The ``setup_terminal.py`` script sets configuration options for ``prefs``:

    * **BASEDIR** - Base directory for all local autopilot data, typically `/usr/autopilot`
    * **MSGPORT** - Port to use for our ROUTER listener, default `5560`
    * **DATADIR** -  `os.path.join(params['BASEDIR'], 'data')`
    * **SOUNDDIR** - `os.path.join(params['BASEDIR'], 'sounds')`
    * **PROTOCOLDIR** - `os.path.join(params['BASEDIR'], 'protocols')`
    * **LOGDIR** - `os.path.join(params['BASEDIR'], 'logs')`
    * **VIZDIR** - `os.path.join(params['BASEDIR'], 'logs')` directory to store generated visualizations
    * **REPODIR** - Path to autopilot git repo
    * **PILOT_DB** - Location of `pilot_db.json` used to populate :attr:`~.Terminal.pilots`
    * **DRAWFPS** - fps to update :class:`.gui.Video` windows
    * **LOGLEVEL** - level for systemwide logging, see :data:`.LOG_LEVELS`

    It then creates the basic directory structure used by the Terminal and creates a launch script (ie. ``<BASE_DIR>/launch_terminal.sh``).

The Terminal does not run as a systemd service, and must be launched each time it is used (typically from ``/usr/autopilot/launch_terminal.sh``)

