HAVE_PYSIDE = False
try:
    from PySide6 import QtCore
    HAVE_PYSIDE = True
except ImportError:
    pass

_INVOKER = None

if HAVE_PYSIDE:

    class InvokeEvent(QtCore.QEvent):
        """
        Sends signals to the main QT thread from spawned message threads

        See `stackoverflow <https://stackoverflow.com/a/12127115>`_
        """

        EVENT_TYPE = QtCore.QEvent.Type(QtCore.QEvent.registerEventType())

        def __init__(self, fn, *args, **kwargs):
            """
            Accepts a function, its args and kwargs and wraps them as a
            :class:`QtCore.QEvent`

            """
            QtCore.QEvent.__init__(self, InvokeEvent.EVENT_TYPE)
            self.fn = fn
            self.args = args
            self.kwargs = kwargs


    class Invoker(QtCore.QObject):
        """
        Wrapper that calls an evoked event made by :class:`.InvokeEvent`
        """
        def event(self, event):
            """
            Args:
                event:
            """
            event.fn(*event.args, **event.kwargs)
            return True


def get_invoker():
    if not globals()['HAVE_PYSIDE']:
        raise Exception("PySide6 could not be imported, no GUI event invoker can be gotten")
    if globals()['_INVOKER'] is None:
        globals()['_INVOKER'] = Invoker()
    return globals()['_INVOKER']