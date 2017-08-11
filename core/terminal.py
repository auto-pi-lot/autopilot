# The terminal is the user-facing GUI that controls the Pis

__version__ = '0.1'
__author__  = 'Jonny Saunders <JLSaunders987@gmail.com'

import argparse
import json
import sys
import os
import datetime
import copy
import logging
import threading
import multiprocessing
import time
from collections import OrderedDict as odict
from PySide import QtCore
from PySide import QtGui
from pprint import pprint
import zmq
from zmq.eventloop.ioloop import IOLoop
from zmq.eventloop.zmqstream import ZMQStream

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mouse import Mouse
from networking import Terminal_Networking
import tasks
import sounds

# TODO: Oh holy hell just rewrite all the inter-widget communication as zmq
# TODO: Be more complete about generating logs
# TODO: Save logs on exit
# TODO: Make exit graceful

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
        # TODO: Make form layout with left column having status icons
        # TODO: Make status icon graphics
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
                               biography=biography_vals)

            if 'protocol' in protocol_vals.keys() and 'step' in protocol_vals.keys():
                protocol_file = os.path.join(prefs['PROTOCOLDIR'], protocol_vals['protocol'] + '.json')
                self.mouse.assign_protocol(protocol_file, int(protocol_vals['step']))

            # Update panels and pilot db, select new mouse
            self.mice.append(biography_vals['id'])
            self.create_buttons(self.mice, biography_vals['id'])
            self.pilot_panel.update_db()

    def select_mouse(self, mouse=None):
        if isinstance(mouse, basestring):
            # If we were specifically passed the mouse
            mouse_id = mouse
        else:
            # The mouse's button was clicked
            sender = self.sender()
            sender = sender.checkedButton()
            mouse_id = sender.text()

        # Try to close the mouse file if one is open
        try:
            self.mouse.h5f.close()
        except:
            pass

        self.mouse = Mouse(mouse_id)
        if not hasattr(self.mouse,'current'):
            # Mouse doesn't have a protocol, we pass nothing
            self.param_trigger()
        else:
            # We pass the protocol dict and step
            self.param_trigger(self.mouse.current, self.mouse.step)

    def give_pilot_panel(self, pilot_panel):
        self.pilot_panel = pilot_panel

    def give_param_trigger(self, param_trigger):
        # We are given a function that tells the main window to make a param window
        self.param_trigger = param_trigger

    def assign_protocol(self):
        # Get list of available protocols
        protocol_list = os.listdir(prefs['PROTOCOLDIR'])
        protocol_list = [os.path.splitext(p)[0] for p in protocol_list]

        protocol_str, ok = QtGui.QInputDialog.getItem(self, "Select Protocol",
                "Protocol:", protocol_list, 0, False)
        if not ok:
            return

        # Load the protocol and parse its steps
        protocol_file = os.path.join(prefs['PROTOCOLDIR'],protocol_str + '.json')
        with open(protocol_file) as protocol_file_open:
            protocol = json.load(protocol_file_open)

        step_list = []
        step_ind   = {}
        for i, s in enumerate(protocol):
            step_list.append(s['step_name'])
            step_ind[s['step_name']] = i

        step_str, ok = QtGui.QInputDialog.getItem(self, "Select Step",
                "Step:", step_list, 0, False)
        if not ok:
            return
        
        # Get the step index
        step_number = step_ind[step_str]

        # Assign protocol in mouse object
        self.mouse.assign_protocol(protocol_file, step_number)

        # Repopulate param window
        self.select_mouse(self.mouse.name)

class Parameters(QtGui.QWidget):
    '''
    Read task parameters from mouse protocol, populate with buttons, etc.
    '''
    def __init__(self):

        QtGui.QWidget.__init__(self)

        # main layout
        self.layout = QtGui.QVBoxLayout(self)

        # Widget label
        label = QtGui.QLabel()
        label.setText("Parameters")
        label.setFixedHeight(30)

        # close button
        self.close_button = QtGui.QPushButton('X')
        self.close_button.setFixedSize(30,30)

        # Combine label and close button
        top_panel = QtGui.QHBoxLayout()
        top_panel.addWidget(label)
        top_panel.addWidget(self.close_button)

        # Form Layout for params
        param_frame = QtGui.QFrame()
        param_frame.setObjectName("parameter_container")
        param_frame.setStyleSheet("#parameter_container {background-color:pink;}")
        self.param_layout = QtGui.QFormLayout()
        param_frame.setLayout(self.param_layout)

        # Main layout
        self.layout.addLayout(top_panel)
        self.layout.addWidget(param_frame)
        self.setLayout(self.layout)

        self.step = None
        self.protocol = None

        #self.show()

    def clear_params(self):
        while self.param_layout.count():
            child = self.param_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

    def populate_params(self, protocol, step):
        # We want to hang on to the protocol and step
        # because they are direct references to the mouse file,
        # but we don't need to have them passed every time
        self.clear_params()

        self.step = step
        self.protocol = protocol

        # Get step list and a dict to convert names back to ints
        self.step_list = []
        self.step_ind  = {}
        for i, s in enumerate(self.protocol):
            self.step_list.append(s['step_name'])
            self.step_ind[s['step_name']] = i

        # Combobox for step selection
        step_label = QtGui.QLabel("Current Step:")
        self.step_selection = QtGui.QComboBox()
        self.step_selection.insertItems(0, self.step_list)
        self.step_selection.setCurrentIndex(self.step)
        self.step_selection.currentIndexChanged.connect(self.step_changed)

        self.param_layout.addRow(step_label, self.step_selection)

        # Populate params for current step
        step_params = self.protocol[self.step]
        task_type = step_params['task_type']
        # Load the base tasks' params so we know what we're making
        self.task_params = copy.deepcopy(tasks.TASK_LIST[task_type].PARAMS)

        for k, v in self.task_params.items():
            if v['type'] == 'int' or v['type'] == 'str':
                rowtag = QtGui.QLabel(v['tag'])
                input_widget = QtGui.QLineEdit()
                input_widget.setObjectName(k)
                if v['type'] == 'int':
                    input_widget.setValidator(QtGui.QIntValidator())
                input_widget.textEdited.connect(self.set_param)
                if k in step_params.keys():
                    input_widget.setText(step_params[k])
                self.param_layout.addRow(rowtag,input_widget)
            elif v['type'] == 'check':
                rowtag = QtGui.QLabel(v['tag'])
                input_widget = QtGui.QCheckBox()
                input_widget.setObjectName(k)
                input_widget.stateChanged.connect(self.set_param)
                if k in step_params.keys():
                    input_widget.setChecked(step_params[k])
                self.param_layout.addRow(rowtag, input_widget)
            elif v['type'] == 'list':
                rowtag = QtGui.QLabel(v['tag'])
                input_widget = QtGui.QListWidget()
                input_widget.setObjectName(k)
                input_widget.insertItems(0, sorted(v['values'], key=v['values'].get))
                input_widget.itemSelectionChanged.connect(self.set_param)
                if k in step_params.keys():
                    select_item = input_widget.item(step_params[k])
                    input_widget.setCurrentItem(select_item)
                self.param_layout.addRow(rowtag, input_widget)
            elif v['type'] == 'sounds':
                self.sound_widget = Sound_Widget()
                self.sound_widget.setObjectName(k)
                self.sound_widget.pass_set_param_function(self.set_sounds)
                self.param_layout.addRow(self.sound_widget)
                if k in step_params.keys():
                    self.sound_widget.populate_lists(step_params[k])
            elif v['type'] == 'label':
                # This is a .json label not for display
                pass


    def step_changed(self):
        # We're passed a new step,
        # and since self.step is a direct ref to mouse file,
        # changing it here should change it there.
        self.step = self.step_selection.currentIndex()
        step_name = self.step_selection.currentText()

        self.update_history('step', step_name, self.step)

        self.populate_params(self.protocol, self.step)

    def set_param(self):
        sender = self.sender()
        param_name = sender.objectName()
        sender_type = self.task_params[param_name]['type']

        if sender_type == 'int' or sender_type == 'str':
            new_val = sender.text()
            self.protocol[self.step][param_name] = new_val
        elif sender_type == 'check':
            new_val = sender.isChecked()
            self.protocol[self.step][param_name] = new_val
        elif sender_type == 'list':
            list_text = sender.currentItem().text()
            new_val = self.task_params[param_name]['values'][list_text]
            self.protocol[self.step][param_name] = new_val
        elif sender_type == 'sounds':
            new_val = self.sound_widget.sound_dict
            self.protocol[self.step][param_name] = new_val

        self.update_history('param', param_name, new_val)
        self.mouse.h5f.flush()


    def set_sounds(self):
        self.protocol[self.step]['sounds'] = self.sound_widget.sound_dict


    def assign_protocol(self, assign_protocol_function):
        assign_protocol_button = QtGui.QPushButton('Assign Protocol')
        assign_protocol_button.clicked.connect(assign_protocol_function)
        self.param_layout.addRow(assign_protocol_button)

    def give_mouse_object(self,mouse):
        # We are given the mouse object's update_params function
        self.mouse = mouse
        self.update_history = self.mouse.update_history

    def give_close_function(self, close_function):
        self.close_button.clicked.connect(close_function)


class DataView(QtGui.QWidget):
    # TODO: Use pyqtgraph for this: http://www.pyqtgraph.org/
    # TODO: Spawn widget in own process, spawn each plot in own thread with subscriber and loop
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

            # List available protocols
            protocol_list = os.listdir(prefs['PROTOCOLDIR'])
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
            protocol_file = os.path.join(prefs['PROTOCOLDIR'],protocol_str + '.json')
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
                self.param_layout.addRow(rowtag,input_widget)
            elif v['type'] == 'check':
                rowtag = QtGui.QLabel(v['tag'])
                input_widget = QtGui.QCheckBox()
                input_widget.setObjectName(k)
                input_widget.stateChanged.connect(self.set_param)
                if 'value' in v.keys():
                    input_widget.setChecked(v['value'])
                self.param_layout.addRow(rowtag, input_widget)
            elif v['type'] == 'list':
                rowtag = QtGui.QLabel(v['tag'])
                input_widget = QtGui.QListWidget()
                input_widget.setObjectName(k)
                input_widget.insertItems(0, sorted(v['values'], key=v['values'].get))
                input_widget.itemSelectionChanged.connect(self.set_param)
                if 'value' in v.keys():
                    select_item = input_widget.item(v['value'])
                    input_widget.setCurrentItem(select_item)
                self.param_layout.addRow(rowtag, input_widget)
            elif v['type'] == 'sounds':
                self.sound_widget = Sound_Widget()
                self.sound_widget.setObjectName(k)
                self.sound_widget.pass_set_param_function(self.set_sounds)
                self.param_layout.addRow(self.sound_widget)
                if 'value' in v.keys():
                    self.sound_widget.populate_lists(v['value'])
            elif v['type'] == 'label':
                # This is a .json label not for display
                pass

            # Step name needs to be hooked up to the step list text

            if k == 'step_name':
                input_widget.editingFinished.connect(self.rename_step)


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

    def check_depends(self):
        # TODO: Make dependent fields unavailable if dependencies unmet
        # I mean if it really matters
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
        self.right_list = QtGui.QListWidget()
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

        # Declare attributes
        self.context = None
        self.loop    = None
        self.pusher = None
        self.listener  = None
        self.networking = None
        self.rows = None #handles to row writing functions
        self.networking_ok = False

        # Start Logging
        timestr = datetime.datetime.now().strftime('%y%m%d_%H%M%S')
        log_file = os.path.join(prefs['LOGDIR'], 'Terminal_Log_{}.log'.format(timestr))

        self.logger = logging.getLogger('main')
        self.log_handler = logging.FileHandler(log_file)
        self.log_formatter = logging.Formatter("%(asctime)s %(levelname)s : %(message)s")
        self.log_handler.setFormatter(self.log_formatter)
        self.logger.addHandler(self.log_handler)
        self.logger.setLevel(logging.INFO)
        self.logger.info('Terminal Logging Initiated')

        # Make invoker object to send GUI events back to the main thread
        self.invoker = Invoker()

        # Start GUI
        self.setWindowTitle('Terminal')
        self.initUI()

        # Start Networking
        self.spawn_network()
        self.init_network()

        time.sleep(1)

        self.check_network()




        #self.send_message('LISTENING')

        # Spawn a thread to check the network
        #self.check_network()

    def initUI(self):
        # Main panel layout
        self.panel_layout = QtGui.QHBoxLayout()
        self.panel_layout.setContentsMargins(0,0,0,0)

        # Init panels and add to layout
        self.pilot_panel = Pilots()
        self.mice_panel = Mice()
        self.data_panel = DataView()

        # Acquaint the panels
        self.pilot_panel.give_mice_panel(self.mice_panel)
        self.mice_panel.give_pilot_panel(self.pilot_panel)
        self.mice_panel.give_param_trigger(self.show_params)

        self.panel_layout.addWidget(self.pilot_panel, stretch = 1)
        self.panel_layout.addWidget(self.mice_panel, stretch = 1)
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

        self.connect_pilots_button = QtGui.QPushButton("Connect to Pilots")
        self.connect_pilots_button.clicked.connect(self.init_pilots)
        self.connect_pilots_button.setFixedHeight(40)

        self.top_strip = QtGui.QHBoxLayout()
        self.top_strip.addWidget(self.new_protocol_button)
        self.top_strip.addWidget(self.connect_pilots_button)
        self.top_strip.addStretch(1)
        self.top_strip.addWidget(self.logo)

        # Get variables from the widgets
        self.pilots = self.pilot_panel.pilots


        self.plot_container = QtGui.QFrame()
        self.plot_container.setLayout(self.panel_layout)
        self.plot_container.setContentsMargins(0,0,0,0)
        self.layout.addLayout(self.top_strip)
        self.layout.addWidget(self.plot_container)

        self.setLayout(self.layout)
        #self.showMaximized()
        self.show()
        logging.info('UI Initialized')

    def show_params(self, protocol=None, step=0):
        # Delete a param panel if one already exists
        if self.panel_layout.count() > 3:
            self.panel_layout.removeWidget(self.param_panel)
            self.param_panel.deleteLater()

        # We are either passed nothing if the mouse has no protocol, or a protocol dict
        self.param_panel = Parameters()

        if protocol:
            self.param_panel.give_mouse_object(self.mice_panel.mouse)
            self.param_panel.populate_params(protocol, step=step)

        else:
            self.param_panel.assign_protocol(self.mice_panel.assign_protocol)

        # Give closing function
        self.param_panel.give_close_function(self.hide_params)

        # Insert param panel
        self.panel_layout.insertWidget(2, self.param_panel, stretch=2)


    def hide_params(self):
        self.panel_layout.removeWidget(self.param_panel)
        self.param_panel.deleteLater()
        self.setLayout(self.layout)

    def start_mouse(self):
        # TODO: Give prefs panel an attribute to refer to the start_mouse function
        # TODO: Give this method to the prefs panel

        # ready table in mouse h5f Get handle to mouse h5f row object
        pass

    def stop_mouse(self):
        # flush table, handle coherence checking, close .h5f
        pass

    ##########################3
    # NETWORKING METHODS

    def spawn_network(self):
        # Start external communications in own process
        self.networking = Terminal_Networking()
        self.networking.start()

    def init_network(self):
        # Start internal communications
        self.context = zmq.Context()
        self.loop = IOLoop.instance()

        # Messenger to send messages to networking class
        # Subscriber to receive return messages
        self.pusher      = self.context.socket(zmq.PUSH)
        self.subscriber  = self.context.socket(zmq.SUB)

        self.pusher.connect('tcp://localhost:{}'.format(prefs['MSGPORT']))
        self.subscriber.connect('tcp://localhost:{}'.format(prefs['PUBPORT']))
        self.subscriber.setsockopt(zmq.SUBSCRIBE, b'T')
        self.subscriber.setsockopt(zmq.SUBSCRIBE, b'X')

        # Setup subscriber for looping
        self.subscriber = ZMQStream(self.subscriber, self.loop)
        self.subscriber.on_recv(self.handle_listen)

        # Listen dictionary - which methods to call for different messages
        self.listens = {
            'ALIVE': self.l_alive, # A Pi is telling us that it is alive
            'DEAD' : self.l_dead, # A Pi we requested is not responding
            'STATE': self.l_state, # A Pi has changed state
            'EVENT': self.l_event, # A Pi is returning data from an event
            'LISTENING': self.l_listening, # The networking object tells us it's online
            'PING' : self.l_ping # Someone wants to know if we're alive
        }

        # Start IOLoop in daemon thread
        self.loop_thread = threading.Thread(target=self.threaded_loop)
        self.loop_thread.daemon = True
        self.loop_thread.start()

        self.logger.info("Networking Initiated")

    def threaded_loop(self):
        while True:
            self.logger.info("Starting IOLoop")
            self.loop.start()

    def check_network(self):
        # Let's see if the network is alive
        self.logger.info("Contacting Networking Object")
        attempts = 0
        while not self.networking_ok and attempts < 10:
            self.send_message('LISTENING')
            attempts += 1
            time.sleep(1)

        if not self.networking_ok:
            self.logger.warning("No response from network object")

    def init_pilots(self):
        self.logger.info('Initializing Pilots')
        self.send_message('INIT', value=self.pilots.keys())

    def handle_listen(self, msg):
        # Listens are multipart target-msg messages
        # target = msg[0]
        message = json.loads(msg[1])

        if not all(i in message.keys() for i in ['key', 'value']):
            self.logger.warning('LISTEN Improperly formatted: {}'.format(msg))
            return

        self.logger.info('LISTEN {} - KEY: {}, VALUE: {}'.format(message['id'], message['key'], message['value']))

        listen_funk = self.listens[message['key']]
        listen_thread = threading.Thread(target=listen_funk, args=(message['value'],))
        listen_thread.start()

        # Tell the networking process that we got it
        self.send_message('RECVD', value=message['id'])


    def send_message(self, key, target='', value=''):
        msg = {'key': key, 'target': target, 'value': value}

        msg_thread = threading.Thread(target= self.pusher.send_json, args=(json.dumps(msg),))
        msg_thread.start()

        self.logger.info("MESSAGE SENT - Target: {}, Key: {}, Value: {}".format(target, key, value))

    def l_alive(self, value):
        # Change icon next to appropriate pilot button
        # If we have the value in our list of pilots...
        self.logger.info('arrived at gui setting, value: {}, pilots: {}'.format(value, self.pilots.keys()))
        if value in self.pilots.keys():
            self.logger.info('boolean passed')
            self.gui_event(self.pilot_panel.buttons[value].setStyleSheet, "background-color:green")
            self.logger.info('passed GUI setting')
            #self.pilot_panel.buttons[value].setStyleSheet("background-color:green")
        else:
            self.logger.info('boolean failed, returning')
            return

    def l_dead(self, value):
        # Change icon next to appropriate pilot button
        # If we have the value in our list of pilots...
        if value in self.pilots.keys():
            self.gui_event(self.pilot_panel.buttons[value].setStyleSheet, "background-color:red")
            #self.pilot_panel.buttons[value].setStyleSheet("background-color:red")
        else:
            return

    def l_state(self, value):
        # A Pi has changed state
        pass

    def l_event(self, value):
        # A Pi sends us either an event or a full trial's data
        pass

    def l_listening(self, value):
        self.networking_ok = True
        self.logger.info('Networking responds as alive')

    def l_ping(self, value):
        self.send_message('ALIVE', value=b'T')

        # TODO: Give params window handle to mouse panel's update params function
        # TODO: Give params window handle to Terminal's delete params function

    def new_protocol(self):
        self.new_protocol_window = Protocol_Wizard()
        self.new_protocol_window.exec_()

        if self.new_protocol_window.result() == 1:
            steps = self.new_protocol_window.steps

            # The values useful to the step functions are stored with a 'value' key in the param_dict
            save_steps = []
            for s in steps:
                param_values = {}
                for k, v in s.items():
                    if 'value' in v.keys():
                        param_values[k] = v['value']
                save_steps.append(param_values)

            # Name the protocol
            name, ok = QtGui.QInputDialog.getText(self, "Name Protocol", "Protocol Name:")
            if ok and name != '':
                protocol_file = os.path.join(prefs['PROTOCOLDIR'], name + '.json')
                with open(protocol_file, 'w') as pfile_open:
                    json.dump(save_steps, pfile_open)
            elif name == '' or not ok:
                placeholder_name = 'protocol_created_{}'.format(datetime.date.today().isoformat())
                protocol_file = os.path.join(prefs['PROTOCOLDIR'], placeholder_name + '.json')
                with open(protocol_file, 'w') as pfile_open:
                    json.dump(save_steps, pfile_open)

    def gui_event(self, fn, *args, **kwargs):
        # Don't ask me how this works, stolen from
        # https://stackoverflow.com/a/12127115
        QtCore.QCoreApplication.postEvent(self.invoker, InvokeEvent(fn, *args, **kwargs))


# Stuff to send signals to the main QT thread from spawned message threads
# https://stackoverflow.com/a/12127115

class InvokeEvent(QtCore.QEvent):
    EVENT_TYPE = QtCore.QEvent.Type(QtCore.QEvent.registerEventType())

    def __init__(self, fn, *args, **kwargs):
        QtCore.QEvent.__init__(self, InvokeEvent.EVENT_TYPE)
        self.fn = fn
        self.args = args
        self.kwargs = kwargs


class Invoker(QtCore.QObject):
    def event(self, event):
        event.fn(*event.args, **event.kwargs)

        return True


if __name__ == '__main__':
    # Parse arguments - this should have been called with a .json prefs file passed
    # We'll try to look in the default location first
    parser = argparse.ArgumentParser(description="Run an RPilot Terminal")
    parser.add_argument('-f', '--prefs', help="Location of .json prefs file (created during setup_terminal.py)")
    args = parser.parse_args()

    if not args.prefs:
        prefs_file = '/usr/rpilot/prefs.json'

        if not os.path.exists(prefs_file):
            raise Exception("No Prefs file passed, and file not in default location")

        raise Warning('No prefs file passed, loaded from default location. Should pass explicitly with -p')

    else:
        prefs_file = args.prefs

    with open(prefs_file) as prefs_file_open:
        prefs = json.load(prefs_file_open)

    app = QtGui.QApplication(sys.argv)
    ex = Terminal()
    sys.exit(app.exec_())


