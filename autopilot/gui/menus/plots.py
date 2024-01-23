import copy

import numpy as np
from PySide6 import QtWidgets, QtGui

from autopilot.data import Subject


class Psychometric(QtWidgets.QDialog):
    """
    A Dialog to select subjects, steps, and variables to use in a psychometric curve plot.

    See :meth:`.Terminal.plot_psychometric`

    Args:
        subjects_protocols (dict): The Terminals :attr:`.Terminal.subjects_protocols` dict

    Attributes:
        plot_params (list): A list of tuples, each consisting of (subject_id, step, variable) to be given to :func:`.viz.plot_psychometric`
    """

    def __init__(self, subjects_protocols):
        super(Psychometric, self).__init__()

        self.subjects = subjects_protocols
        # self.protocols = protocols
        # self.protocol_dir = prefs.get('PROTOCOLDIR')
        self.subject_objects = {}

        self.init_ui()


    def init_ui(self):
        self.grid = QtWidgets.QGridLayout()

        # top row just has checkbox for select all
        check_all = QtWidgets.QCheckBox()
        check_all.stateChanged.connect(self.check_all)

        self.grid.addWidget(check_all, 0,0)
        self.grid.addWidget(QtWidgets.QLabel('Check All'), 0, 1)

        # identical to Reassign, above
        for i, (subject, protocol) in zip(range(len(self.subjects)), self.subjects.items()):
            subject_name = copy.deepcopy(subject)
            step = protocol[1]

            # container for each subject's GUI object
            # checkbox, step, variable
            self.subject_objects[subject] = [QtWidgets.QCheckBox(),  QtWidgets.QComboBox(), QtWidgets.QComboBox(), QtWidgets.QLineEdit()]

            # include checkbox
            checkbox = self.subject_objects[subject][0]
            checkbox.setObjectName(subject_name)
            # checkbox.stateChanged.connect(self.select_subject)
            # self.checks.append(this_checkbox)

            # subject label
            subject_lab = QtWidgets.QLabel(subject_name)

            # protocol_box = self.subject_objects[subject][0]
            # protocol_box.setObjectName(subject_name)
            # protocol_box.insertItems(0, self.protocols)
            # # set current item if subject has matching protocol
            # protocol_bool = [protocol == p for p in self.protocols]
            # if any(protocol_bool):
            #     protocol_ind = np.where(protocol_bool)[0][0]
            #     protocol_box.setCurrentIndex(protocol_ind)
            # protocol_box.currentIndexChanged.connect(self.set_protocol)
            self.populate_steps(subject_name)
            step_box = self.subject_objects[subject][1]
            step_box.setObjectName(subject_name)
            step_box.currentIndexChanged.connect(self.populate_variables)



            # variable box
            var_box = self.subject_objects[subject][2]
            var_box.setObjectName(subject_name)

            # n most recent trials
            n_trials_box = self.subject_objects[subject][3]
            # verify that an int is given
            n_trials_box.setValidator(QtGui.QIntValidator())
            n_trials_box.setText("-1")

            # set index of current step to populate variables
            step_box.setCurrentIndex(step)

            # add layout
            self.grid.addWidget(checkbox, i+1, 0)
            self.grid.addWidget(subject_lab, i+1, 1)
            self.grid.addWidget(step_box, i+1, 2)
            self.grid.addWidget(var_box, i+1, 3)
            self.grid.addWidget(n_trials_box, i+1, 4)

        # finish layout
        buttonBox = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        buttonBox.accepted.connect(self.accept)
        buttonBox.rejected.connect(self.reject)
        main_layout = QtWidgets.QVBoxLayout()
        main_layout.addLayout(self.grid)
        main_layout.addWidget(buttonBox)

        self.setLayout(main_layout)





    def populate_steps(self, subject):
        """
        When a protocol is selected, populate the selection box with the steps that can be chosen.

        Args:
            subject (str): ID of subject whose steps are being populated
        """
        # protocol_str = self.subjects[subject][0]
        step_box = self.subject_objects[subject][1]

        while step_box.count():
            step_box.removeItem(0)

        # open the subject file and use 'current' to get step names
        asub = Subject(subject)

        step_list = []
        for s in asub.current:
            step_list.append(s['step_name'])

        step_box.insertItems(0, step_list)

    def populate_variables(self):
        """
        Fill selection boxes with step and variable names
        """
        # get step number from step box

        subject = self.sender().objectName()
        step_ind = self.subject_objects[subject][1].currentIndex()

        # the variables box
        var_box = self.subject_objects[subject][2]
        while var_box.count():
            var_box.removeItem(0)

        # open the subjet's file and get a description of the data for this
        this_subject = Subject(subject)
        step_data = this_subject.get_trial_data(step=step_ind, what="variables")
        # should only have one step, so denest
        step_data = step_data[step_data.keys()[0]]

        # iterate through variables, only keeping numerics
        add_vars = []
        for col_name, col_type in step_data.items():
            if issubclass(col_type.dtype.type, np.integer) or issubclass(col_type.dtype.type, np.floating):
                add_vars.append(col_name)

        var_box.insertItems(0, add_vars)



    def check_all(self):
        """
        Toggle all checkboxes on or off
        """
        # check states to know if we're toggling everything on or off
        check_states = [objs[0].checkState() for objs in self.subject_objects.values()]

        toggle_on = True
        if all(check_states):
            toggle_on = False


        for objs in self.subject_objects.values():
            if toggle_on:
                objs[0].setCheckState(True)
            else:
                objs[0].setCheckState(False)

    @property
    def plot_params(self):
        """
        Generate parameters for plot to be passed to :func:`.viz.plot_psychometric`

        Returns:
            tuple: (subject_name, step_name, x_var_name, n_trials_back)
        """
        _plot_params = []

        for sub_name, objs in self.subject_objects.items():
            if objs[0].checkState():
                _plot_params.append((
                    sub_name,
                    objs[1].currentText(),
                    objs[2].currentText(),
                    int(objs[3].text())
                ))
        return _plot_params