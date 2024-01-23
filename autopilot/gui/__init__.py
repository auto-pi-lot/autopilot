"""
These classes implement the GUI used by the Terminal.

The GUI is built using `PySide6 <https://doc.qt.io/qtforpython/>`_, a Python wrapper around Qt5.

These classes are all currently used only by the :class:`~.autopilot.agents.terminal.Terminal`.

If performing any GUI operations in another thread (eg. as a callback from a networking object),
the method must be decorated with `@gui_event` which will call perform the update in the main thread as required by Qt.

.. note::

    Currently, the GUI code is some of the oldest code in the library --
    in particular much of it was developed before the network infrastructure was mature.
    As a result, a lot of modules are interdependent (eg. pass objects between each other).
    This will be corrected before v1.0

"""

from PySide6 import QtWidgets, QtCore

_MAPS = {
    'dialog': {
        'icon': {
            'info': QtWidgets.QMessageBox.Information,
            'question': QtWidgets.QMessageBox.Question,
            'warning': QtWidgets.QMessageBox.Warning,
            'error': QtWidgets.QMessageBox.Critical
        },
        'modality': {
            'modal': QtCore.Qt.NonModal,
            'nonmodal': QtCore.Qt.WindowModal
        }
    }
}