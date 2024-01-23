from functools import reduce
from operator import ior

from PySide6 import QtWidgets

from autopilot.gui import _MAPS


def pop_dialog(message:str,
               details:str="",
               buttons:tuple=("Ok",),
               modality:str="nonmodal",
               msg_type:str="info",) -> QtWidgets.QMessageBox:
    """Convenience function to pop a :class:`.QtGui.QDialog window to display a message.

    .. note::

        This function does *not* call `.exec_` on the dialog so that it can be managed by the caller.

    Examples:
        box = pop_dialog(
            message='Hey what up',
            details='i got something to tell you',
            buttons = ('Ok', 'Cancel'))
        ret = box.exec_()
        if ret == box.Ok:
            print("user answered 'Ok'")
        else:
            print("user answered 'Cancel'")

    Args:
        message (str): message to be displayed
        details (str): Additional detailed to be added to the displayed message
        buttons (list): A list specifying which :class:`.QtWidgets.QMessageBox.StandardButton` s to display. Use a string matching the button name, eg. "Ok" gives :class:`.QtWidgets.QMessageBox.Ok`

            The full list of available buttons is::

                ['NoButton', 'Ok', 'Save', 'SaveAll', 'Open', 'Yes', 'YesToAll',
                 'No', 'NoToAll', 'Abort', 'Retry', 'Ignore', 'Close', 'Cancel',
                 'Discard', 'Help', 'Apply', 'Reset', 'RestoreDefaults',
                 'FirstButton', 'LastButton', 'YesAll', 'NoAll', 'Default',
                 'Escape', 'FlagMask', 'ButtonMask']

        modality (str): Window modality to use, one of "modal", "nonmodal" (default). Modal windows block nonmodal windows don't.
        msg_type (str): "info" (default), "question", "warning", or "error" to use :meth:`.QtGui.QMessageBox.information`,
            :meth:`.QtGui.QMessageBox.question`, :meth:`.QtGui.QMessageBox.warning`, or :meth:`.QtGui.QMessageBox.error`,
            respectively

    Returns:
        QtWidgets.QMessageBox
    """

    msgBox = QtWidgets.QMessageBox()

    # set text
    msgBox.setText(message)
    if details:
        msgBox.setInformativeText(details)

    # add buttons
    button_objs = [getattr(QtWidgets.QMessageBox, button) for button in buttons]
    # bitwise or to add them to the dialog box
    # https://www.geeksforgeeks.org/python-bitwise-or-among-list-elements/
    bitwise_buttons = reduce(ior, button_objs)
    msgBox.setStandardButtons(bitwise_buttons)

    if "Ok" in buttons:
        msgBox.setDefaultButton(QtWidgets.QMessageBox.Ok)

    icon = _MAPS['dialog']['icon'].get(msg_type, None)
    if icon is not None:
        msgBox.setIcon(icon)

    modality = _MAPS['dialog']['modality'].get(modality, None)
    if modality is not None:
        msgBox.setWindowModality(modality)

    return msgBox