import datetime
import json
import os

from PySide2 import QtWidgets, QtGui
from autopilot import prefs


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

        self.protocol_dir = prefs.get('PROTOCOLDIR')

        tabWidget = QtWidgets.QTabWidget()

        self.bio_tab = self.Biography_Tab()
        tabWidget.addTab(self.bio_tab, "Biography")

        if self.protocol_dir:
            self.task_tab = self.Task_Tab()
            tabWidget.addTab(self.task_tab, "Protocol")

        buttonBox = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        buttonBox.accepted.connect(self.accept)
        buttonBox.rejected.connect(self.reject)

        mainLayout = QtWidgets.QVBoxLayout()
        mainLayout.addWidget(tabWidget)
        mainLayout.addWidget(buttonBox)
        self.setLayout(mainLayout)

        self.setWindowTitle("Setup New Subject")

    class Biography_Tab(QtWidgets.QWidget):
        """
        A widget that allows defining basic biographical attributes about a subject

        Creates a set of widgets connected to :py:meth:`~.Biography_Tab.update_return_dict` that stores the parameters.

        Warning:
            The below attributes are **not** the object attributes, but are descriptions of the parameters
            available in the values dictionary. The attributes themselves are PySide Widgets that set the values.

        Attributes:
            id (str): A Subject's ID or name
            start_date (str): The date the subject started the task. Automatically filled by
                :py:meth:`datetime.date.today().isoformat()`
            blmass (float): The subject's baseline mass
            minmass_pct (int): The percentage of baseline mass that a water restricted subject is allowed to reach
            minmass (float): The subject's minimum mass, automatically calculated `blmass * (minmass_pct / 100.)`
            genotype (str): A string describing the subject's genotype
            expt (str): A tag to describe what experiment this subject is a part of
        """
        def __init__(self):
            QtWidgets.QWidget.__init__(self)

            # Input Labels
            ID_label = QtWidgets.QLabel("ID:")
            start_label = QtWidgets.QLabel("Start Date:")
            blmass_label = QtWidgets.QLabel("Baseline Mass:")
            minmasspct_label = QtWidgets.QLabel("% of Baseline Mass:")
            minmass_label = QtWidgets.QLabel("Minimum Mass:")
            genotype_label = QtWidgets.QLabel("Genotype:")
            expt_label = QtWidgets.QLabel("Experiment Tag:")

            # Input widgets
            self.id = QtWidgets.QLineEdit()
            self.start_date = QtWidgets.QLineEdit(datetime.date.today().isoformat())
            self.blmass = QtWidgets.QLineEdit()
            self.blmass.setValidator(QtGui.QDoubleValidator(0.0, 30.0, 1, self.blmass))
            self.minmass_pct = QtWidgets.QSpinBox()
            self.minmass_pct.setRange(0,100)
            self.minmass_pct.setSingleStep(5)
            self.minmass_pct.setSuffix('%')
            self.minmass_pct.setValue(80)
            self.minmass = QtWidgets.QLineEdit()
            self.minmass.setValidator(QtGui.QDoubleValidator(0.0, 30.0, 1, self.minmass))
            self.genotype = QtWidgets.QLineEdit()
            self.expt     = QtWidgets.QLineEdit()

            # Set return dictionary signals
            self.id.editingFinished.connect(lambda: self.update_return_dict('id', self.id.text()))
            self.start_date.editingFinished.connect(lambda: self.update_return_dict('start_date', self.start_date.text()))
            self.blmass.editingFinished.connect(lambda: self.update_return_dict('baseline_mass', self.blmass.text()))
            self.minmass.editingFinished.connect(lambda: self.update_return_dict('min_mass', self.minmass.text()))
            self.genotype.editingFinished.connect(lambda: self.update_return_dict('genotype', self.genotype.text()))
            self.expt.editingFinished.connect(lambda: self.update_return_dict('experiment', self.expt.text()))

            # Set update minmass signals
            self.blmass.editingFinished.connect(self.calc_minmass)
            self.minmass_pct.valueChanged.connect(self.calc_minmass)

            # Setup Layout
            mainLayout = QtWidgets.QVBoxLayout()
            mainLayout.addWidget(ID_label)
            mainLayout.addWidget(self.id)
            mainLayout.addWidget(start_label)
            mainLayout.addWidget(self.start_date)
            mainLayout.addWidget(blmass_label)
            mainLayout.addWidget(self.blmass)
            mainLayout.addWidget(minmasspct_label)
            mainLayout.addWidget(self.minmass_pct)
            mainLayout.addWidget(minmass_label)
            mainLayout.addWidget(self.minmass)
            mainLayout.addWidget(genotype_label)
            mainLayout.addWidget(self.genotype)
            mainLayout.addWidget(expt_label)
            mainLayout.addWidget(self.expt)
            mainLayout.addStretch(1)

            self.setLayout(mainLayout)

            # Dictionary to return values
            self.values = {}

        def update_return_dict(self, key, val):
            """
            Called by lambda functions by the widgets, eg.::

                self.id.editingFinished.connect(lambda: self.update_return_dict('id', self.id.text()))

            Args:
                key (str): The key of the value being stored
                val: The value being stored.
            """
            self.values[key] = val
            # When values changed, update return dict

        def calc_minmass(self):
            """
            Calculates the minimum mass for a subject based on its baseline mass
            and the allowable percentage of that baseline
            """
            # minimum mass automatically from % and baseline
            baseline = float(self.blmass.text())
            pct = float(self.minmass_pct.text()[:-1])/100
            self.minmass.setText(str(baseline*pct))

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