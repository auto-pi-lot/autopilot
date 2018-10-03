import sys
import os
import json
import copy
import datetime
from collections import OrderedDict as odict
from PySide import QtGui, QtCore

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mouse import Mouse
import tasks
import sounds

class Control_Panel(QtGui.QWidget):
    # Hosts two nested tab widgets to select pilot and mouse,
    # set params, run mice, etc.

    def __init__(self, pilots=None, mice=None, msg_fn=None, prefs=None):
        super(Control_Panel, self).__init__()
        # We should be passed a pilot odict {'pilot':[mouse1, mouse2]}
        # If we're not, try to load prefs, and if we don't have prefs, from default loc.
        self.prefs = prefs

        # We share a dict of mouse objects with the main Terminal class to avoid access conflicts
        self.mice = mice

        # We get the Terminal's send_message function so we can communicate directly from here
        self.send_message = msg_fn

        if pilots:
            self.pilots = pilots
        else:
            try:
                # Try finding prefs in the encapsulating namespaces
                with open(prefs['PILOT_DB']) as pilot_file:
                    self.pilots = json.load(pilot_file, object_pairs_hook=odict)
            except NameError:
                try:
                    with open('/usr/rpilot/pilot_db.json') as pilot_file:
                        self.pilots = json.load(pilot_file, object_pairs_hook=odict)
                except IOError:
                    Exception('Couldnt find pilot directory!')

        # Make dict to store handles to mice lists
        self.mouse_lists = {}

        # Set layout for whole widget
        self.layout = QtGui.QGridLayout()
        self.layout.setContentsMargins(0,0,0,0)
        self.layout.setSpacing(0)
        self.setLayout(self.layout)

        self.init_ui()

        self.setSizePolicy(QtGui.QSizePolicy.Maximum,QtGui.QSizePolicy.Maximum)

    def init_ui(self):
        self.layout.setColumnStretch(0, 1)
        self.layout.setColumnStretch(1, 5)

        # Iterate through pilots and mice, making start/stop buttons for pilots and lists of mice
        for i, (pilot, mice) in enumerate(self.pilots.items()):
            # in pilot dict, format is {'pilot':{'mice':['mouse1',...],'ip':'',etc.}}
            mice = mice['mice']
            # Make a list of mice
            mouse_list = Mouse_List(mice, drop_fn = self.update_db)
            mouse_list.setSizePolicy(QtGui.QSizePolicy.Expanding, QtGui.QSizePolicy.Expanding)
            mouse_list.itemDoubleClicked.connect(self.edit_params)
            self.mouse_lists[pilot] = mouse_list

            # Make a panel for pilot control
            pilot_panel = Pilot_Panel(pilot, mouse_list, self.toggle_start, self.create_mouse)
            pilot_panel.setFixedWidth(100)

            self.layout.addWidget(pilot_panel, i, 1, 1, 1)
            self.layout.addWidget(mouse_list, i, 2, 1, 1)

    def reset_ui(self):
        # TODO This don't work.
        self.layout = QtGui.QGridLayout()
        self.layout.setContentsMargins(0,0,0,0)
        self.layout.setSpacing(0)
        self.setLayout(self.layout)
        self.init_ui()

    def toggle_start(self, starting, pilot, mouse=None):
        # stopping is the enemy of starting so we put them in the same function to learn about each other
        if starting is True:
            # Ope'nr up if she aint
            if mouse not in self.mice.keys():
                self.mice[mouse] = Mouse(mouse)

            self.mice[mouse].prepare_run()

            # Get the mouse's task info to send to the pilot
            try:
                protocol = self.mice[mouse].current
                step = self.mice[mouse].step
                task = protocol[step]
            except:
                # TODO: Log this error - mouse started but has no task
                # TODO: Popup to the same effect.
                return

            # Prep task to send to pi, the pilot needs to know the mouse
            task['mouse'] = self.mice[mouse].name
            task['pilot'] = pilot
            task['step'] = step
            task['current_trial'] = self.mice[mouse].current_trial
            task['session'] = self.mice[mouse].session

            # Get Weights
            start_weight, ok = QtGui.QInputDialog.getDouble(self, "Set Starting Weight",
                                                        "Starting Weight:" )
            if ok:
                self.mice[mouse].update_weights(start=float(start_weight))
            else:
                # pressed cancel, don't start
                self.mice[mouse].stop_run()
                return

            self.send_message('START', bytes(pilot), task)

        else:
            # Send message to pilot to stop running,
            # it should initiate a coherence checking routine to make sure
            # its data matches what the Terminal got,
            # so the terminal will handle closing the mouse object
            self.send_message('STOP', bytes(pilot), 'STOP')
            # TODO: Start coherence checking ritual
            # TODO: Close mouse object
            # TODO: Pop weight entry window
            # TODO: Auto-select the next mouse in the list.

            # get weight
            # Get Weights
            stop_weight, ok = QtGui.QInputDialog.getDouble(self, "Set Stopping Weight",
                                                        "Stopping Weight:" )

            self.mice[mouse].stop_run()

            if ok:
                self.mice[mouse].update_weights(stop=float(stop_weight))



    def create_mouse(self, pilot):
        new_mouse_wizard = New_Mouse_Wizard(self.prefs['PROTOCOLDIR'])
        new_mouse_wizard.exec_()

        # If the wizard completed successfully, get its values
        if new_mouse_wizard.result() == 1:
            biography_vals = new_mouse_wizard.bio_tab.values

            # Make a new mouse object, make it temporary because we want to close it
            mouse_obj = Mouse(biography_vals['id'], new=True,
                              biography=biography_vals)
            self.mice[biography_vals['id']] = mouse_obj

            # If a protocol was selected in the mouse wizard, assign it.
            try:
                protocol_vals = new_mouse_wizard.task_tab.values
                if 'protocol' in protocol_vals.keys() and 'step' in protocol_vals.keys():
                    protocol_file = os.path.join(self.prefs['PROTOCOLDIR'], protocol_vals['protocol'] + '.json')
                    mouse_obj.assign_protocol(protocol_file, int(protocol_vals['step']))
            except:
                # the wizard couldn't find the protocol dir, so no task tab was made
                # or no task was assigned
                pass

            # Add mouse to pilots dict, update it and our tabs
            self.pilots[pilot]['mice'].append(biography_vals['id'])
            self.mouse_lists[pilot].addItem(biography_vals['id'])
            self.update_db()

    def edit_params(self, item):
        # edit a mouse's task parameters, called when mouse double-clicked
        mouse = item.text()
        if mouse not in self.mice.keys():
            self.mice[mouse] = Mouse(mouse)

        if '/current' not in self.mice[mouse].h5f:
            Warning("Mouse {} has no protocol!".format(mouse))
            return

        protocol = self.mice[mouse].current
        step = self.mice[mouse].step

        protocol_edit = Protocol_Parameters_Dialogue(protocol, step)
        protocol_edit.exec_()

        if protocol_edit.result() == 1:
            param_changes = protocol_edit.step_changes
            # iterate through steps, checking for changes
            for i, step_changes in enumerate(param_changes):
                # if there are any changes to this step, stash them
                if step_changes:
                    for k, v in step_changes.items():
                        self.mice[mouse].update_history('param', k, v, step=i)

        # TODO: Check if mouse running, if mouse is running, communicate current step changes to pi


    def update_db(self, *args, **kwargs):
        for pilot, mlist in self.mouse_lists.items():
            mice = []
            for i in range(mlist.count()):
                mice.append(mlist.item(i).text())

            self.pilots[pilot]['mice'] = mice

        try:
            with open(self.prefs['PILOT_DB'], 'w') as pilot_file:
                json.dump(self.pilots, pilot_file)
        except NameError:
            try:
                with open('/usr/rpilot/pilot_db.json', 'w') as pilot_file:
                    json.dump(self.pilots, pilot_file)
            except IOError:
                Exception('Couldnt update pilot db!')

####################################
# Control Panel Widgets
###################################

class Mouse_List(QtGui.QListWidget):
    def __init__(self, mice=None, drop_fn=None):
        super(Mouse_List, self).__init__()

        # if we are passed a list of mice, populate
        if mice:
            self.mice = mice
            self.populate_list()

        # make draggable
        self.setDragDropMode(QtGui.QAbstractItemView.InternalMove)
        self.setDragDropOverwriteMode(False)
        self.setAcceptDrops(True)

        # drop_fn gets called on a dropEvent (after calling the superclass method)
        self.drop_fn = drop_fn

    def populate_list(self):
        for m in self.mice:
            self.addItem(m)

    def dropEvent(self, event):
        # call the parent dropEvent to make sure all the list ops happen
        super(Mouse_List, self).dropEvent(event)
        # then we call the drop_fn passed to us
        self.drop_fn()


class Pilot_Panel(QtGui.QWidget):
    def __init__(self, pilot=None, mouse_list=None, toggle_fn=None, create_fn=None):
        # A little panel with the name of a pilot on top,
        # a big start/stop button, and two smaller add/remove mouse buttons at the bottom
        super(Pilot_Panel, self).__init__()

        self.layout = QtGui.QGridLayout()
        self.layout.setContentsMargins(0,0,0,0)
        self.layout.setSpacing(0)
        self.setLayout(self.layout)

        self.pilot = pilot
        self.mouse_list = mouse_list
        self.toggle_fn = toggle_fn
        self.create_fn = create_fn

        self.init_ui()

    def init_ui(self):
        label = QtGui.QLabel(self.pilot)
        start_button = Pilot_Button(self.pilot, self.mouse_list, self.toggle_fn)
        add_button = QtGui.QPushButton("+")
        add_button.clicked.connect(self.create_mouse)
        remove_button = QtGui.QPushButton("-")
        remove_button.clicked.connect(self.remove_mouse)

        self.layout.addWidget(label, 0, 0, 1, 2)
        self.layout.addWidget(start_button, 1, 0, 1, 2)
        self.layout.addWidget(add_button, 2,0,1,1)
        self.layout.addWidget(remove_button, 2,1,1,1)

        self.layout.setRowStretch(0, 0)
        self.layout.setRowStretch(1, 5)
        self.layout.setRowStretch(2, 0)

    def remove_mouse(self):
        self.mouse_list.takeItem(self.mouse_list.currentRow())
        # the drop fn updates the db
        self.mouse_list.drop_fn()

    def create_mouse(self):
        # essentially just a decorator, just calling create_mouse w/ our name
        self.create_fn(self.pilot)


class Pilot_Button(QtGui.QPushButton):
    def __init__(self, pilot=None, mouse_list=None, toggle_fn=None):
        # Just easier to add the button behavior as a class.
        super(Pilot_Button, self).__init__()

        ## GUI Settings
        self.setCheckable(True)
        self.setChecked(False)
        self.setStyleSheet("QPushButton {color:white; background-color: green}"
                           "QPushButton:checked {color:white; background-color: red}")
        # since we're stopped when created, set our text as a start button...
        self.setText("START")

        # Normally buttons only expand horizontally, but these big ole ones....
        self.setSizePolicy(QtGui.QSizePolicy.Expanding, QtGui.QSizePolicy.Maximum)

        # What's yr name anyway?
        self.pilot = pilot

        # What mice do we know about?
        self.mouse_list = mouse_list

        # Passed a function to toggle start from the control panel
        self.toggle_fn = toggle_fn
        # toggle_start has a little sugar on it before sending to control panel
        self.toggled.connect(self.toggle_start)


    def toggle_start(self, toggled):
        # If we're stopped, start, and vice versa...
        current_mouse = self.mouse_list.currentItem().text()
        if toggled is True: # ie

            self.setText("STOP")
            self.toggle_fn(True, self.pilot, current_mouse)

        else:
            self.setText("START")
            self.toggle_fn(False, self.pilot, current_mouse)



###################################3
# Parameter setting widgets
######################################

class Parameters(QtGui.QWidget):
    # Superclass to embed wherever needed
    # Subclasses will implement use as standalong dialog and as step selector
    # Reads and edits tasks parameters from a mouse's protocol
    def __init__(self, params=None, stash_changes=False):
        super(Parameters, self).__init__()

        # We're just a simple label and a populateable form layout
        self.layout = QtGui.QVBoxLayout()
        self.setLayout(self.layout)

        label = QtGui.QLabel("Parameters")
        label.setFixedHeight(40)

        self.param_layout = QtGui.QFormLayout()

        self.layout.addWidget(label)
        self.layout.addLayout(self.param_layout)

        # sometimes we only are interested in the changes - like editing params
        # when that's the case, we keep a log of it
        self.stash_changes = stash_changes
        if self.stash_changes:
            self.param_changes = {}


        # If we were initialized with params, populate them now
        self.params = None
        if params:
            self.populate_params(params)

    def populate_params(self, params):
        # We want to hang on to the protocol and step
        # because they are direct references to the mouse file,
        # but we don't need to have them passed every time

        self.clear_layout(self.param_layout)

        if isinstance(params, basestring):
            # we are filling an empty parameter set
            self.params = {}
            task_type = params
        else:
            # we are populating an existing parameter set (ie. the fields already have values)
            self.params = params
            task_type = params['task_type']

        self.param_layout.addRow("Task Type:", QtGui.QLabel(task_type))

        # we need to load the task class to get the types of our parameters,
        self.task_params = copy.deepcopy(tasks.TASK_LIST[task_type].PARAMS)

        # Make parameter widgets depending on type and populate with current values
        for k, v in self.task_params.items():
            if v['type'] == 'int' or v['type'] == 'str':
                rowtag = QtGui.QLabel(v['tag'])
                input_widget = QtGui.QLineEdit()
                input_widget.setObjectName(k)
                if v['type'] == 'int':
                    input_widget.setValidator(QtGui.QIntValidator())
                input_widget.textEdited.connect(self.set_param)
                if k in self.params.keys():
                    input_widget.setText(self.params[k])
                self.param_layout.addRow(rowtag,input_widget)
            elif v['type'] == 'check':
                rowtag = QtGui.QLabel(v['tag'])
                input_widget = QtGui.QCheckBox()
                input_widget.setObjectName(k)
                input_widget.stateChanged.connect(self.set_param)
                if k in self.params.keys():
                    input_widget.setChecked(self.params[k])
                self.param_layout.addRow(rowtag, input_widget)
            elif v['type'] == 'list':
                rowtag = QtGui.QLabel(v['tag'])
                input_widget = QtGui.QListWidget()
                input_widget.setObjectName(k)
                input_widget.insertItems(0, sorted(v['values'], key=v['values'].get))
                input_widget.itemSelectionChanged.connect(self.set_param)
                if k in self.params.keys():
                    select_item = input_widget.item(self.params[k])
                    input_widget.setCurrentItem(select_item)
                self.param_layout.addRow(rowtag, input_widget)
            elif v['type'] == 'sounds':
                self.sound_widget = Sound_Widget()
                self.sound_widget.setObjectName(k)
                self.sound_widget.pass_set_param_function(self.set_sounds)
                self.param_layout.addRow(self.sound_widget)
                if k in self.params.keys():
                    self.sound_widget.populate_lists(self.params[k])
            elif v['type'] == 'label':
                # This is a .json label not for display
                pass

    def clear_layout(self, layout=None):
        if not layout:
            layout = self.param_layout
        while layout.count():
            child = layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

    def set_param(self):
        # A param was changed in the window, update our values here and in the mouse object
        sender = self.sender()
        param_name = sender.objectName()
        sender_type = self.task_params[param_name]['type']

        if sender_type == 'int' or sender_type == 'str':
            new_val = sender.text()
        elif sender_type == 'check':
            new_val = sender.isChecked()
        elif sender_type == 'list':
            list_text = sender.currentItem().text()
            new_val = self.task_params[param_name]['values'][list_text]
        elif sender_type == 'sounds':
            new_val = self.sound_widget.sound_dict

        self.params[param_name] = new_val
        if self.stash_changes:
            self.param_changes[param_name] = new_val

    def set_sounds(self):
        # Have to handle sounds slightly differently
        # because the sound widget updates its own parameters
        self.protocol[self.step]['sounds'] = self.sound_widget.sound_dict


class Protocol_Parameters(QtGui.QWidget):
    # Multiple steps in a protocol, enable selection of multiple param windows

    def __init__(self, protocol, step, protocol_name=None):
        super(Protocol_Parameters, self).__init__()

        self.protocol = protocol
        self.step = step

        # We're just a Parameters window with a combobox that lets us change step
        self.layout = QtGui.QVBoxLayout()
        self.setLayout(self.layout)

        if protocol_name:
            label = QtGui.QLabel(protocol_name)
        else:
            label = QtGui.QLabel('Protocol Parameters')

        label.setFixedHeight(20)

        # Make a combobox, we'll populate it in a second.
        self.step_selection = QtGui.QComboBox()
        self.step_selection.currentIndexChanged.connect(self.step_changed)

        # And the rest of our body is the params window
        self.params_widget = Parameters(stash_changes=True)
        self.step_changes = []

        # Add everything to the layout
        self.layout.addWidget(label)
        self.layout.addWidget(self.step_selection)
        self.layout.addWidget(self.params_widget)

        # and populate
        self.populate_protocol(self.protocol, self.step)


    def populate_protocol(self, protocol, step=0):
        # clean up first
        self.clear()

        # store in case things have changed since init
        self.protocol = protocol
        self.step = step

        if isinstance(self.protocol, basestring):
            # If we were passed a string, we're being passed a path to a protocol
            with open(self.protocol, 'r') as protocol_file:
                self.protocol = json.load(protocol_file)

        # Get step list and a dict to convert names back to ints
        self.step_list = []
        self.step_ind  = {}
        for i, s in enumerate(self.protocol):
            self.step_list.append(s['step_name'])
            self.step_ind[s['step_name']] = i
        # fill step_changes with empty dicts to be able to assign later
        self.step_changes = [{} for i in range(len(self.protocol))]


        # Add steps to combobox
        # disconnect indexChanged trigger first so we don't fire a billion times
        self.step_selection.currentIndexChanged.disconnect(self.step_changed)
        self.step_selection.insertItems(0, self.step_list)
        self.step_selection.currentIndexChanged.connect(self.step_changed)

        # setting the current index should trigger the params window to refresh
        self.step_selection.setCurrentIndex(self.step)
        self.params_widget.populate_params(self.protocol[self.step])


    def clear(self):
        while self.step_selection.count():
            self.step_selection.removeItem(0)

        self.params_widget.clear_layout()

    def step_changed(self):
        # save any changes to last step
        if self.params_widget.params:
            self.protocol[self.step] = self.params_widget.params
        if self.params_widget.stash_changes:
            self.step_changes[self.step].update(self.params_widget.param_changes)

        # the step was changed! Change our parameters here and update the mouse object
        self.step = self.step_selection.currentIndex()

        self.params_widget.populate_params(self.protocol[self.step])


class Protocol_Parameters_Dialogue(QtGui.QDialog):
    def __init__(self, protocol, step):
        super(Protocol_Parameters_Dialogue, self).__init__()

        # Dialogue wrapper for Protocol_Parameters

        self.protocol = protocol
        self.step = step

        # Since we share self.protocol, updates in the widget should propagate to us
        self.protocol_widget = Protocol_Parameters(self.protocol, self.step)

        # We stash changes in the protocol widget and recover them on close
        self.step_changes = None

        # ok/cancel buttons
        buttonBox = QtGui.QDialogButtonBox(QtGui.QDialogButtonBox.Ok | QtGui.QDialogButtonBox.Cancel)
        buttonBox.accepted.connect(self.accept)
        buttonBox.rejected.connect(self.reject)

        self.layout = QtGui.QVBoxLayout()
        self.layout.addWidget(self.protocol_widget)
        self.layout.addWidget(buttonBox)
        self.setLayout(self.layout)

        self.setWindowTitle("Edit Protocol Parameters")

    def accept(self):
        # Get the changes from the currently open params window
        self.step_changes = self.protocol_widget.step_changes
        # And any since the last time the qcombobox was changed
        self.step_changes[self.protocol_widget.step].update(self.protocol_widget.params_widget.param_changes)

        # call the rest of the accept method
        super(Protocol_Parameters_Dialogue, self).accept()

class Popup(QtGui.QDialog):
    def __init__(self, message):
        super(Popup, self,).__init__()
        self.layout = QtGui.QVBoxLayout()
        self.text = QtGui.QLabel(message)
        self.layout.addWidget(self.text)
        self.setLayout(self.layout)





##################################
# Wizard Widgets
################################3#

# TODO: Change these classes to use the update params windows

class New_Mouse_Wizard(QtGui.QDialog):
    def __init__(self, protocol_dir=None):
        QtGui.QDialog.__init__(self)

        if not protocol_dir:
            try:
                self.protocol_dir = prefs['PROTOCOLDIR']
            except NameError:
                Warning('No protocol dir found, cant assign protocols here')
        else:
            self.protocol_dir = protocol_dir

        tabWidget = QtGui.QTabWidget()

        self.bio_tab = self.Biography_Tab()
        tabWidget.addTab(self.bio_tab, "Biography")

        if self.protocol_dir:
            self.task_tab = self.Task_Tab(self.protocol_dir)
            tabWidget.addTab(self.task_tab, "Protocol")

        buttonBox = QtGui.QDialogButtonBox(QtGui.QDialogButtonBox.Ok | QtGui.QDialogButtonBox.Cancel)
        buttonBox.accepted.connect(self.accept)
        buttonBox.rejected.connect(self.reject)

        mainLayout = QtGui.QVBoxLayout()
        mainLayout.addWidget(tabWidget)
        mainLayout.addWidget(buttonBox)
        self.setLayout(mainLayout)

        self.setWindowTitle("Setup New Mouse")

    class Biography_Tab(QtGui.QWidget):
        def __init__(self):
            QtGui.QWidget.__init__(self)

            # Input Labels
            ID_label = QtGui.QLabel("ID:")
            start_label = QtGui.QLabel("Start Date:")
            blmass_label = QtGui.QLabel("Baseline Mass:")
            minmasspct_label = QtGui.QLabel("% of Baseline Mass:")
            minmass_label = QtGui.QLabel("Minimum Mass:")
            genotype_label = QtGui.QLabel("Genotype:")
            expt_label = QtGui.QLabel("Experiment Tag:")

            # Input widgets
            self.id = QtGui.QLineEdit()
            self.start_date = QtGui.QLineEdit(datetime.date.today().isoformat())
            self.blmass = QtGui.QLineEdit()
            self.blmass.setValidator(QtGui.QDoubleValidator(0.0, 30.0, 1, self.blmass))
            self.minmass_pct = QtGui.QSpinBox()
            self.minmass_pct.setRange(0,100)
            self.minmass_pct.setSingleStep(5)
            self.minmass_pct.setSuffix('%')
            self.minmass_pct.setValue(80)
            self.minmass = QtGui.QLineEdit()
            self.minmass.setValidator(QtGui.QDoubleValidator(0.0, 30.0, 1, self.minmass))
            self.genotype = QtGui.QLineEdit()
            self.expt     = QtGui.QLineEdit()

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
            mainLayout = QtGui.QVBoxLayout()
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
            self.values[key] = val
            # When values changed, update return dict

        def calc_minmass(self):
            # minimum mass automatically from % and baseline
            baseline = float(self.blmass.text())
            pct = float(self.minmass_pct.text()[:-1])/100
            self.minmass.setText(str(baseline*pct))

    class Task_Tab(QtGui.QWidget):
        def __init__(self, protocol_dir):
            QtGui.QWidget.__init__(self)

            self.protocol_dir = protocol_dir

            topLabel = QtGui.QLabel("Protocols:")

            # List available protocols
            protocol_list = os.listdir(self.protocol_dir)
            protocol_list = [os.path.splitext(p)[0] for p in protocol_list]

            self.protocol_listbox = QtGui.QListWidget()
            self.protocol_listbox.insertItems(0, protocol_list)
            self.protocol_listbox.currentItemChanged.connect(self.protocol_changed)

            # Make Step combobox
            self.step_selection = QtGui.QComboBox()
            self.step_selection.currentIndexChanged.connect(self.step_changed)

            layout = QtGui.QVBoxLayout()
            layout.addWidget(topLabel)
            layout.addWidget(self.protocol_listbox)
            layout.addWidget(self.step_selection)

            self.setLayout(layout)

            # Dict to return values
            self.values = {}

        def update_step_box(self):
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
            self.values['protocol'] = self.protocol_listbox.currentItem().text()
            self.update_step_box()

        def step_changed(self):
            current_step = self.step_selection.currentText()
            # Check that we have selected a step...
            if current_step is not u'':
                self.values['step'] = self.step_ind[current_step]

class Protocol_Wizard(QtGui.QDialog):
    def __init__(self, prefs):
        QtGui.QDialog.__init__(self)

        self.prefs = prefs

        # Left Task List/Add Step Box
        addstep_label = QtGui.QLabel("Add Step")
        addstep_label.setFixedHeight(40)
        self.task_list = QtGui.QListWidget()
        self.task_list.insertItems(0, tasks.TASK_LIST.keys())
        self.add_button = QtGui.QPushButton("+")
        self.add_button.setFixedHeight(40)
        self.add_button.clicked.connect(self.add_step)

        addstep_layout = QtGui.QVBoxLayout()
        addstep_layout.addWidget(addstep_label)
        addstep_layout.addWidget(self.task_list)
        addstep_layout.addWidget(self.add_button)

        # Center Step List Box
        steplist_label = QtGui.QLabel("Step List")
        steplist_label.setFixedHeight(40)
        self.step_list = QtGui.QListWidget()
        self.step_list.setDragDropMode(QtGui.QAbstractItemView.InternalMove)
        self.step_list.selectionMode = QtGui.QAbstractItemView.SingleSelection
        self.step_list.itemSelectionChanged.connect(self.populate_params)
        self.list_model = self.step_list.model()
        self.list_model.rowsMoved.connect(self.reorder_steps)
        self.remove_step_button = QtGui.QPushButton('-')
        self.remove_step_button.setFixedHeight(40)
        self.remove_step_button.clicked.connect(self.remove_step)

        steplist_layout = QtGui.QVBoxLayout()
        steplist_layout.addWidget(steplist_label)
        steplist_layout.addWidget(self.step_list)
        steplist_layout.addWidget(self.remove_step_button)

        # Right Parameter Definition Window
        param_label = QtGui.QLabel("Step Parameters")
        param_label.setFixedHeight(40)
        self.param_layout = QtGui.QFormLayout()
        param_frame = QtGui.QFrame()
        param_frame.setLayout(self.param_layout)

        param_box_layout = QtGui.QVBoxLayout()
        param_box_layout.addWidget(param_label)
        param_box_layout.addWidget(param_frame)

        # Main Layout
        frame_layout = QtGui.QHBoxLayout()
        frame_layout.addLayout(addstep_layout, stretch=1)
        frame_layout.addLayout(steplist_layout, stretch=1)
        frame_layout.addLayout(param_box_layout, stretch=3)

        buttonBox = QtGui.QDialogButtonBox(QtGui.QDialogButtonBox.Ok | QtGui.QDialogButtonBox.Cancel)
        buttonBox.accepted.connect(self.accept)
        buttonBox.rejected.connect(self.reject)

        main_layout = QtGui.QVBoxLayout()
        main_layout.addLayout(frame_layout)
        main_layout.addWidget(buttonBox)

        self.setLayout(main_layout)
        self.setWindowTitle("Make New Protocol")

        # List to store dicts of steps and params
        self.steps = []

    def add_step(self):
        task_type = self.task_list.currentItem().text()
        new_item = QtGui.QListWidgetItem()
        new_item.setText(task_type)
        task_params = copy.deepcopy(tasks.TASK_LIST[task_type].PARAMS)

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
        sender = self.sender()
        sender_text = sender.text()
        current_step = self.step_list.item(self.step_list.currentRow())
        current_step.setText(sender_text)

    def remove_step(self):
        step_index = self.step_list.currentRow()
        del self.steps[step_index]
        self.step_list.takeItem(step_index)

    def populate_params(self):
        self.clear_params()

        # Get current item index
        step_index = self.step_list.currentRow()
        step_dict = self.steps[step_index]

        # Iterate through params to make input widgets
        for k, v in step_dict.items():
            # Make Input Widget depending on type
            # Each Input type needs a different widget type,
            # and each widget type has different methods to get/change values, so we have to do this ugly
            if v['type'] == 'int' or v['type'] == 'str':
                rowtag = QtGui.QLabel(v['tag'])
                input_widget = QtGui.QLineEdit()
                input_widget.setObjectName(k)
                if v['type'] == 'int':
                    input_widget.setValidator(QtGui.QIntValidator())
                input_widget.editingFinished.connect(self.set_param)
                if 'value' in v.keys():
                    input_widget.setText(v['value'])
                elif v['type'] == 'str':
                    self.steps[step_index][k]['value'] = ''
                self.param_layout.addRow(rowtag,input_widget)

            elif v['type'] == 'check':
                rowtag = QtGui.QLabel(v['tag'])
                input_widget = QtGui.QCheckBox()
                input_widget.setObjectName(k)
                input_widget.stateChanged.connect(self.set_param)
                if 'value' in v.keys():
                    input_widget.setChecked(v['value'])
                else:
                    self.steps[step_index][k]['value'] = False
                self.param_layout.addRow(rowtag, input_widget)

            elif v['type'] == 'list':
                rowtag = QtGui.QLabel(v['tag'])
                input_widget = QtGui.QListWidget()
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
                self.sound_widget = Sound_Widget(self.prefs)
                self.sound_widget.setObjectName(k)
                self.sound_widget.pass_set_param_function(self.set_sounds)
                self.param_layout.addRow(self.sound_widget)
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


        # Iterate again to check for dependencies
        # no idea what i meant here -jls 180913
        # maybe greying out unavailable boxes?
        # for k, v in self.steps[step_index].items():
        #    pass

    def clear_params(self):
        while self.param_layout.count():
            child = self.param_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

    def reorder_steps(self, *args):
        # arg positions 1 and 4 are starting and ending positions in the list, respectively
        # We reorder our step list so the params line up.
        before = args[1]
        after = args[4]
        self.steps.insert(after, self.steps.pop(before))

    def set_param(self):
        sender = self.sender()
        param_name = sender.objectName()
        current_step = self.step_list.currentRow()
        sender_type = self.steps[current_step][param_name]['type']

        if sender_type == 'int' or sender_type == 'str':
            self.steps[current_step][param_name]['value'] = sender.text()
        elif sender_type == 'check':
            self.steps[current_step][param_name]['value'] = sender.isChecked()
        elif sender_type == 'list':
            list_text = sender.currentItem().text()
            list_value = self.steps[current_step][param_name]['values'][list_text]
            self.steps[current_step][param_name]['value'] = list_value
        elif sender_type == 'sounds':
            self.steps[current_step][param_name]['value'] = self.sound_widget.sound_dict

        # pprint(dict(self.steps[current_step]))

    def set_sounds(self):
        current_step = self.step_list.currentRow()
        self.steps[current_step]['sounds']['value'] = self.sound_widget.sound_dict

    def set_graduation(self):
        current_step = self.step_list.currentRow()
        grad_type = self.grad_widget.type
        grad_params = self.grad_widget.param_dict
        self.steps[current_step]['graduation']['value'] = {'type':grad_type,'value':grad_params}


    def check_depends(self):
        # TODO: Make dependent fields unavailable if dependencies unmet
        # I mean if it really matters
        pass

class Graduation_Widget(QtGui.QWidget):
    def __init__(self):
        super(Graduation_Widget, self).__init__()

        # Grad type dropdown
        type_label = QtGui.QLabel("Graduation Criterion:")
        self.type_selection = QtGui.QComboBox()
        self.type_selection.insertItems(0, tasks.GRAD_LIST.keys())
        self.type_selection.currentIndexChanged.connect(self.populate_params)

        # Param form
        self.param_layout = QtGui.QFormLayout()

        layout = QtGui.QVBoxLayout()
        layout.addWidget(type_label)
        layout.addWidget(self.type_selection)
        layout.addLayout(self.param_layout)

        self.setLayout(layout)

        self.param_dict = {}

        # we receive a method from the protocol wizard to
        # store the graduation params in the step dictionary
        self.set_graduation = None

        self.populate_params()

    def populate_params(self, params=None):
        self.clear_params()
        self.type = self.type_selection.currentText()
        self.param_dict['type'] = self.type

        for k in tasks.GRAD_LIST[self.type].PARAMS:
            edit_box = QtGui.QLineEdit()
            edit_box.setObjectName(k)
            edit_box.editingFinished.connect(self.store_param)
            if isinstance(params, dict):
                if k in params.keys():
                    edit_box.setText(params[k])
            self.param_layout.addRow(QtGui.QLabel(k), edit_box)

    def clear_params(self):
        while self.param_layout.count():
            child = self.param_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

    def store_param(self):
        sender = self.sender()
        name = sender.objectName()
        self.param_dict[name] = sender.text()
        print(self.param_dict)
        self.set_graduation()

class Drag_List(QtGui.QListWidget):
    # graciously copied from
    # https://stackoverflow.com/a/25614674
    fileDropped = QtCore.Signal(list)

    def __init__(self):
        super(Drag_List, self).__init__()
        self.setAcceptDrops(True)

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls:
            e.accept()
        else:
            e.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls:
            event.setDropAction(QtCore.Qt.CopyAction)
            event.accept()
        else:
            event.ignore()

    def dropEvent(self, event):
        if event.mimeData().hasUrls:
            event.setDropAction(QtCore.Qt.CopyAction)
            event.accept()
            links = []
            for url in event.mimeData().urls():
                links.append(str(url.toLocalFile()))
            self.fileDropped.emit(links)
        else:
            event.ignore()

class Sound_Widget(QtGui.QWidget):
    def __init__(self, prefs):
        QtGui.QWidget.__init__(self)

        self.prefs = prefs
        self.sounddir = self.prefs['SOUNDDIR']

        # Left sounds
        left_label = QtGui.QLabel("Left Sounds")
        left_label.setFixedHeight(30)
        self.left_list = Drag_List()
        self.left_list.fileDropped.connect(self.files_dropped)
        self.left_list.setObjectName("L")
        self.add_left_button = QtGui.QPushButton("+")
        self.add_left_button.setFixedHeight(30)
        self.add_left_button.clicked.connect(lambda: self.add_sound('L'))
        self.remove_left_button = QtGui.QPushButton("-")
        self.remove_left_button.setFixedHeight(30)
        self.remove_left_button.clicked.connect(lambda: self.remove_sound('L'))

        left_layout = QtGui.QVBoxLayout()
        left_button_layout = QtGui.QHBoxLayout()
        left_button_layout.addWidget(self.add_left_button)
        left_button_layout.addWidget(self.remove_left_button)
        left_layout.addWidget(left_label)
        left_layout.addWidget(self.left_list)
        left_layout.addLayout(left_button_layout)

        # Right sounds
        right_label = QtGui.QLabel("Right Sounds")
        right_label.setFixedHeight(30)
        self.right_list = Drag_List()
        self.right_list.fileDropped.connect(self.files_dropped)
        self.right_list.setObjectName("R")
        self.add_right_button = QtGui.QPushButton("+")
        self.add_right_button.setFixedHeight(30)
        self.add_right_button.clicked.connect(lambda: self.add_sound('R'))
        self.remove_right_button = QtGui.QPushButton("-")
        self.remove_right_button.setFixedHeight(30)
        self.remove_right_button.clicked.connect(lambda: self.remove_sound('R'))

        right_layout = QtGui.QVBoxLayout()
        right_button_layout = QtGui.QHBoxLayout()
        right_button_layout.addWidget(self.add_right_button)
        right_button_layout.addWidget(self.remove_right_button)
        right_layout.addWidget(right_label)
        right_layout.addWidget(self.right_list)
        right_layout.addLayout(right_button_layout)

        self.sound_dict = {'L': [], 'R': []}

        main_layout = QtGui.QHBoxLayout()
        main_layout.addLayout(left_layout)
        main_layout.addLayout(right_layout)
        self.setLayout(main_layout)

        # TODO:Add drag and drop for files

    def pass_set_param_function(self, set_param_fnxn):
        self.set_sounds = set_param_fnxn

    def add_sound(self, side):
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
        # Populate the sound lists after re-selecting a step
        self.sound_dict = sound_dict
        for k in self.sound_dict['L']:
            self.left_list.addItem(k['type'])
        for k in self.sound_dict['R']:
            self.right_list.addItem(k['type'])

    def files_dropped(self, files):
        # TODO: Make this more general...
        msg = QtGui.QMessageBox()
        msg.setText("Are these Speech sounds in the format '/speaker/cv/cv_#.wav'?")
        msg.setStandardButtons(QtGui.QMessageBox.Yes | QtGui.QMessageBox.No)
        ret = msg.exec_()

        sender = self.sender()
        side = sender.objectName()

        if ret == QtGui.QMessageBox.No:
            for f in files:
                f = f.strip(self.sounddir)

                self.sound_dict[side].append({'type':'File', 'path':f})
                if side == 'L':
                    self.left_list.addItem(f)
                elif side == 'R':
                    self.right_list.addItem(f)


        elif ret == QtGui.QMessageBox.Yes:
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

    class Add_Sound_Dialog(QtGui.QDialog):
        def __init__(self):
            QtGui.QDialog.__init__(self)

            # Sound type dropdown
            type_label = QtGui.QLabel("Sound Type:")
            self.type_selection = QtGui.QComboBox()
            self.type_selection.insertItems(0, sounds.SOUND_LIST.keys())
            self.type_selection.currentIndexChanged.connect(self.populate_params)

            # Param form
            self.param_layout = QtGui.QFormLayout()

            # Button box
            buttonBox = QtGui.QDialogButtonBox(QtGui.QDialogButtonBox.Ok | QtGui.QDialogButtonBox.Cancel)
            buttonBox.accepted.connect(self.accept)
            buttonBox.rejected.connect(self.reject)

            # Layout
            layout = QtGui.QVBoxLayout()
            layout.addWidget(type_label)
            layout.addWidget(self.type_selection)
            layout.addLayout(self.param_layout)
            layout.addWidget(buttonBox)

            self.setLayout(layout)

            # dict for storing params
            self.param_dict = {}

        def populate_params(self):
            self.clear_params()

            self.type = self.type_selection.currentText()
            self.param_dict['type'] = self.type

            for k in sounds.SOUND_LIST[self.type].PARAMS:
                edit_box = QtGui.QLineEdit()
                edit_box.setObjectName(k)
                edit_box.editingFinished.connect(self.store_param)
                self.param_layout.addRow(QtGui.QLabel(k), edit_box)

        def clear_params(self):
            while self.param_layout.count():
                child = self.param_layout.takeAt(0)
                if child.widget():
                    child.widget().deleteLater()

        def store_param(self):
            sender = self.sender()
            name = sender.objectName()
            self.param_dict[name] = sender.text()

###################################3
# Tools
######################################

class Calibrate_Water(QtGui.QDialog):
    def __init__(self, pilots, message_fn):
        super(Calibrate_Water, self).__init__()

        self.pilots = pilots
        self.send_message = message_fn

    class Pilot_Ports(QtGui.QWidget):
        def __init__(self, pilot, message_fn, n_clicks=1000, click_dur=30):
            super(Pilot_Ports, self).__init__()

            self.pilot = pilot
            self.send_message = message_fn

        def init_ui(self):
            #
            pass




class Weights(QtGui.QTableWidget):
    def __init__(self, mice_weights):
        super(Weights, self).__init__()

        self.mice_weights = mice_weights




        self.colnames = odict()
        self.colnames['mouse'] = "Mouse"
        self.colnames['date'] = "Date"
        self.colnames['baseline_mass'] = "Baseline"
        self.colnames['minimum_mass'] = "Minimum"
        self.colnames['start'] = 'Starting Mass'
        self.colnames['stop'] = 'Stopping Mass'

        self.setSizePolicy(QtGui.QSizePolicy.Expanding, QtGui.QSizePolicy.Expanding)

        self.init_ui()


    def init_ui(self):
        # set shape (rows by cols
        self.shape = (len(self.mice_weights), len(self.colnames.keys()))
        self.setRowCount(self.shape[0])
        self.setColumnCount(self.shape[1])


        for row in range(self.shape[0]):
            for j, col in enumerate(self.colnames.keys()):
                if col == "date":
                    format_date = datetime.datetime.strptime(self.mice_weights[row][col], '%y%m%d-%H%M%S')
                    format_date = format_date.strftime('%b %d')
                    item = QtGui.QTableWidgetItem(format_date)
                elif col == "stop":
                    stop_wt = str(self.mice_weights[row][col])
                    minimum = float(self.mice_weights[row]['minimum_mass'])
                    item = QtGui.QTableWidgetItem(stop_wt)
                    if float(stop_wt) < minimum:
                        item.setBackground(QtGui.QColor(255,0,0))

                else:
                    item = QtGui.QTableWidgetItem(str(self.mice_weights[row][col]))
                self.setItem(row, j, item)

        # make headers
        self.setHorizontalHeaderLabels(self.colnames.values())

        self.sortItems(0)



class Expanding_Tabs(QtGui.QTabBar):
    # The expanding method of the QTabBar doesn't work,
    # we have to manually adjust the size policy and size hint
    def __init__(self, width=30):
        super(Expanding_Tabs, self).__init__()
        self.setSizePolicy(QtGui.QSizePolicy.Policy.Fixed, QtGui.QSizePolicy.Policy.Expanding)
        self.width = width

    def tabSizeHint(self, index):
        # Pretty janky, but the tab bar is two children deep from the main widget
        # First compute the size taken up by the 'new' button and the margin
        # We assume the code is unchanged that binds our width to that button's width
        #ctl_panel_handle = self.parent().parent()
        #ctl_panel_handle = self.parent().parent()
        #margins = ctl_panel_handle.layout.getContentsMargins()
        #nudge_size = self.width + margins[1]*2 + margins[3]*2 + 25 + ctl_panel_handle.layout.spacing() # top and bottom
        # TODO: MAKE THIS NON JANKY, THERE IS SOME EXTRA SPACE IN THE PADDING COME BACK WHEN SOBER N PATIENT
        #return QtCore.QSize(self.width, (ctl_panel_handle.frameGeometry().height()-nudge_size)/float(self.count()))
        newsize = QtCore.QSize(self.width, float(self.parent().geometry().height())/float(self.count()))
        return newsize

class Stacked_Tabs(QtGui.QTabBar):
    # Setting tab position to west also rotates text 90 degrees, which is dumb
    # From https://stackoverflow.com/questions/3607709/how-to-change-text-alignment-in-qtabwidget
    def __init__(self, width=150, height=30):
        super(Stacked_Tabs, self).__init__()
        self.tabSize = QtCore.QSize(width, height)

    def paintEvent(self, event):
        painter = QtGui.QStylePainter(self)
        option = QtGui.QStyleOptionTab()

        #painter.begin(self)
        for index in range(self.count()):
            self.initStyleOption(option, index)
            tabRect = self.tabRect(index)
            tabRect.moveLeft(10)
            painter.drawControl(QtGui.QStyle.CE_TabBarTabShape, option)
            painter.drawText(tabRect, QtCore.Qt.AlignVCenter | QtCore.Qt.TextDontClip,
                             self.tabText(index))

        painter.end()

    def tabSizeHint(self, index):
        return self.tabSize
