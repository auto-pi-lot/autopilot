# The terminal is the user-facing GUI that controls the Pis

__version__ = '0.1'
__author__  = 'Jonny Saunders <JLSaunders987@gmail.com'

import argparse
import json
import sys
import os
from collections import OrderedDict as odict
from PySide import QtCore
from PySide import QtGui

from mouse import Mouse


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
        print(self.pilot_window.result())
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

    def create_buttons(self, mice):
        # Create the buttons for each mouse that a pilot owns
        self.clear_buttons()
        self.mice = mice
        self.buttons = {}
        for m in mice:
            self.buttons[m] = QtGui.QPushButton(str(m))
            self.buttons[m].setCheckable(True)
            self.button_group.addButton(self.buttons[m])
            self.button_layout.addWidget(self.buttons[m])

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

    class New_Mouse_Wizard(QtGui.QDialog):
        def __init__(self):

    def create_mouse(self):
        text, ok = QtGui.QInputDialog.getText(self, "Input Mouse ID", "Mouse ID:")
        if ok:
            self.mice.append(text)
            self.create_buttons(self.mice)
            self.pilot_panel.update_db()

    def select_mouse(self):
        pass

    def give_pilot_panel(self, pilot_panel):
        self.pilot_panel = pilot_panel

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

        # add logo
        self.layout = QtGui.QVBoxLayout()
        self.layout.setContentsMargins(5,5,5,5)
        self.logo = QtGui.QLabel()
        print(prefs['REPODIR']+'/graphics/logo.png')
        self.logo.setPixmap(QtGui.QPixmap(prefs['REPODIR']+'/graphics/logo.png').scaled(265,40))
        self.logo.setFixedHeight(40)
        self.logo.setAlignment(QtCore.Qt.AlignRight)

        self.plot_container = QtGui.QFrame()
        self.plot_container.setLayout(self.panel_layout)
        self.plot_container.setContentsMargins(0,0,0,0)
        self.layout.addWidget(self.logo)
        self.layout.addWidget(self.plot_container)

        self.setLayout(self.layout)
        self.show()


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


