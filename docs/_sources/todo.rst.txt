.. _todo:

To-Do
=====

* Upgrade to PySide 2 & Qt5
* Split the ncurses setup functions into multiple tabs, have them load exiting prefs, change values depending on config values (eg. selection Configuration : "VISUAL" should remove audio options)
* Unify "Parameters" across Autopilot
    - Rebuild protocol parameter handling to allow for stimulus managers, reward managers, graduation to populate their parameters in the GUI.
    - Specifically, want dropdown to select stim manager (sided, n sides, etc.), to create subwidget, then dropdown to select type of stim "audio", "visual" to control which are populated.
* Finalize continuous data handling in the :class:`~autopilot.core.subject.Subject` class.



