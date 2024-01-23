from functools import wraps

from autopilot.utils.invoker import get_invoker, InvokeEvent
from PySide6 import QtCore

def gui_event(fn):
    """
    Wrapper/decorator around an event that posts GUI events back to the main
    thread that our window is running in.

    Args:
        fn (callable): a function that does something to the GUI
    """
    @wraps(fn)
    def wrapper_gui_event(*args, **kwargs):
        """

        Args:
            *args ():
            **kwargs ():
        """
        QtCore.QCoreApplication.postEvent(get_invoker(), InvokeEvent(fn, *args, **kwargs))
    return wrapper_gui_event