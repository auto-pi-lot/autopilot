import json
import os

from PySide6 import QtWidgets
from autopilot import prefs
from autopilot.data.models.biography import Biography
from autopilot.gui.widgets.model import ModelWidget
from autopilot.utils.loggers import init_logger


class New_Subject_Wizard(QtWidgets.QDialog):
    """
    A popup that prompts you to define variables for a new :class:`.subject.Subject` object

    Called by :py:meth:`.Control_Panel.create_subject` , which handles actually creating
    the subject file and updating the :py:attr:`.Terminal.pilots` dict and file.

    Contains two tabs
    - :class:`~.New_Subject_Wizard.Biography_Tab` - to set basic biographical information about a subject
    - :class:`~.New_Subject_Wizard.Task_Tab` - to set the protocol and step to start the subject on

    Attributes:
        protocol_dir (str): A full path to where protocols are stored,
            received from :py:const:`.prefs.get('PROTOCOLDIR')`
        bio_tab (:class:`~.New_Subject_Wizard.Biography_Tab`): Sub-object to set and store biographical variables
        task_tab (:class:`~.New_Subject_Wizard.Task_Tab`): Sub-object to set and store protocol and step assignment
    """

    def __init__(self):
        QtWidgets.QDialog.__init__(self)
        self.logger = init_logger(self)

        self.protocol_dir = prefs.get('PROTOCOLDIR')

        tabWidget = QtWidgets.QTabWidget()

        self.bio_tab = ModelWidget(Biography)
        tabWidget.addTab(self.bio_tab, "Biography")

        if self.protocol_dir:
            self.task_tab = self.Task_Tab()
            tabWidget.addTab(self.task_tab, "Protocol")

        buttonBox = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        buttonBox.accepted.connect(self._accept)
        buttonBox.rejected.connect(self.reject)

        mainLayout = QtWidgets.QVBoxLayout()
        mainLayout.addWidget(tabWidget)
        mainLayout.addWidget(buttonBox)
        self.setLayout(mainLayout)

        self.setWindowTitle("Setup New Subject")

    def _accept(self):
        # validate model
        self.logger.debug('Clicked OK to create subject')
        model = self.bio_tab.validate(dialog=True)
        if not isinstance(model, Biography):
            return
        self.accept()


    class Task_Tab(QtWidgets.QWidget):
        """
        A tab for selecting a task and step to assign to the subject.

        Reads available tasks from `prefs.get('PROTOCOLDIR')` , lists them, and
        creates a spinbox to select from the available steps.

        Warning:
            Like :class:`.Biography_Tab` , these are not the actual instance attributes.
            Values are stored in a `values` dictionary.

        Attributes:
            protocol (str): the name of the assigned protocol, filename without .json extension
            step (int): current step to assign.
        """
        def __init__(self):
            QtWidgets.QWidget.__init__(self)

            self.protocol_dir = prefs.get('PROTOCOLDIR')

            topLabel = QtWidgets.QLabel("Protocols:")

            # List available protocols
            protocol_list = os.listdir(self.protocol_dir)
            protocol_list = [os.path.splitext(p)[0] for p in protocol_list]

            self.protocol_listbox = QtWidgets.QListWidget()
            self.protocol_listbox.insertItems(0, protocol_list)
            self.protocol_listbox.currentItemChanged.connect(self.protocol_changed)

            # Make Step combobox
            self.step_selection = QtWidgets.QComboBox()
            self.step_selection.currentIndexChanged.connect(self.step_changed)

            layout = QtWidgets.QVBoxLayout()
            layout.addWidget(topLabel)
            layout.addWidget(self.protocol_listbox)
            layout.addWidget(self.step_selection)

            self.setLayout(layout)

            # Dict to return values
            self.values = {}

        def update_step_box(self):
            """
            Clears any steps that might be in the step selection box,
            loads the protocol file and repopulates it.
            """
            # Clear box
            while self.step_selection.count():
                self.step_selection.removeItem(0)

            # Load the protocol and parse its steps
            protocol_str = self.protocol_listbox.currentItem().text()
            protocol_file = os.path.join(self.protocol_dir,protocol_str + '.json')
            with open(protocol_file) as protocol_file_open:
                protocol = json.load(protocol_file_open)

            step_list = []
            self.step_ind   = {}
            for i, s in enumerate(protocol):
                step_list.append(s['step_name'])
                self.step_ind[s['step_name']] = i

            self.step_selection.insertItems(0, step_list)
            self.step_selection.setCurrentIndex(0)

        def protocol_changed(self):
            """
            When the protocol is changed, save the value and call :py:meth:`.update_step_box`.
            """
            self.values['protocol'] = self.protocol_listbox.currentItem().text()
            self.update_step_box()

        def step_changed(self):
            """
            When the step is changed, save it.
            """
            current_step = self.step_selection.currentText()
            # Check that we have selected a step...
            if current_step != '':
                self.values['step'] = self.step_ind[current_step]