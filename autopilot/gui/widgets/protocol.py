import os

import autopilot
from autopilot import prefs
from autopilot.gui.widgets.list import Drag_List
from PySide6 import QtWidgets

class Graduation_Widget(QtWidgets.QWidget):
    """
    A widget used in :class:`.Protocol_Wizard` to define graduation parameters.

    See :py:mod:`.tasks.graduation` .

    A protocol is composed of multiple tasks (steps), and graduation criteria
    define when a subject should progress through those steps.

    eg. a subject should graduate one stage after 300 trials, or after it reaches
    75% accuracy over the last 500 trials.

    Attributes:
        type_selection (:class:`QtWidgets.QComboBox`): A box to select from the available
            graduation types listed in :func:`autopilot.get_task()` . Has its `currentIndexChanged`
            signal connected to :py:meth:`.Graduation_Widget.populate_params`
        param_dict (dict): Stores the type of graduation and the relevant params,
            fetched by :class:`.Protocol_Wizard` when defining a protocol.
        set_graduation (:py:meth:`.Protocol_Wizard.set_graduation`): Passed to us after we're inited.
    """

    def __init__(self):
        super(Graduation_Widget, self).__init__()

        # Grad type dropdown
        type_label = QtWidgets.QLabel("Graduation Criterion:")
        self.type_selection = QtWidgets.QComboBox()
        self.type_selection.insertItems(0, autopilot.get_names('graduation'))
        self.type_selection.currentIndexChanged.connect(self.populate_params)

        # Param form
        self.param_layout = QtWidgets.QFormLayout()

        layout = QtWidgets.QVBoxLayout()
        layout.addWidget(type_label)
        layout.addWidget(self.type_selection)
        layout.addLayout(self.param_layout)

        self.setLayout(layout)

        self.param_dict = {}

        self.type = ""

        self.set_graduation = None

        self.populate_params()

    def populate_params(self, params=None):
        """
        Repopulate the widget with fields to edit graduation parameters, fill fields
        if we are passed `params`.

        Each :class:`QtWidgets.QLineEdit` 's :py:meth:`.QLineEdit.editingFinished` signal is connected
        to :py:meth:`.Graduation_Widget.store_param` .

        TODO:
            For now we assume all parameters are defined with a text edit box, so it's not
            clear how we'd do boolean parameters for example. This will be fixed with refactoring
            the parameter scheme.

        Args:
            params (dict): In the case that :class:`.Protocol_Wizard` switches us back to
                a step where we have already defined graduation parameters, it will pass them
                so we can repopulate the relevant widgets with them.
        """
        self.clear_params()
        self.type = self.type_selection.currentText()
        self.param_dict['type'] = self.type

        for k in autopilot.get('graduation', self.type).PARAMS:
            edit_box = QtWidgets.QLineEdit()
            edit_box.setObjectName(k)
            edit_box.editingFinished.connect(self.store_param)
            if isinstance(params, dict):
                if k in params.keys():
                    edit_box.setText(params[k])
            self.param_layout.addRow(QtWidgets.QLabel(k), edit_box)

    def clear_params(self):
        """
        Clear any parameter widgets we have.
        """
        while self.param_layout.count():
            child = self.param_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

    def store_param(self):
        """
        When a parameter is edited, save it in our param_dict, and also call our
        `set_graduation` method, which should be :py:meth:`.Protocol_Wizard.set_graduation`
        passed to us after instantiation.

        If we were not passed `set_graduation`, just saves in `param_dict`.
        """
        sender = self.sender()
        name = sender.objectName()
        self.param_dict[name] = sender.text()

        if not callable(self.set_graduation):
            Warning("Stored Graduation parameters in our param_dict, but wasn't passed a set_graduation method!")
            return

        self.set_graduation()


class Sound_Widget(QtWidgets.QWidget):
    """
    A widget that allows sounds to be parameterized.

    Used in :class:`.Protocol_Wizard` .

    Has two :class:`.Drag_List` s for left and right sounds (for a 2afc task), given
    Buttons beneath them allow adding and removing sounds.

    Adding a sound will open a :class:`.Add_SoundDialog`

    TODO:
        Sounds will eventually be more elegantly managed by a ... sound manager..
        For now sound managers are rudimentary and only support random presentation
        with correction trials and bias correction.

    Attributes:
        sound_dict (dict): Dictionary with the structure::

                {'L': [{'param_1':'param_1', ... }], 'R': [...]}

            where multiple sounds can be present in either 'L' or 'R' list.



    """
    def __init__(self):
        # type: () -> None
        QtWidgets.QWidget.__init__(self)

        self.sounddir = prefs.get('SOUNDDIR')

        self.set_sounds = None

        # Left sounds
        left_label = QtWidgets.QLabel("Left Sounds")
        left_label.setFixedHeight(30)
        self.left_list = Drag_List()
        self.left_list.fileDropped.connect(self.files_dropped)
        self.left_list.setObjectName("L")
        self.add_left_button = QtWidgets.QPushButton("+")
        self.add_left_button.setFixedHeight(30)
        self.add_left_button.clicked.connect(lambda: self.add_sound('L'))
        self.remove_left_button = QtWidgets.QPushButton("-")
        self.remove_left_button.setFixedHeight(30)
        self.remove_left_button.clicked.connect(lambda: self.remove_sound('L'))

        left_layout = QtWidgets.QVBoxLayout()
        left_button_layout = QtWidgets.QHBoxLayout()
        left_button_layout.addWidget(self.add_left_button)
        left_button_layout.addWidget(self.remove_left_button)
        left_layout.addWidget(left_label)
        left_layout.addWidget(self.left_list)
        left_layout.addLayout(left_button_layout)

        # Right sounds
        right_label = QtWidgets.QLabel("Right Sounds")
        right_label.setFixedHeight(30)
        self.right_list = Drag_List()
        self.right_list.fileDropped.connect(self.files_dropped)
        self.right_list.setObjectName("R")
        self.add_right_button = QtWidgets.QPushButton("+")
        self.add_right_button.setFixedHeight(30)
        self.add_right_button.clicked.connect(lambda: self.add_sound('R'))
        self.remove_right_button = QtWidgets.QPushButton("-")
        self.remove_right_button.setFixedHeight(30)
        self.remove_right_button.clicked.connect(lambda: self.remove_sound('R'))

        right_layout = QtWidgets.QVBoxLayout()
        right_button_layout = QtWidgets.QHBoxLayout()
        right_button_layout.addWidget(self.add_right_button)
        right_button_layout.addWidget(self.remove_right_button)
        right_layout.addWidget(right_label)
        right_layout.addWidget(self.right_list)
        right_layout.addLayout(right_button_layout)

        self.sound_dict = {'L': [], 'R': []}

        main_layout = QtWidgets.QHBoxLayout()
        main_layout.addLayout(left_layout)
        main_layout.addLayout(right_layout)
        self.setLayout(main_layout)

        # TODO:Add drag and drop for files

    def pass_set_param_function(self, set_param_fnxn):
        """
        Receives :py:meth:`.Protocol_Wizard.set_sounds`

        Args:
            set_param_fnxn (:py:meth:`.Protocol_Wizard.set_sounds`): Called when sounds are changed.
        """
        self.set_sounds = set_param_fnxn

    def add_sound(self, side):
        """
        When the "+" button on either side is pressed, open an :class:`.Add_Sound_Dialog`.

        Args:
            side (str): The buttons are connected with a lambda function, this will be either 'L' or 'R'.
                Used to add sounds to the `sound_dict`
        """
        new_sound = self.Add_Sound_Dialog()
        new_sound.exec_()

        if new_sound.result() == 1:
            self.sound_dict[side].append(new_sound.param_dict)
            if side == 'L':
                self.left_list.addItem(new_sound.param_dict['type'])
            elif side == 'R':
                self.right_list.addItem(new_sound.param_dict['type'])
            self.set_sounds()

    def remove_sound(self, side):
        """
        When the "-" button is pressed, remove the currently highlighted sound.

        Args:
            side (str): The buttons are connected with a lambda function, this will be either 'L' or 'R'.
                Selects that list so we can remove the currently selected row.
        """
        if side == 'L':
            current_sound = self.left_list.currentRow()
            del self.sound_dict['L'][current_sound]
            self.left_list.takeItem(current_sound)
        elif side == 'R':
            current_sound = self.right_list.currentRow()
            del self.sound_dict['R'][current_sound]
            self.right_list.takeItem(current_sound)
        self.set_sounds()

    def populate_lists(self, sound_dict):
        """
        Populates the sound lists after re-selecting a step.

        Args:
            sound_dict (dict): passed to us by :class:`.Protocol_Wizard` upon reselecting a step.
        """
        # Populate the sound lists after re-selecting a step
        self.sound_dict = sound_dict
        for k in self.sound_dict['L']:
            self.left_list.addItem(k['type'])
        for k in self.sound_dict['R']:
            self.right_list.addItem(k['type'])

    def files_dropped(self, files):
        """
        Warning:
            This was programmed hastily and is pretty idiosyncratic to my use.

            It does work for general files but has some extra logic built in to handle my stimuli.

            To be made more general in v0.3

        Note:
            Sounds must be in the folder specified in `prefs.get('SOUNDDIR')`.

        When files are dropped on the lists, strips `prefs.get('SOUNDDIR')` from them to make them
        relative paths, adds them to the `sound_dict`

        Args:
            files (list): List of absolute paths.
        """
        # TODO: Make this more general...
        msg = QtWidgets.QMessageBox()
        msg.setText("Are these Speech sounds in the format '/speaker/cv/cv_#.wav'?")
        msg.setStandardButtons(QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No)
        ret = msg.exec_()

        sender = self.sender()
        side = sender.objectName()

        if ret == QtWidgets.QMessageBox.No:
            for f in files:
                f = f.strip(self.sounddir)

                self.sound_dict[side].append({'type':'File', 'path':f})
                if side == 'L':
                    self.left_list.addItem(f)
                elif side == 'R':
                    self.right_list.addItem(f)


        elif ret == QtWidgets.QMessageBox.Yes:
            for f in files:
                f = f.strip(self.sounddir)
                f_split = f.split(os.sep)
                speaker = f_split[0]
                cv = f_split[-1].split('.')[0].split('_')[0]
                consonant = cv[0]
                vowel = cv[1:]
                token = f_split[-1].split('.')[0].split('_')[1]
                param_dict = {'type':'Speech','path':f,
                 'speaker':speaker,'consonant':consonant,
                 'vowel':vowel,'token':token}
                self.sound_dict[side].append(param_dict)
                if side == 'L':
                    self.left_list.addItem(f)
                elif side == 'R':
                    self.right_list.addItem(f)

        self.set_sounds()

    class Add_Sound_Dialog(QtWidgets.QDialog):
        """
        Presents a dialog to define a new sound.

        Makes a selection box to choose the sound type from
        ``autopilot.get_names('sound')``, and then populates edit boxes
        so we can fill in its `PARAMS` .

        Attributes:
            type_selection (:class:`QtWidgets.QComboBox`): Select from a list of available sounds
            param_dict (dict): Parameters that are retreived by the calling :class:`.Sound_Widget`.

        """
        def __init__(self):
            # type: () -> None
            QtWidgets.QDialog.__init__(self)

            # Sound type dropdown
            type_label = QtWidgets.QLabel("Sound Type:")
            self.type_selection = QtWidgets.QComboBox()
            self.type_selection.insertItems(0, autopilot.get_names('sound'))
            self.type_selection.currentIndexChanged.connect(self.populate_params)

            # Param form
            self.param_layout = QtWidgets.QFormLayout()

            # Button box
            buttonBox = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
            buttonBox.accepted.connect(self.accept)
            buttonBox.rejected.connect(self.reject)

            # Layout
            layout = QtWidgets.QVBoxLayout()
            layout.addWidget(type_label)
            layout.addWidget(self.type_selection)
            layout.addLayout(self.param_layout)
            layout.addWidget(buttonBox)

            self.setLayout(layout)


            # dict for storing params
            self.param_dict = {}

            # do initial population
            self.populate_params()

        def populate_params(self):
            """
            When a sound type is selected, make a :class:`.QtWidgets.QLineEdit` for each
            `PARAM` in its definition.
            """
            self.clear_params()

            self.type = self.type_selection.currentText()
            self.param_dict['type'] = self.type

            for k in autopilot.get('sound', self.type).PARAMS:
                edit_box = QtWidgets.QLineEdit()
                edit_box.setObjectName(k)
                edit_box.editingFinished.connect(self.store_param)
                self.param_layout.addRow(QtWidgets.QLabel(k), edit_box)

        def clear_params(self):
            """
            Clear all current widgets
            """
            while self.param_layout.count():
                child = self.param_layout.takeAt(0)
                if child.widget():
                    child.widget().deleteLater()

        def store_param(self):
            """
            When one of our edit boxes is edited, stash the parameter in `param_dict`
            """
            sender = self.sender()
            name = sender.objectName()
            self.param_dict[name] = sender.text()