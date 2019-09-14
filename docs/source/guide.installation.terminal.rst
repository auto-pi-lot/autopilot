.. _setup_terminal:

Terminal Setup
*********************

The Terminal is the user-facing Agent in Autopilot.

It provides a GUI used to control task operation on a set of Pilots, as well as a few calibration and maintenance routines.

We have found that locally compiling Qt4 and PySide increases stability, but using precompiled binaries shouldn't be qualitatively different.

Installing Qt4
==============

Note:
    Since Autopilot was developed, `PySide 2 <https://pypi.org/project/PySide2/>`_ which uses Qt5 has been released. We will be upgrading Autopilot to use it in the next minor release.

