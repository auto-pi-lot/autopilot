import ast
import copy
from collections import OrderedDict as odict

import autopilot
from autopilot.gui.widgets.protocol import Sound_Widget, Graduation_Widget
from PySide6 import QtWidgets, QtGui

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