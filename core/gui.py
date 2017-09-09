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
                # Try finding prefs in the encapsulating namespaces
                with open(prefs['PILOT_DB']) as pilot_file:
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
        self.layout.setSpacing(0)
        self.setLayout(self.layout)

        # Make top row 'new' buttons
        new_button_panel = QtGui.QHBoxLayout()
        new_button_panel.setContentsMargins(0,0,0,0)
        new_button_panel.setSpacing(0)
        self.new_pilot_button = QtGui.QPushButton('+')
        self.new_pilot_button.setContentsMargins(0,0,0,0)
        self.new_pilot_button.setFixedSize(self.pilot_width, self.pilot_width)
        self.new_pilot_button.clicked.connect(self.create_pilot)
        self.new_mouse_button = QtGui.QPushButton('+')
        self.new_mouse_button.setContentsMargins(0,0,0,0)
        self.new_mouse_button.setFixedSize(self.mouse_width, self.pilot_width)
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
        self.pilot_tabs.setSizePolicy(QtGui.QSizePolicy.Fixed, QtGui.QSizePolicy.Expanding)
        self.pilot_tabs.setUsesScrollButtons(False)
        self.pilot_tabs.setTabPosition(QtGui.QTabWidget.West)
        self.pilot_tabs.currentChanged.connect(self.select_pilot)

        self.layout.addWidget(self.pilot_tabs, stretch=1)

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
            mice_tabs.setContentsMargins(0,0,0,0)
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
        #self.pilot_tabs.setSizePolicy(QtGui.QSizePolicy.Fixed, QtGui.QSizePolicy.Maximum)


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
                    protocol_file = os.path.join(self.prefs['PROTOCOLDIR'], protocol_vals['protocol'] + '.json')
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
        #self.pilot_tabs.setSizePolicy(QtGui.QSizePolicy.Expanding, QtGui.QSizePolicy.Expanding)

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
            with open(self.prefs['PILOT_DB'], 'w') as pilot_file:
                json.dump(self.pilots, pilot_file)
        except NameError:
            try:
                with open('/usr/rpilot/pilot_db.json', 'w') as pilot_file:
                    json.dump(self.pilots, pilot_file)
            except IOError:
                Exception('Couldnt update pilot db!')
                # TODO: Probably just pop a dialog, don't need to crash shit.

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
        self.layout.setSizeConstraint(QtGui.QLayout.SetFixedSize)
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

            # Prep task to send to pi, the pilot needs to know the mouse
            task = self.protocol[self.step]
            task['mouse'] = self.mouse.name
            task['pilot'] = self.pilot

            # TODO: Get last trial number and send to pi as well
            self.send_message('START', bytes(self.pilot), task)

        else:
            # Send message to pilot to stop running,
            # it should initiate a coherence checking routine to make sure
            # its data matches what the Terminal got,
            # so the terminal will handle closing the mouse object
            self.send_message('STOP', bytes(self.pilot))

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
