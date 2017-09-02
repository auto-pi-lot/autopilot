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
import pyqtgraph as pg
import zmq
from zmq.eventloop.ioloop import IOLoop
from zmq.eventloop.zmqstream import ZMQStream

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mouse import Mouse
from plots import Plot_Widget
from networking import Terminal_Networking
import tasks
import sounds

# TODO: Oh holy hell just rewrite all the inter-widget communication as zmq
# TODO: Be more complete about generating logs
# TODO: Make exit graceful

# http://zetcode.com/gui/pysidetutorial/layoutmanagement/
# https://wiki.qt.io/PySide_Tutorials


class Control_Panel(QtGui.QWidget):
    # Hosts two nested tab widgets to select pilot and mouse,
    # set params, run mice, etc.

    def __init__(self, pilots=None, mice=None, msg_fn=None, pilot_width=30, mouse_width=150, prefs=None):
        super(Control_Panel, self).__init__()
        # We should be passed a pilot odict {'pilot':[mouse1, mouse2]}
        # If we're not, try to load prefs, and if we don't have prefs, from default loc.

        self.prefs = prefs

        # We share a dict of mouse objects with the main Terminal class to avoid access conflicts
        # TODO: Pass mice list on instantiation
        self.mice = mice

        # We get the Terminal's send_message function and give it to all the Param windows on instantiation
        self.send_message = msg_fn

        if pilots:
            self.pilots = pilots
        else:
            try:
                with open(self.prefs['PILOT_DB']) as pilot_file:
                    self.pilots = json.load(pilot_file, object_pairs_hook=odict)
            except NameError:
                try:
                    with open('/usr/rpilot/pilot_db.json') as pilot_file:
                        self.pilots = json.load(pilot_file, object_pairs_hook=odict)
                except IOError:
                    Exception('Couldnt find pilot directory!')

        # Sizes to pass to the tab widgets
        self.pilot_width = pilot_width
        self.mouse_width = mouse_width

        self.init_ui()

    def init_ui(self):
        # Layout for whole widget
        self.layout = QtGui.QVBoxLayout()
        self.layout.setContentsMargins(0,0,0,0)
        self.setLayout(self.layout)

        # Make top row 'new' buttons
        new_button_panel = QtGui.QHBoxLayout()
        new_button_panel.setContentsMargins(0,0,0,0)
        self.new_pilot_button = QtGui.QPushButton('+')
        self.new_pilot_button.setFixedSize(self.pilot_width, self.pilot_width)
        self.new_pilot_button.clicked.connect(self.create_pilot)
        self.new_mouse_button = QtGui.QPushButton('+')
        margins = self.new_pilot_button.getContentsMargins()
        self.new_mouse_button.setFixedSize(self.mouse_width-5, self.pilot_width)
        self.new_mouse_button.clicked.connect(self.create_mouse)
        new_button_panel.addWidget(self.new_pilot_button)
        new_button_panel.addWidget(self.new_mouse_button)
        new_button_panel.addStretch(1)
        self.layout.addLayout(new_button_panel)

        # Make main pilot tab widget
        self.pilot_tabs = QtGui.QTabWidget()
        # NOTE! If you make the "new pilot" button bigger than 30x30px,
        # You must pass the vertical size to Expanding tabs or.. well you'll see.
        self.pilot_tabs.setTabBar(Expanding_Tabs(self.pilot_width))
        self.pilot_tabs.setUsesScrollButtons(False)
        self.pilot_tabs.setTabPosition(QtGui.QTabWidget.West)
        self.pilot_tabs.currentChanged.connect(self.select_pilot)

        self.layout.addWidget(self.pilot_tabs)

        # Make dict to store handles to mice tabs
        self.mouse_tabs = {}

        self.populate_tabs()
        self.hide_tabs()


    def populate_tabs(self, new_mouse=False):
        # Clear tabs if there are any
        # We can use clear even though it doesn't delete the sub-widgets because
        # adding a bunch of mice should be rare,
        # and the widgets themselves should be lightweight

        # If we are making a new mouse, we'll want to select it at the end.
        # Let's figure out which we should select first

        if new_mouse:
            current_pilot = self.pilot_tabs.currentIndex()
        else:
            current_pilot = 0

        # Try to clear our index changed flag if we have one so it doesn't get called 50 times
        self.pilot_tabs.currentChanged.disconnect()

        self.pilot_tabs.clear()

        # Iterate through pilots and mice, making tabs and subtabs
        for pilot, mice in self.pilots.items():
            mice_tabs = QtGui.QTabWidget()
            mice_tabs.setTabBar(Stacked_Tabs(width=self.mouse_width,
                                             height=self.pilot_width))
            mice_tabs.setTabPosition(QtGui.QTabWidget.West)
            for m in mice:
                param_widget = Parameters(pilot=pilot,
                                          msg_fn=self.send_message,
                                          hide_fn=self.hide_tabs)
                mice_tabs.addTab(param_widget, m)
            mice_tabs.currentChanged.connect(self.select_mouse)

            self.pilot_tabs.addTab(mice_tabs, pilot)

        self.pilot_tabs.setCurrentIndex(current_pilot)
        self.pilot_tabs.currentChanged.connect(self.select_pilot)
        #if new_mouse:
            # If we have just made a new mouse, we'll want to select the last one,#
            # Otherwise we're just switching between tabs and we want the first one
            #self.select_mouse(new_mouse=True)

    def hide_tabs(self):
        # It does what it says it does, you want it to be the width it is,
        # and you want this to be relatively sticky
        # because drawing panels and hiding them is less expensive
        # than we thought it was
        #self.pilot_tabs.currentWidget().setCurrentIndex(-1)
        self.pilot_tabs.setMaximumWidth(self.pilot_width+self.mouse_width)
        self.pilot_tabs.setSizePolicy(QtGui.QSizePolicy.Expanding, QtGui.QSizePolicy.Maximum)


    def create_pilot(self):
        name, ok = QtGui.QInputDialog.getText(self, "Pilot ID", "Pilot ID:")
        if ok and name != '':
            self.pilots[name] = []
            self.update_db()
            self.populate_tabs()
            # Make a mouse TabWidget
            #mice_tabs = QtGui.QTabWidget()
            #mice_tabs.setTabBar(Stacked_Tabs(width=self.mouse_width,
            #                                 height=self.pilot_width))
            #mice_tabs.setTabPosition(QtGui.QTabWidget.West)
            #mice_tabs.currentChanged.connect(self.select_mouse)
            #self.pilot_tabs.addTab(mice_tabs,name)
            #self.pilot_tabs.setCurrentWidget(mice_tabs)
            # TODO: Add a row to the dataview

        else:
            # Idk maybe pop a dialog window but i don't really see why
            pass

    def create_mouse(self):
        new_mouse_wizard = New_Mouse_Wizard(self.prefs['PROTOCOLDIR'])
        new_mouse_wizard.exec_()

        # If the wizard completed successfully, get its values
        if new_mouse_wizard.result() == 1:
            biography_vals = new_mouse_wizard.bio_tab.values

            # Make a new mouse object, make it temporary because we want to close it
            mouse_obj = Mouse(biography_vals['id'], new=True,
                              biography=biography_vals)

            # If a protocol was selected in the mouse wizard, assign it.
            try:
                protocol_vals = new_mouse_wizard.task_tab.values
                if 'protocol' in protocol_vals.keys() and 'step' in protocol_vals.keys():
                    protocol_file = os.path.join(prefs['PROTOCOLDIR'], protocol_vals['protocol'] + '.json')
                    mouse_obj.assign_protocol(protocol_file, int(protocol_vals['step']))
            except:
                # the wizard couldn't find the protocol dir, so no task tab was made
                pass


            # Close the file because we want to keep mouse objects only when they are running
            mouse_obj.close_h5f()

            # Add mouse to pilots dict, update it and our tabs
            current_pilot = self.pilot_tabs.tabText(self.pilot_tabs.currentIndex())
            self.pilots[current_pilot].append(biography_vals['id'])
            self.update_db()
            self.populate_tabs(new_mouse=True)




    def select_pilot(self):
        print('called')
        self.select_mouse(index=0)
        # Probably just ping it to check its status
        #pass

    def select_mouse(self, index=0):
        # When a mouse's button is clicked, we expand a parameters pane for it
        # This pane lets us give the mouse a protocol if it doesn't have one,
        # adjust the parameters if it does, and start the mouse running

        # sender is the mice qtabwidget, we we get the text of the current tab
        if self.pilot_tabs.currentWidget().count() == 0:
            # If the current mouse tab has no mice in it (we just made the pilot)
            # just chill until we do.
            self.hide_tabs()
            return

        sender = self.pilot_tabs.currentWidget()


        #if new_mouse:
        #    sender.setCurrentIndex(sender.count())
        mouse_id = sender.tabText(sender.currentIndex())

        # Set an arbitrarily large max width to counteract the spell of hide_tabs()
        # Set expanding size policy to let the params panel take as much space as it wants,
        # it is supposed to float, aftear all.
        self.pilot_tabs.setMaximumWidth(10000)
        self.pilot_tabs.setSizePolicy(QtGui.QSizePolicy.Expanding, QtGui.QSizePolicy.Expanding)

        # We check if there was a param window populated before and close it if it was
        for i in xrange(sender.count()):
            w = sender.widget(i)
            if hasattr(w.mouse, 'running'):
                if not w.mouse.running:
                    self.mice[w.mouse.name].close_h5f()
                    del self.mice[w.mouse.name]
                    w.mouse = None
            #w.hide_params()

        # open the mouse object if it isn't already
        if not mouse_id in self.mice:
            self.mice[mouse_id] = Mouse(mouse_id)
            mouse_obj = self.mice[mouse_id]
        else:
            mouse_obj = self.mice[mouse_id]

        params_widget = sender.widget(index)
        params_widget.show_params(mouse_obj)

        # TODO: Also look for mouse objects in our dict that aren't running and delete them

        #sender = sender.checkedButton()
        #self.mouse = sender.text()

    def update_db(self):
        # TODO: Pretty hacky, should explicitly pass prefs or find some way of making sure every object has it
        try:
            with open(prefs['PILOT_DB'], 'w') as pilot_file:
                json.dump(self.pilots, pilot_file)
        except NameError:
            try:
                with open('/usr/rpilot/pilot_db.json', 'w') as pilot_file:
                    json.dump(self.pilots, pilot_file)
            except IOError:
                Exception('Couldnt update pilot db!')
                # TODO: Probably just pop a dialog, don't need to crash shit.



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

        self.pilot = None # Currently selected pilot

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
        self.pilot = pilot_name
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

        # Name of currently selected mouse, do NOT load Mouse object here,
        # the main Terminal class should have all the Mouse objects because pyTables isn't thread-safe
        self.mouse = ''


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
            mouse_obj = Mouse(biography_vals['id'], new=True,
                               biography=biography_vals)

            if 'protocol' in protocol_vals.keys() and 'step' in protocol_vals.keys():
                protocol_file = os.path.join(prefs['PROTOCOLDIR'], protocol_vals['protocol'] + '.json')
                mouse_obj.assign_protocol(protocol_file, int(protocol_vals['step']))

            # make mouse_obj save to delete by closing h5f
            mouse_obj.close_h5f()

            # Update panels and pilot db, select new mouse
            self.mice.append(biography_vals['id'])
            self.create_buttons(self.mice, biography_vals['id'])
            self.pilot_panel.update_db()

    def select_mouse(self, mouse=None):
        if isinstance(mouse, basestring):
            # If we were specifically passed the mouse
            self.mouse = mouse
        else:
            # The mouse's button was clicked
            sender = self.sender()
            sender = sender.checkedButton()
            self.mouse = sender.text()

        # Call trigger to have terminal populate params for us
        self.param_trigger(self.mouse)

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
        mouse_obj = Mouse(self.mouse)
        mouse_obj.assign_protocol(protocol_file, step_number)
        mouse_obj.close_h5f()

        # Repopulate param window
        self.select_mouse(self.mouse)


class Parameters(QtGui.QWidget):
    # Reads and edits tasks parameters from a mouse's protocol
    def __init__(self, pilot, msg_fn, hide_fn):
        super(Parameters, self).__init__()

        # send_message function from Terminal, lets us start the task from here
        self.send_message = msg_fn

        # we keep track of what pilot we're nested under so starting tasks is easier
        self.pilot = pilot

        self.hide = hide_fn

        # Placeholders
        self.close_button = None
        self.param_layout = None
        self.step = None
        self.protocol = None
        self.mouse = None
        self.layout = None

        # Says if we are currently open or not
        self.populated = False

        # make layout objects

        self.init_ui()
        self.setVisible(False)


        # We want to do essentially nothing on init and only populate params when asked to
    def show_params(self, mouse_obj):
        self.populated = True
        self.setVisible(True)

        self.mouse = mouse_obj

        # If the mouse has a task assigned to it, we populate the window with its parameters
        # Otherwise we make a button to assign a protocol
        if hasattr(self.mouse, 'current'):
            self.populate_params(self.mouse.current, self.mouse.step)
        else:
            assign_protocol_button = QtGui.QPushButton('Assign Protocol')
            assign_protocol_button.clicked.connect(self.assign_protocol)
            self.param_layout.addRow(assign_protocol_button)

    def hide_params(self):
        # call clear params, and also clear top panel
        self.populated = False
        if isinstance(self.param_layout, QtGui.QLayout):
            self.clear_layout(self.param_layout)
        # if isinstance(self.top_panel, QtGui.QLayout):
        #     self.clear_layout(self.top_panel)

        #for i in range(self.layout.count()):
        #    sublayout = self.layout.takeAt(i)
        #    self.layout.removeItem(sublayout)

        #self.param_layout = None
        #self.top_panel    = None
        self.setVisible(False)
        self.hide()

        # Set layout to blank layout
        #self.layout = QtGui.QVBoxLayout(self)
        #self.setLayout(self.layout)


    def init_ui(self):
        self.param_layout = QtGui.QFormLayout()
        self.top_panel = QtGui.QHBoxLayout()

        label = QtGui.QLabel('Parameters')
        label.setFixedHeight(30)
        self.close_button = QtGui.QPushButton('X')
        self.close_button.setFixedSize(30,30)
        self.close_button.clicked.connect(self.hide_params)
        self.top_panel.addWidget(label)
        self.top_panel.addWidget(self.close_button)

        self.layout = QtGui.QVBoxLayout(self)
        self.layout.addLayout(self.top_panel)
        self.layout.addLayout(self.param_layout)

        self.setLayout(self.layout)

        # Top bar - Label and close button

    def populate_params(self, protocol, step):
        # We want to hang on to the protocol and step
        # because they are direct references to the mouse file,
        # but we don't need to have them passed every time
        self.clear_layout(self.param_layout)

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

        # Make parameter widgets depending on type and populate with current values
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

        # Add button to start, stop run

        start_stop_button = QtGui.QPushButton("START/STOP")
        start_stop_button.setCheckable(True)
        # Set button status depending on status in mouse object
        if self.mouse.running:
            start_stop_button.setChecked(True)
        else:
            start_stop_button.setChecked(False)

        start_stop_button.toggled.connect(self.toggle_start)

        #self.param_layout.addRow(QtGui.QSpacerItem(1,1))
        self.param_layout.addRow(start_stop_button)

    def clear_layout(self, layout):
        while layout.count():
            child = layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

    def step_changed(self):
        # the step was changed! Change our parameters here and update the mouse object
        self.step = self.step_selection.currentIndex()
        step_name = self.step_selection.currentText()

        self.mouse.update_history('step', step_name, self.step)

        self.populate_params(self.protocol, self.step)

        # TODO: Send changes to the pi

    def set_param(self):
        # A param was changed in the window, update our values here and in the mouse object
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

        self.mouse.update_history('param', param_name, new_val)
        self.mouse.h5f.flush()

    def set_sounds(self):
        # Have to handle sounds slightly differently
        # because the sound widget updates its own parameters
        self.protocol[self.step]['sounds'] = self.sound_widget.sound_dict

    def assign_protocol(self):
        # Get list of available protocols
        protocol_list = os.listdir(prefs['PROTOCOLDIR'])
        protocol_list = [os.path.splitext(p)[0] for p in protocol_list]

        # Pop some dialogs to select a protocol and step
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
        self.show_params(self.mouse)

    def toggle_start(self, toggled):
        # If we're stopped, start, and vice versa...
        if toggled:
            # Sets the mouse to running, makes a file to store data
            self.mouse.prepare_run()

            # Prep task to send to pi
            task = self.protocol[self.step]
            task['mouse'] = self.mouse.name

            # TODO: Get last trial number and send to pi as well
            self.send_message('START', bytes(self.pilot), task)

        else:
            # Send message to pilot to stop running,
            # it should initiate a coherence checking routine to make sure
            # its data matches what the Terminal got,
            # so the terminal will handle closing the mouse object
            self.send_message('STOP', bytes(self.pilot))

class Parameters_Old(QtGui.QWidget):
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

        # Start/stop placeholder
        self.toggle_start = None

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

        # Add button to start, stop run

        start_stop_button = QtGui.QPushButton("START/STOP")
        start_stop_button.setCheckable(True)
        # Set button status depending on status in mouse object
        if self.mouse.running:
            start_stop_button.setChecked(True)
        else:
            start_stop_button.setChecked(False)

        start_stop_button.toggled.connect(self.toggle_start)

        #self.param_layout.addRow(QtGui.QSpacerItem(1,1))
        self.param_layout.addRow(start_stop_button)



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

    def give_startstop_function(self, toggle_start):
        self.toggle_start = toggle_start


# Mouse Biography Classes
# TODO: Make 'edit mouse' button
# TODO: Populate task tab and get possible levels, but also put those in param window
# TODO: Make experiment tags, save and populate?
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









class Terminal(QtGui.QWidget):
    '''
    GUI for RPilot Terminal
    '''

    def __init__(self, prefs):
        # Initialize the superclass (QtGui.QWidget)
        QtGui.QWidget.__init__(self)

        # Get prefs dict
        self.prefs = prefs

        # Load pilots db
        with open(self.prefs['PILOT_DB']) as pilot_file:
            self.pilots = json.load(pilot_file, object_pairs_hook=odict)

        # Declare attributes
        self.context = None
        self.loop    = None
        self.pusher = None
        self.listener  = None
        self.networking = None
        self.rows = None #handles to row writing functions
        self.networking_ok = False
        self.mice = {} # Dict of our open mouse objects
        self.current_mouse = None # ID of mouse currently in params panel

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

        # Spawn a thread to check the networks
        #self.check_network()

    def initUI(self):
        # Main panel layout
        self.panel_layout = QtGui.QHBoxLayout()
        #self.panel_layout.setContentsMargins(0,0,0,0)

        # Init panels and add to layout
        self.control_panel = Control_Panel(pilots = self.pilots,
                                           mice=self.mice,
                                           msg_fn=self.send_message)

        self.pilot_panel = Pilots()
        #self.pilots = self.pilot_panel.pilots
        #self.mice_panel = Mice()
        self.data_panel = Plot_Widget()
        self.data_panel.init_plots(self.pilots.keys())

        # Acquaint the panels
        #self.pilot_panel.give_mice_panel(self.mice_panel)
        #self.mice_panel.give_pilot_panel(self.pilot_panel)
        #self.mice_panel.give_param_trigger(self.show_params)

        self.panel_layout.addWidget(self.control_panel)
        #self.panel_layout.addWidget(self.mice_panel, stretch = 1)
        self.panel_layout.addWidget(self.data_panel, stretch=5)

        # add logo and new protocol button
        self.layout = QtGui.QVBoxLayout()
        self.layout.setContentsMargins(0,0,0,0)

        self.logo = QtGui.QLabel()
        #self.logo.setPixmap(QtGui.QPixmap(prefs['REPODIR']+'/graphics/logo.png').scaled(265,40))
        self.logo.setFixedHeight(40)
        self.logo.setAlignment(QtCore.Qt.AlignRight)

        self.new_protocol_button = QtGui.QPushButton("New Protocol")
        self.new_protocol_button.clicked.connect(self.new_protocol)
        self.new_protocol_button.setFixedHeight(40)

        self.connect_pilots_button = QtGui.QPushButton("Connect to Pilots")
        self.connect_pilots_button.clicked.connect(self.init_pilots)
        self.connect_pilots_button.setFixedHeight(40)

        #self.top_strip = QtGui.QHBoxLayout()
        #self.top_strip.addWidget(self.new_protocol_button)
        #self.top_strip.addWidget(self.connect_pilots_button)
        #self.top_strip.addStretch(1)
        #self.top_strip.addWidget(self.logo)

        # Get variables from the widgets



        #self.plot_container = QtGui.QFrame()
        #self.plot_container.setLayout(self.panel_layout)
        #self.plot_container.setContentsMargins(0,0,0,0)
        #self.layout.addLayout(self.top_strip)
        self.layout.addLayout(self.panel_layout)
        #self.layout.addStretch(1)
        #self.layout.addWidget(self.plot_container)

        self.setLayout(self.layout)
        #self.showMaximized()
        titleBarHeight = self.style().pixelMetric(QtGui.QStyle.PM_TitleBarHeight,
            QtGui.QStyleOptionTitleBar(), self)
        winsize = app.desktop().availableGeometry()
        # Then subtract height of titlebar
        winsize.setHeight(winsize.height()-titleBarHeight*4)
        self.setGeometry(winsize)

        self.show()
        logging.info('UI Initialized')

    def show_params(self, mouse_id):
        # Delete a param panel if one already exists
        if self.panel_layout.count() > 3:
            self.hide_params()

        self.current_mouse = mouse_id

        self.param_panel = Parameters()

        # Create Mouse object if we haven't already and load protocol
        if not mouse_id in self.mice.keys():
            self.mice[mouse_id] = Mouse(mouse_id)

        # Give methods/mouse object
        self.param_panel.give_mouse_object(self.mice[mouse_id])
        self.param_panel.give_close_function(self.hide_params)
        self.param_panel.give_startstop_function(self.mouse_start_toggled)

        if hasattr(self.mice[mouse_id], 'current'):
            self.param_panel.populate_params(self.mice[mouse_id].current,
                                             step=self.mice[mouse_id].step)
        else:
            # Mouse doesn't have a protocol, we pass the assign_protocol method
            self.param_panel.assign_protocol(self.mice_panel.assign_protocol)

        # Insert param panel
        self.panel_layout.insertWidget(2, self.param_panel, stretch=2)


    def hide_params(self):
        # If the current mouse isn't running, close its h5f file and delete the object
        try:
            if not self.mice[self.current_mouse].running:
                self.mice[self.current_mouse].close_h5f()
                del self.mice[self.current_mouse]
        except:
            # TODO Logging here
            pass

        # Set current mouse to None because we're closing the window anyway
        self.current_mouse = None

        self.panel_layout.removeWidget(self.param_panel)
        self.param_panel.deleteLater()
        self.setLayout(self.layout)

    def mouse_start_toggled(self, toggled):
        # Get object for current mouse
        mouse = self.mice[self.current_mouse]
        pilot = bytes(self.pilot_panel.pilot)

        # If toggled=True we are starting the mouse
        if toggled:
            # Set mouse to running
            mouse.prepare_run()
            # Get protocol and send it to the pi
            task = mouse.current[mouse.step]
            # Dress up the protocol dict with some extra values that the pilot needs
            task['mouse'] = mouse.name
            # TODO: Get last trial number and insert in dict
            self.send_message('START', pilot, task)
            # TODO: Spawn dataview widget
            # TODO: Spawn timer thread to trigger stop after run duration

        # Or else we are stopping the mouse
        else:
            mouse.running = False
            self.send_message('STOP', pilot)
            mouse.h5f.flush()
            # TODO: Destroy dataview widget



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
            'LISTENING': self.l_listening, # The networking object tells us it's online
            'PING' : self.l_ping, # Someone wants to know if we're alive
            'FILE' : self.l_file, # A pi needs some files to run its protocol
            'DATA' : self.l_data
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
            # TODO: maintain list of responsive pilots, only try to send 'start' to connected pilots
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
        # TODO: If we are stopping, we enter into a cohere state
        # TODO: If we are stopped, close the mouse object.
        # TODO: Also tell the relevant dataview to clear
        pass

    def l_data(self, value):
        # A Pi has sent us data, let's save it huh?
        mouse_name = value['mouse']
        self.mice[mouse_name].save_data(value)

    def l_listening(self, value):
        self.networking_ok = True
        self.logger.info('Networking responds as alive')

    def l_ping(self, value):
        self.send_message('ALIVE', value=b'T')

        # TODO: Give params window handle to mouse panel's update params function
        # TODO: Give params window handle to Terminal's delete params function

    def l_file(self, value):
        pass

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


class Expanding_Tabs(QtGui.QTabBar):
    # The expanding method of the QTabBar doesn't work,
    # we have to manually adjust the size policy and size hint
    def __init__(self, width=30):
        super(Expanding_Tabs, self).__init__()
        self.setSizePolicy(QtGui.QSizePolicy.Policy.Fixed, QtGui.QSizePolicy.Policy.Minimum)
        self.width = width

    def tabSizeHint(self, index):
        # Pretty janky, but the tab bar is two children deep from the main widget
        # First compute the size taken up by the 'new' button and the margin
        # We assume the code is unchanged that binds our width to that button's width
        #ctl_panel_handle = self.parent().parent()
        ctl_panel_handle = self.parent().parent()
        margins = ctl_panel_handle.layout.getContentsMargins()
        nudge_size = self.width + margins[1]*2 + margins[3]*2 +25+ ctl_panel_handle.layout.spacing() # top and bottom
        # TODO: MAKE THIS NON JANKY, THERE IS SOME EXTRA SPACE IN THE PADDING COME BACK WHEN SOBER N PATIENT
        return QtCore.QSize(self.width, (ctl_panel_handle.frameGeometry().height()-nudge_size)/self.count())


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
    app.setStyle('plastique') # Keeps some GTK errors at bay
    ex = Terminal(prefs=prefs)
    sys.exit(app.exec_())


