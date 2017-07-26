# The terminal is the user-facing GUI that controls the Pis

__version__ = '0.1'
__author__  = 'Jonny Saunders <JLSaunders987@gmail.com'

import argparse
import json
import sys
import os
import datetime
from collections import OrderedDict as odict
from PySide import QtCore
from PySide import QtGui
from pprint import pprint

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mouse import Mouse
import tasks
import sounds


# http://zetcode.com/gui/pysidetutorial/layoutmanagement/
# https://wiki.qt.io/PySide_Tutorials

class Pilots(QtGui.QWidget):
    '''
    Widget container for all our pilots
    '''
    def __init__(self):
        QtGui.QWidget.__init__(self)

        # main layout
        self.layout = QtGui.QVBoxLayout(self)
        #self.layout.setContentsMargins(0,0,0,0)

        # Make containers to style backgrounds
        self.container = QtGui.QGroupBox()
        self.container.setObjectName("pilot_container")
        self.container.setStyleSheet("#pilot_container {background-color:blue;}")

        # Widget label
        label = QtGui.QLabel()
        label.setText("Pilots")
        #label.setAlignment(QtCore.Qt.AlignBottom)
        label.setFixedHeight(30)

        # Create vertical layouts to hold buttons and nest within main layout
        self.button_layout = QtGui.QVBoxLayout()
        self.container.setLayout(self.button_layout)
        self.layout.addWidget(label)
        self.layout.addWidget(self.container)
        self.setLayout(self.layout)

        # Create button group that houses button logic / exclusivity
        self.button_group = QtGui.QButtonGroup()
        self.button_group.buttonClicked.connect(self.select_pilot)

        # Get dict of pilots and make buttons
        with open(prefs['PILOT_DB']) as pilot_file:
            # load as ordered dictionary
            self.pilots = json.load(pilot_file, object_pairs_hook=odict)
        self.create_buttons()

    def create_buttons(self):
        self.clear_buttons()
        self.buttons = {}
        for p in self.pilots.keys():
            self.buttons[p] = (QtGui.QPushButton(str(p)))
            self.buttons[p].setCheckable(True)
            self.button_group.addButton(self.buttons[p])
            self.button_layout.addWidget(self.buttons[p])

        # Make an add pilot button
        self.add_pilot_button = QtGui.QPushButton("+")
        self.add_pilot_button.clicked.connect(self.create_pilot)
        self.button_layout.addWidget(self.add_pilot_button)
        self.button_layout.addStretch(1)

    def clear_buttons(self):
        while self.button_layout.count():
            child = self.button_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        for b in self.button_group.buttons():
            self.button_group.removeButton(b)

    class New_Pilot_Window(QtGui.QDialog):
        # Dialog window for declaring a new pilot
        def __init__(self):
            QtGui.QDialog.__init__(self)

            # Lines to add
            self.name = QtGui.QLineEdit()
            self.ip = QtGui.QLineEdit("0.0.0.0")

            # OK/Cancel buttons
            self.cancel = QtGui.QPushButton("Cancel")
            self.ok     = QtGui.QPushButton("OK")
            self.cancel.clicked.connect(self.reject)
            self.ok.clicked.connect(self.accept)

            # Add buttons to layout
            self.layout = QtGui.QFormLayout()
            self.layout.addRow(QtGui.QLabel("RPilot Name:"), self.name)
            self.layout.addRow(QtGui.QLabel("IP:"), self.ip)
            self.layout.addRow(self.cancel,self.ok)

            self.setLayout(self.layout)


    def create_pilot(self):
        self.pilot_window = self.New_Pilot_Window()
        self.pilot_window.exec_()

        # If OK was pressed, we make a new pilot
        if self.pilot_window.result() == 1:
            # TODO: List RPilots that are broadcasting availability and list rather than manual IP config
            # TODO: Test connection to RPilots

            self.pilots[self.pilot_window.name.text()] = {"ip": self.pilot_window.ip.text(), "mice":[]}
            self.update_db()

            self.create_buttons()

    def select_pilot(self):
        pilot_name = self.button_group.checkedButton().text()
        # This passes the actual list, not a copy,
        # so appending to it in the mice object appends to it here
        self.mice_panel.create_buttons(self.pilots[pilot_name]["mice"])
        pass

    def give_mice_panel(self, mice_panel):
        # Pass the instance of the mice panel so we know where to send signals
        self.mice_panel = mice_panel

    def update_db(self):
        with open(prefs['PILOT_DB'], 'w') as pilot_file:
            json.dump(self.pilots, pilot_file)

class Mice(QtGui.QWidget):
    '''
    Panel to list mice within a RPilot
    '''
    def __init__(self):
        QtGui.QWidget.__init__(self)

        # Main layout
        self.layout = QtGui.QVBoxLayout(self)

        # Containers to style background
        self.container = QtGui.QGroupBox()
        self.container.setObjectName("mice_container")
        self.container.setStyleSheet("#mice_container {background-color:green;}")

        # Widget Label
        label = QtGui.QLabel(self)
        label.setText("Mice")
        label.setFixedHeight(30)

        # Vertical layout to hold buttons, nest within container
        self.button_layout = QtGui.QVBoxLayout()
        self.button_layout.addStretch(1) # Since we don't immediately populate, add this now
        self.container.setLayout(self.button_layout)
        self.layout.addWidget(label)
        self.layout.addWidget(self.container)
        self.setLayout(self.layout)

        # Create button group that houses button logic / exclusivity
        self.button_group = QtGui.QButtonGroup()
        self.button_group.buttonClicked.connect(self.select_mouse)

        # Empty list of mice, passed from the pilot widget
        self.mice = []

        # Current Mouse, opened as Mouse Data model
        self.mouse = []


        #self.show()

    def create_buttons(self, mice, current=None):
        # Create the buttons for each mouse that a pilot owns
        self.clear_buttons()
        self.mice = mice
        self.buttons = {}
        for m in mice:
            self.buttons[m] = QtGui.QPushButton(str(m))
            self.buttons[m].setCheckable(True)
            self.button_group.addButton(self.buttons[m])
            self.button_layout.addWidget(self.buttons[m])

        # If we are passed a mouse to select, select it
        if current:
            self.buttons[current].setChecked(True)

        # Make an add mouse button
        self.add_mouse_button = QtGui.QPushButton("+")
        self.add_mouse_button.clicked.connect(self.create_mouse)
        self.button_layout.addWidget(self.add_mouse_button)
        self.button_layout.addStretch(1)

    def clear_buttons(self):
        while self.button_layout.count():
            child = self.button_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        for b in self.button_group.buttons():
            self.button_group.removeButton(b)


    def create_mouse(self):
        self.new_mouse_window = New_Mouse_Wizard()
        self.new_mouse_window.exec_()

        # If new mouse wizard completed successfully, get its values
        if self.new_mouse_window.result() == 1:
            biography_vals = self.new_mouse_window.bio_tab.values
            protocol_vals = self.new_mouse_window.task_tab.values

            # Make new mouse object
            self.mouse = Mouse(biography_vals['id'], new=True,
                               biography=biography_vals, protocol=protocol_vals)

            # Update panels and pilot db, select new mouse
            self.mice.append(biography_vals['id'])
            self.create_buttons(self.mice, biography_vals['id'])
            self.pilot_panel.update_db()

    def select_mouse(self):
        # TODO: Check if current mouse is already assigned, eg. from create_mouse
        pass

    def give_pilot_panel(self, pilot_panel):
        self.pilot_panel = pilot_panel

    def assign_protocol(self):
        # TODO: Read assigned protocol from setup
        pass

class Parameters(QtGui.QWidget):
    '''
    Read task parameters from mouse protocol, populate with buttons, etc.
    '''
    def __init__(self):
        QtGui.QWidget.__init__(self)

        # main layout
        self.layout = QtGui.QVBoxLayout(self)

        # Make containers to style backgrounds
        self.container = QtGui.QFrame()
        self.container.setObjectName("parameter_container")
        self.container.setStyleSheet("#parameter_container {background-color:pink;}")

        # Widget label
        label = QtGui.QLabel()
        label.setText("Parameters")
        label.setFixedHeight(30)

        # Form Layout for params
        self.form_layout = QtGui.QFormLayout()
        self.container.setLayout(self.form_layout)
        self.layout.addWidget(label)
        self.layout.addWidget(self.container)
        self.layout.addStretch(1)
        self.setLayout(self.layout)

        #self.show()

    def populate_params(self, mouse):
        mouse_path = os.path.join(prefs['DATADIR'],mouse+'.h5')

        # TODO: Actually should check if mouse file has params, should always exist if passed by mouse panel
        if not os.path.exists(mouse_path):
            self.form_layout.addRow(QtGui.QLabel("Mouse has no protocol!"))
            self.form_layout.addRow(QtGui.QPushButton("Assign Protocol"))
            return

        # TODO: Get params


    def assign_protocol(self):
        pass


class DataView(QtGui.QWidget):
    # TODO: Use pyqtgraph for this: http://www.pyqtgraph.org/
    def __init__(self):
        QtGui.QWidget.__init__(self)

        # Main Layout
        self.layout = QtGui.QVBoxLayout(self)

        # Containers to style backgrounds
        self.container = QtGui.QFrame()
        self.container.setObjectName("data_container")
        self.container.setStyleSheet("#data_container {background-color:orange;}")

        # Plot Selection Buttons
        self.plot_select = self.create_plot_buttons()

        # Plot Layout and put in container
        self.plot_layout = QtGui.QVBoxLayout()
        #self.plot_layout.addStretch(1)
        self.container.setLayout(self.plot_layout)

        # Assemble buttons and plots
        self.layout.addWidget(self.plot_select)
        self.layout.addWidget(self.container)
        self.setLayout(self.layout)

        #self.show()

    def create_plot_buttons(self):
        groupbox = QtGui.QGroupBox()
        groupbox.setFlat(True)
        groupbox.setFixedHeight(30)
        groupbox.setContentsMargins(0,0,0,0)
        #groupbox.setAlignment(QtCore.Qt.AlignBottom)

        check1 = QtGui.QCheckBox("Corrects")
        check1.setChecked(True)
        check2 = QtGui.QCheckBox("Responses")
        check3 = QtGui.QCheckBox("Rolling Accuracy")
        check4 = QtGui.QCheckBox("Bias")
        winsize = QtGui.QLineEdit("50")
        winsize.setFixedWidth(50)
        winsize_lab = QtGui.QLabel("Window Size")
        n_trials = QtGui.QLineEdit("50")
        n_trials.setFixedWidth(50)
        n_trials_lab = QtGui.QLabel("N Trials")

        hbox = QtGui.QHBoxLayout()
        hbox.setContentsMargins(0,0,0,0)
        hbox.addWidget(check1)
        hbox.addWidget(check2)
        hbox.addWidget(check3)
        hbox.addWidget(check4)
        hbox.addWidget(winsize)
        hbox.addWidget(winsize_lab)
        hbox.addStretch(1)
        hbox.addWidget(n_trials_lab)
        hbox.addWidget(n_trials)
        #hbox.setAlignment(QtCore.Qt.AlignBottom)

        groupbox.setLayout(hbox)

        return groupbox


# Mouse Biography Classes
# TODO: Make 'edit mouse' button
# TODO: Populate task tab and get possible levels, but also put those in param window
# TODO: Make experiment tags, save and populate?
class New_Mouse_Wizard(QtGui.QDialog):
    def __init__(self):
        QtGui.QDialog.__init__(self)

        tabWidget = QtGui.QTabWidget()

        self.bio_tab = self.Biography_Tab()
        self.task_tab = self.Task_Tab()
        tabWidget.addTab(self.bio_tab, "Biography")
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
            # We try but don't really care if we fail bc cmon
            #try:
            baseline = float(self.blmass.text())
            pct = float(self.minmass_pct.text()[:-1])/100
            self.minmass.setText(str(baseline*pct))
            #except:
            #    print(float(self.blmass.text()))
            #    print(float(self.minmass_pct.text()[:-1]))



    class Task_Tab(QtGui.QWidget):
        def __init__(self):
            QtGui.QWidget.__init__(self)

            topLabel = QtGui.QLabel("Protocols:")

            self.protocol_listbox = QtGui.QListWidget()
            # TODO: Load available protocols
            # Dummy for now
            protocols = ['test protocol']

            self.protocol_listbox.insertItems(0, protocols)

            # TODO: Get Steps
            self.step = QtGui.QSpinBox()
            max_step = 5
            self.step.setRange(1,5)
            self.step.setSingleStep(1)

            self.protocol_listbox.itemChanged.connect(lambda: self.update_return_dict('protocol'))
            self.step.valueChanged.connect(lambda: self.update_return_dict('step'))

            layout = QtGui.QVBoxLayout()
            layout.addWidget(topLabel)
            layout.addWidget(self.protocol_listbox)
            layout.addWidget(self.step)

            self.setLayout(layout)

            # Dict to return values
            self.values = {}

        def update_return_dict(self, key):
            sender = self.sender()
            self.values[key] = sender.text()


class Protocol_Wizard(QtGui.QDialog):
    def __init__(self):
        QtGui.QDialog.__init__(self)

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
        self.steps.append(tasks.TASK_LIST[task_type].PARAMS)
        self.step_list.addItem(new_item)
        self.step_list.setCurrentItem(new_item)


    def rename_step(self):
        pass

    def remove_step(self):
        pass

    def populate_params(self):
        # Widget dict to set dependencies later
        self.clear_params()
        widgets = {}

        # Get current item index
        step_index = self.step_list.currentRow()

        # Iterate through params to make input widgets
        for k, v in self.steps[step_index].items():
            # Make Input Widget depending on type
            if v['type'] == 'int':
                rowtag = QtGui.QLabel(v['tag'])
                input_widget = QtGui.QLineEdit()
                input_widget.setObjectName(k)
                input_widget.setValidator(QtGui.QIntValidator())
                input_widget.editingFinished.connect(self.set_param)
                self.param_layout.addRow(rowtag,input_widget)
            elif v['type'] == 'check':
                rowtag = QtGui.QLabel(v['tag'])
                input_widget = QtGui.QCheckBox()
                input_widget.setObjectName(k)
                input_widget.stateChanged.connect(self.set_param)
                self.param_layout.addRow(rowtag, input_widget)
            elif v['type'] == 'list':
                rowtag = QtGui.QLabel(v['tag'])
                input_widget = QtGui.QListWidget()
                input_widget.setObjectName(k)
                input_widget.insertItems(0, v['values'].keys())
                input_widget.itemSelectionChanged.connect(self.set_param)
                self.param_layout.addRow(rowtag, input_widget)
            elif v['type'] == 'sounds':
                self.sound_widget = self.Sound_Widget()
                self.sound_widget.setObjectName(k)
                self.sound_widget.pass_set_param_function(self.set_sounds)
                self.param_layout.addRow(self.sound_widget)

            widgets[k] = input_widget

        # Iterate again to check for dependencies
        for k, v in self.steps[step_index].items():
            pass

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

        if sender_type == 'int':
            self.steps[current_step][param_name]['value'] = sender.text()
        elif sender_type == 'check':
            self.steps[current_step][param_name]['value'] = sender.isChecked()
        elif sender_type == 'list':
            list_text = sender.currentItem().text()
            list_value = self.steps[current_step][param_name]['values'][list_text]
            self.steps[current_step][param_name]['value'] = list_value
        elif sender_type == 'sounds':
            self.steps[current_step][param_name]['value'] = self.sound_widget.sound_dict

        pprint(dict(self.steps[current_step]))

    def set_sounds(self):
        current_step = self.step_list.currentRow()
        self.steps[current_step]['sounds']['value'] = self.sound_widget.sound_dict

    def check_depends(self):
        pass


    class Sound_Widget(QtGui.QWidget):
        def __init__(self):
            QtGui.QWidget.__init__(self)

            # Left sounds
            left_label = QtGui.QLabel("Left Sounds")
            left_label.setFixedHeight(30)
            self.left_list = QtGui.QListWidget()
            self.add_left_button = QtGui.QPushButton("+")
            self.add_left_button.setFixedHeight(30)
            self.add_left_button.clicked.connect(lambda: self.add_sound('L'))

            left_layout = QtGui.QVBoxLayout()
            left_layout.addWidget(left_label)
            left_layout.addWidget(self.left_list)
            left_layout.addWidget(self.add_left_button)

            # Right sounds
            right_label = QtGui.QLabel("Right Sounds")
            right_label.setFixedHeight(30)
            self.right_list = QtGui.QListWidget()
            self.add_right_button = QtGui.QPushButton("+")
            self.add_right_button.setFixedHeight(30)
            self.add_right_button.clicked.connect(lambda: self.add_sound('R'))

            right_layout = QtGui.QVBoxLayout()
            right_layout.addWidget(right_label)
            right_layout.addWidget(self.right_list)
            right_layout.addWidget(self.add_right_button)

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
                    edit_box.editingFinished.connect(lambda: self.store_param(k, edit_box.text()))
                    self.param_layout.addRow(QtGui.QLabel(k), edit_box)

            def clear_params(self):
                while self.param_layout.count():
                    child = self.param_layout.takeAt(0)
                    if child.widget():
                        child.widget().deleteLater()

            def store_param(self, key, value):
                self.param_dict[key] = value









class Terminal(QtGui.QWidget):
    '''
    GUI for RPilot Terminal
    '''

    def __init__(self):
        # Initialize the superclass (QtGui.QWidget)
        QtGui.QWidget.__init__(self)
        self.setWindowTitle('Terminal')
        self.initUI()

    def initUI(self):
        # Main panel layout
        self.panel_layout = QtGui.QHBoxLayout()
        self.panel_layout.setContentsMargins(0,0,0,0)

        # Init panels and add to layout
        self.pilot_panel = Pilots()
        self.mice_panel = Mice()
        self.param_panel = Parameters()
        self.data_panel = DataView()

        # Acquaint the panels
        self.pilot_panel.give_mice_panel(self.mice_panel)
        self.mice_panel.give_pilot_panel(self.pilot_panel)

        self.panel_layout.addWidget(self.pilot_panel, stretch = 1)
        self.panel_layout.addWidget(self.mice_panel, stretch = 1)
        # TODO: Expand Params when mouse is clicked, hide when clicked again
        #self.panel_layout.addWidget(self.param_panel, stretch = 2)
        self.panel_layout.addWidget(self.data_panel, stretch=5)

        # add logo and new protocol button
        self.layout = QtGui.QVBoxLayout()
        self.layout.setContentsMargins(5,5,5,5)

        self.logo = QtGui.QLabel()
        self.logo.setPixmap(QtGui.QPixmap(prefs['REPODIR']+'/graphics/logo.png').scaled(265,40))
        self.logo.setFixedHeight(40)
        self.logo.setAlignment(QtCore.Qt.AlignRight)

        self.new_protocol_button = QtGui.QPushButton("New Protocol")
        self.new_protocol_button.clicked.connect(self.new_protocol)
        self.new_protocol_button.setFixedHeight(40)

        self.top_strip = QtGui.QHBoxLayout()
        self.top_strip.addWidget(self.new_protocol_button)
        self.top_strip.addStretch(1)
        self.top_strip.addWidget(self.logo)


        self.plot_container = QtGui.QFrame()
        self.plot_container.setLayout(self.panel_layout)
        self.plot_container.setContentsMargins(0,0,0,0)
        self.layout.addLayout(self.top_strip)
        self.layout.addWidget(self.plot_container)

        self.setLayout(self.layout)
        #self.showMaximized()
        self.show()

    def new_protocol(self):
        self.new_protocol_window = Protocol_Wizard()
        self.new_protocol_window.exec_()

        if self.new_protocol_window.result() == 1:
            protocol_dict = self.new_protocol_window.protocol_dict
            # TODO: Dump to JSON


if __name__ == '__main__':
    # Parse arguments - this should have been called with a .json prefs file passed
    # We'll try to look in the default location first
    parser = argparse.ArgumentParser(description="Run an RPilot Terminal")
    parser.add_argument('-p', '--prefs', help="Location of .json prefs file (created during setup_terminal.py)")
    args = parser.parse_args()

    if not args.prefs:
        prefs_file = '/usr/rpilot/prefs.json'

        if not os.path.exists(prefs_file):
            raise Exception("No Prefs file passed, and file not in default location")

        raise Warning('No prefs file passed, loaded from default location. Should pass explicitly with -p')

    else:
        prefs_file = args.prefs

    print(prefs_file)
    with open(prefs_file) as prefs_file_open:
        prefs = json.load(prefs_file_open)

    app = QtGui.QApplication(sys.argv)
    ex = Terminal()
    sys.exit(app.exec_())


