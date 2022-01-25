import ast
import copy
import os
from collections import OrderedDict as odict

import autopilot
from autopilot import prefs


class Protocol_Wizard(QtWidgets.QDialog):
    """
    A dialog window to create a new protocol.

    Warning:
        This is a heavily overloaded class, and will be split into separate objects
        to handle parameters separately. For now this is what we got though and it works.

    Protocols are collections of multiple tasks (steps)
    with some graduation criterion for moving between them.

    This widget is composed of three windows:

    * **left**: possible task types from :func:`autopilot.get_task()`
    * **center**: current steps in task
    * **right**: :class:`.Parameters` for currently selected step.

    The parameters that are used are of the form used by :py:attr:`.Task.PARAMS`
    (see :py:attr:`.Nafc.PARAMS` for an example).

    TODO:
        Make specific parameter class so this definition is less squishy

    its general structure is::

        {'parameter_key': {'tag':'Human Readable Name',
                           'type':'param_type'}}

    while some parameter types have extra items, eg.::

        {'list_param': {'tag':'Select from a List of Parameters',
                        'type': 'list',
                        'values': {'First Option':0, 'Second Option':1}}

    where k:v pairs are still used with lists to allow parameter values (0, 1) be human readable.

    The available types include:

    * **int** - integer
    * **float** - floating point number
    * **bool** - boolean boolbox
    * **list** - a list of `values` to choose from
    * **sounds** - a :class:`.Sound_Widget` that allows sounds to be defined.
    * **graduation** - a :class:`.Graduation_Widget` that allows graduation criteria to be defined

    Attributes:
        task_list (:class:`QtWidgets.QListWidget`): The leftmost window, lists available tasks
        step_list (:class:`QtWidgets.QListWidget`): The center window, lists tasks currently in protocol
        param_layout (:class:`QtWidgets.QFormLayout`): The right window, allows changing available
            parameters for currently selected step.
        steps (list): A list of dictionaries defining the protocol.

    """
    def __init__(self):
        QtWidgets.QDialog.__init__(self)

        # Left Task List/Add Step Box
        addstep_label = QtWidgets.QLabel("Add Step")
        addstep_label.setFixedHeight(40)
        self.task_list = QtWidgets.QListWidget()
        self.task_list.insertItems(0, autopilot.get_names('task'))
        self.add_button = QtWidgets.QPushButton("+")
        self.add_button.setFixedHeight(40)
        self.add_button.clicked.connect(self.add_step)

        addstep_layout = QtWidgets.QVBoxLayout()
        addstep_layout.addWidget(addstep_label)
        addstep_layout.addWidget(self.task_list)
        addstep_layout.addWidget(self.add_button)

        # Center Step List Box
        steplist_label = QtWidgets.QLabel("Step List")
        steplist_label.setFixedHeight(40)
        self.step_list = QtWidgets.QListWidget()
        self.step_list.setDragDropMode(QtWidgets.QAbstractItemView.InternalMove)
        self.step_list.selectionMode = QtWidgets.QAbstractItemView.SingleSelection
        self.step_list.itemSelectionChanged.connect(self.populate_params)
        self.list_model = self.step_list.model()
        self.list_model.rowsMoved.connect(self.reorder_steps)
        self.remove_step_button = QtWidgets.QPushButton('-')
        self.remove_step_button.setFixedHeight(40)
        self.remove_step_button.clicked.connect(self.remove_step)

        steplist_layout = QtWidgets.QVBoxLayout()
        steplist_layout.addWidget(steplist_label)
        steplist_layout.addWidget(self.step_list)
        steplist_layout.addWidget(self.remove_step_button)

        # Right Parameter Definition Window
        param_label = QtWidgets.QLabel("Step Parameters")
        param_label.setFixedHeight(40)
        self.param_layout = QtWidgets.QFormLayout()
        param_frame = QtWidgets.QFrame()
        param_frame.setLayout(self.param_layout)

        param_box_layout = QtWidgets.QVBoxLayout()
        param_box_layout.addWidget(param_label)
        param_box_layout.addWidget(param_frame)

        # Main Layout
        frame_layout = QtWidgets.QHBoxLayout()
        frame_layout.addLayout(addstep_layout, stretch=1)
        frame_layout.addLayout(steplist_layout, stretch=1)
        frame_layout.addLayout(param_box_layout, stretch=3)

        buttonBox = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        buttonBox.accepted.connect(self.accept)
        buttonBox.rejected.connect(self.reject)

        main_layout = QtWidgets.QVBoxLayout()
        main_layout.addLayout(frame_layout)
        main_layout.addWidget(buttonBox)

        self.setLayout(main_layout)
        self.setWindowTitle("Make New Protocol")

        # List to store dicts of steps and params
        self.steps = []

    def add_step(self):
        """
        Loads `PARAMS` from task object, adds base parameters to :py:attr:`.steps` list
        """
        task_type = self.task_list.currentItem().text()
        new_item = QtWidgets.QListWidgetItem()
        new_item.setText(task_type)
        task_params = copy.deepcopy(autopilot.get_task(task_type).PARAMS)

        # Add params that are non-task specific
        # Name of task type
        task_params['task_type'] = {'type':'label','value':task_type}
        # Prepend name of step shittily
        task_params_temp = odict()
        task_params_temp['step_name'] = {'type':'str', 'tag':'Step Name', 'value':task_type}
        task_params_temp.update(task_params)
        task_params.clear()
        task_params.update(task_params_temp)
        # add graduation field
        task_params['graduation'] = {'type':'graduation', 'tag':'Graduation Criterion', 'value':{}}

        self.steps.append(task_params)
        self.step_list.addItem(new_item)
        self.step_list.setCurrentItem(new_item)

    def rename_step(self):
        """
        When the step name widget's text is changed,
        fire this function to update :py:attr:`.step_list` which updates
         :py:attr:`.steps`
        """
        sender = self.sender()
        sender_text = sender.text()
        current_step = self.step_list.item(self.step_list.currentRow())
        current_step.setText(sender_text)

    def remove_step(self):
        """
        Remove step from :py:attr:`.step_list` and :py:attr:`.steps`
        """
        step_index = self.step_list.currentRow()
        del self.steps[step_index]
        self.step_list.takeItem(step_index)

    def populate_params(self):
        """
        Calls :py:meth:`.clear_params` and then creates widgets to edit parameter values.
        Returns:

        """
        self.clear_params()

        # Get current item index
        step_index = self.step_list.currentRow()
        step_dict = self.steps[step_index]

        # Iterate through params to make input widgets
        for k, v in step_dict.items():
            # Make Input Widget depending on type
            # Each Input type needs a different widget type,
            # and each widget type has different methods to get/change values, so we have to do this ugly
            if v['type'] == 'int' or v['type'] == 'str' or v['type'] == 'float':
                rowtag = QtWidgets.QLabel(v['tag'])
                input_widget = QtWidgets.QLineEdit()
                input_widget.setObjectName(k)
                if v['type'] == 'int':
                    input_widget.setValidator(QtGui.QIntValidator())
                elif v['type'] == 'float':
                    input_widget.setValidator(QtGui.QDoubleValidator())
                input_widget.editingFinished.connect(self.set_param)
                if 'value' in v.keys():
                    input_widget.setText(v['value'])
                elif v['type'] == 'str':
                    self.steps[step_index][k]['value'] = ''
                self.param_layout.addRow(rowtag,input_widget)

            elif v['type'] == 'bool':
                rowtag = QtWidgets.QLabel(v['tag'])
                input_widget = QtWidgets.QCheckBox()
                input_widget.setObjectName(k)
                input_widget.stateChanged.connect(self.set_param)
                if 'value' in v.keys():
                    input_widget.setChecked(v['value'])
                else:
                    self.steps[step_index][k]['value'] = False
                self.param_layout.addRow(rowtag, input_widget)

            elif v['type'] == 'list':
                rowtag = QtWidgets.QLabel(v['tag'])
                input_widget = QtWidgets.QListWidget()
                input_widget.setObjectName(k)
                sorted_values = sorted(v['values'], key=v['values'].get)
                input_widget.insertItems(0, sorted_values)
                input_widget.itemSelectionChanged.connect(self.set_param)
                if 'value' in v.keys():
                    select_item = input_widget.item(v['value'])
                    input_widget.setCurrentItem(select_item)
                else:
                    self.steps[step_index][k]['value'] = sorted_values[0]
                self.param_layout.addRow(rowtag, input_widget)
                self.steps[step_index][k]['value'] = False
            elif v['type'] == 'sounds':
                self.sound_widget = Sound_Widget()
                self.sound_widget.setObjectName(k)
                self.sound_widget.pass_set_param_function(self.set_sounds)
                self.param_layout.addRow(self.sound_widget)
                self.steps[step_index][k]['sounds'] = {}
                if 'value' in v.keys():
                    self.sound_widget.populate_lists(v['value'])
            elif v['type'] == 'graduation':
                self.grad_widget = Graduation_Widget()
                self.grad_widget.setObjectName(k)
                self.grad_widget.set_graduation = self.set_graduation
                self.param_layout.addRow(self.grad_widget)
                if 'type' in v['value'].keys():
                    combo_index = self.grad_widget.type_selection.findText(v['value']['type'])
                    self.grad_widget.type_selection.setCurrentIndex(combo_index)
                    self.grad_widget.populate_params(v['value']['value'])

            elif v['type'] == 'label':
                # This is a .json label not for display
                pass

            # Step name needs to be hooked up to the step list text
            if k == 'step_name':
                input_widget.editingFinished.connect(self.rename_step)

        # TODO: Implement dependencies between parameters

    def clear_params(self):
        """
        Clears widgets from parameter window
        """
        while self.param_layout.count():
            child = self.param_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

    def reorder_steps(self, *args):
        """
        When steps are dragged into a different order, update the step dictionary

        Args:
            *args: Input from our :py:attr:`.step_list` 's :class:`.QtWidgets.QListModel` 's reorder signal.
        """
        # arg positions 1 and 4 are starting and ending positions in the list, respectively
        # We reorder our step list so the params line up.
        before = args[1]
        after = args[4]
        self.steps.insert(after, self.steps.pop(before))

    def set_param(self):
        """
        Callback function connected to the signal each widget uses to signal it has changed.

        Identifies the param that was changed, gets the current value, and updates `self.steps`
        """
        sender = self.sender()
        param_name = sender.objectName()
        current_step = self.step_list.currentRow()
        sender_type = self.steps[current_step][param_name]['type']

        if sender_type == 'bool':
            self.steps[current_step][param_name]['value'] = sender.isChecked()
        elif sender_type == 'list':
            list_text = sender.currentItem().text()
            #list_value = self.steps[current_step][param_name]['values'][list_text]
            self.steps[current_step][param_name]['value'] = list_text
        elif sender_type == 'sounds':
            self.steps[current_step][param_name]['value'] = self.sound_widget.sound_dict
        else:
            try:
                sender_text = ast.literal_eval(sender.text())
            except:
                sender_text = sender.text()
            self.steps[current_step][param_name]['value'] = sender_text

    def set_sounds(self):
        """
        Stores parameters that define sounds.

        Sound parameters work a bit differently, specifically we have to retrieve
        :py:attr:`.Sound_Widget.sound_dict`.
        """
        current_step = self.step_list.currentRow()
        #if 'sounds' in self.steps[current_step]['stim'].keys():
        #    self.steps[current_step][param_name]['sounds']['value'].update(self.sound_widget.sound_dict)
        #else:
        self.steps[current_step]['stim']['sounds'] = self.sound_widget.sound_dict

    def set_graduation(self):
        """
        Stores parameters that define graduation criteria in `self.steps`

        Graduation parameters work a bit differently, specifically we have to retrieve
        :py:attr:`.Graduation_Widget.param_dict`.
        """
        current_step = self.step_list.currentRow()
        grad_type = self.grad_widget.type
        grad_params = self.grad_widget.param_dict
        self.steps[current_step]['graduation']['value'] = {'type':grad_type,'value':grad_params}


    def check_depends(self):
        """
        Handle dependencies between parameters, eg. if "correction trials" are unchecked,
        the box that defines the correction trial percentage should be grayed out.

        TODO:
            Not implemented.
        """
        # TODO: Make dependent fields unavailable if dependencies unmet
        # I mean if it really matters
        pass


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

        for k in autopilot.get_task(self.type).PARAMS:
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