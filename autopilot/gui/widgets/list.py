
from PySide6 import QtWidgets, QtCore

class Drag_List(QtWidgets.QListWidget):
    """
    A :class:`QtWidgets.QListWidget` that is capable of having files dragged & dropped.

    copied with much gratitude from `stackoverflow <https://stackoverflow.com/a/25614674>`_

    Primarily used in :class:`.Sound_Widget` to be able to drop sound files.

    To use: connect `fileDropped` to a method, that method will receive a list of files
    dragged onto this widget.

    Attributes:
        fileDropped (:class:`QtCore.Signal`): A Qt signal that takes a list
    """
    fileDropped = QtCore.Signal(list)

    def __init__(self):
        # type: () -> None
        super(Drag_List, self).__init__()
        self.setAcceptDrops(True)

    def dragEnterEvent(self, e):
        """
        When files are dragged over us, if they have paths in them,
        accept the event.

        Args:
            e (:class:`QtCore.QEvent`): containing the drag information.
        """
        if e.mimeData().hasUrls:
            e.accept()
        else:
            e.ignore()

    def dragMoveEvent(self, event):
        """
        If the `dragEnterEvent` was accepted, while the drag is being moved within us,
        `setDropAction` to :class:`.QtCore.Qt.CopyAction`

        Args:
            event (:class:`QtCore.QEvent`): containing the drag information.
        """
        if event.mimeData().hasUrls:
            event.setDropAction(QtCore.Qt.CopyAction)
            event.accept()
        else:
            event.ignore()

    def dropEvent(self, event):
        """
        When the files are finally dropped, if they contain paths,
        emit the list of paths through the `fileDropped` signal.

        Args:
            event (:class:`QtCore.QEvent`): containing the drag information.
        """
        if event.mimeData().hasUrls:
            event.setDropAction(QtCore.Qt.CopyAction)
            event.accept()
            links = []
            for url in event.mimeData().urls():
                links.append(str(url.toLocalFile()))
            self.fileDropped.emit(links)
        else:
            event.ignore()