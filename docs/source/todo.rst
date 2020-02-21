Development Roadmap, Minor To-dos, and all future plans :)

.. _todo:

To-Do
=====

* Split the ncurses setup functions into multiple tabs, have them load exiting prefs, change values depending on config values (eg. selection Configuration : "VISUAL" should remove audio options)
* Unify "Parameters" across Autopilot
    - Rebuild protocol parameter handling to allow for stimulus managers, reward managers, graduation to populate their parameters in the GUI.
    - Specifically, want dropdown to select stim manager (sided, n sides, etc.), to create subwidget, then dropdown to select type of stim "audio", "visual" to control which are populated.
* Finalize continuous data handling in the :class:`~autopilot.core.subject.Subject` class.
* Sound Calibration
.. _setup_routines:
* Setup routines and prefs editing
* Visualization & data server
* Error reporting, status checking for pilots
* Mesh Networking
* Parameter updating in subjects via GUI
* Parameter updating in plot objects -- generally more interactive plot customization



Completed Goals
---------------

* :ref:`changelog_v030` - Upgrade to Python 3
* :ref:`changelog_v030` - Upgrade to PySide 2 & Qt5


