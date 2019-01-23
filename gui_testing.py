import sys
import os
import json
import copy
from collections import OrderedDict as odict
from PySide import QtCore
from PySide import QtGui
sys.path.append('/home/jonny/git/RPilot')
from rpilot.core import New_Mouse_Wizard, Sound_Widget
from rpilot.core.mouse import Mouse
from rpilot import tasks


class Control_Panel(QtGui.QWidget):
    # Hosts two nested tab widgets to select pilot and mouse,
    # set params, run mice, etc.

    def __init__(self, pilots=None, mice=None, msg_fn=None, pilot_width=30, mouse_width=150, prefs=None):
        """
        Args:
            pilots:
            mice:
            msg_fn:
            pilot_width:
            mouse_width:
            prefs:
        """
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
        """
        Args:
            new_mouse:
        """
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
        """
        Args:
            index:
        """
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
                json.dump(self.pilots, pilot_file, indent=4, separators=(',', ': '), sort_keys=True)
        except NameError:
            try:
                with open('/usr/rpilot/pilot_db.json', 'w') as pilot_file:
                    json.dump(self.pilots, pilot_file, indent=4, separators=(',', ': '), sort_keys=True)
            except IOError:
                Exception('Couldnt update pilot db!')
                # TODO: Probably just pop a dialog, don't need to crash shit.



class Parameters(QtGui.QWidget):
    # Reads and edits tasks parameters from a mouse's protocol
    def __init__(self, pilot, msg_fn, hide_fn):
        """
        Args:
            pilot:
            msg_fn:
            hide_fn:
        """
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
        """
        Args:
            mouse_obj:
        """
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
        """
        Args:
            protocol:
            step:
        """
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
        """
        Args:
            layout:
        """
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
        """
        Args:
            toggled:
        """
        # TODO: Why does this object have toggle_start...
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










                        # Add corner widget to declare new pilot
        #self.new_pilot_button = QtGui.QPushButton('+')
        #self.new_pilot_button.setFixedHeight(30)
        #self.pilot_tabs.setCornerWidget(self.new_pilot_button, QtCore.Qt.BottomLeftCorner)



# def expanding_tabs:
#     tabs = QtGui.QTabBar()
#     tabs.setExpanding(True)
#     layout = QtGui.QVBoxLayout()
#         self.setLayout(layout)
#         stackedLayout = QtGui.QStackedLayout()
#         layout.addWidget(self)
#         layout.addLayout(stackedLayout)

class Expanding_Tabs(QtGui.QTabBar):
    # The expanding method of the QTabBar doesn't work,
    # we have to manually adjust the size policy and size hint
    def __init__(self, width=30):
        """
        Args:
            width:
        """
        super(Expanding_Tabs, self).__init__()
        self.setSizePolicy(QtGui.QSizePolicy.Policy.Fixed, QtGui.QSizePolicy.Policy.Minimum)
        self.width = width

    def tabSizeHint(self, index):
        """
        Args:
            index:
        """
        # Pretty janky, but the tab bar is two children deep from the main widget
        # First compute the size taken up by the 'new' button and the margin
        # We assume the code is unchanged that binds our width to that button's width
        ctl_panel_handle = self.parent().parent()
        margins = ctl_panel_handle.layout.getContentsMargins()
        nudge_size = self.width + margins[1] + margins[3] + ctl_panel_handle.layout.spacing() # top and bottom
        return QtCore.QSize(self.width, (ctl_panel_handle.frameGeometry().height()-nudge_size)/self.count())


class Stacked_Tabs(QtGui.QTabBar):
    # Setting tab position to west also rotates text 90 degrees, which is dumb
    # From https://stackoverflow.com/questions/3607709/how-to-change-text-alignment-in-qtabwidget
    def __init__(self, width=150, height=30):
        """
        Args:
            width:
            height:
        """
        super(Stacked_Tabs, self).__init__()
        self.tabSize = QtCore.QSize(width, height)

    def paintEvent(self, event):
        """
        Args:
            event:
        """
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
        """
        Args:
            index:
        """
        return self.tabSize


class Test_App(QtGui.QWidget):
    def __init__(self, prefs):
        """
        Args:
            prefs:
        """
        super(Test_App, self).__init__()
        self.prefs = prefs
        self.initUI()

    def initUI(self):
        #self.setWindowState(QtCore.Qt.WindowMaximized)
        self.layout = QtGui.QHBoxLayout()
        self.setLayout(self.layout)
        mice = {}
        self.panel = Control_Panel(prefs=self.prefs, mice=mice, msg_fn=self.blank_fn)
        self.layout.addWidget(self.panel)
        self.layout.addStretch(1)
        titleBarHeight = self.style().pixelMetric(QtGui.QStyle.PM_TitleBarHeight,
            QtGui.QStyleOptionTitleBar(), self)
        winsize = app.desktop().availableGeometry()
        # Then subtract height of titlebar
        winsize.setHeight(winsize.height()-titleBarHeight*2)
        self.setGeometry(winsize)

        #self.show()
    def blank_fn(self):
        pass




if __name__ == '__main__':
    prefs_file = '/usr/rpilot/prefs.json'
    with open(prefs_file) as prefs_file_open:
        prefs = json.load(prefs_file_open)

    app = QtGui.QApplication(sys.argv)
    app.setStyle('Cleanlooks')
    ex = Test_App(prefs)
    ex.show()
    sys.exit(app.exec_())





