# The terminal is the user-facing GUI that controls the Pis

__version__ = '0.1'
__author__  = 'Jonny Saunders <JLSaunders987@gmail.com'

import argparse
import json
import sys
from PySide import QtCore
from PySide import QtGui

# Parse arguments - this should have been called with a .json prefs file passed
# parser = argparse.ArgumentParser(description="Run an RPilot Terminal")
# parser.add_argument('-p', '--prefs', help="Location of .json prefs file (created during setup_terminal.py)")
# args = parser.parse_args()

#if not args.prefs:
#   raise Exception('Need to path a .json prefs file with -p')
#with open(args.prefs) as prefs_file:
#   prefs = json.load(prefs_file)

# http://zetcode.com/gui/pysidetutorial/layoutmanagement/
# https://wiki.qt.io/PySide_Tutorials

class Parameters(QtGui.QFormLayout):
    '''
    Read task parameters from mouse protocol, populate with buttons, etc.
    '''
    def __init__(self):
        QtGui.QFormLayout.__init__(self)

        self.addRow(QtGui.QLabel("Reward (ms)"), QtGui.QLineEdit("50"))
        self.addRow(QtGui.QLabel("Runtime (min)"), QtGui.QLineEdit("60"))



class Pilots(QtGui.QWidget):
    '''
    Widget container for all our pilots
    '''
    def __init__(self):
        QtGui.QWidget.__init__(self)

        # main layout
        self.layout = QtGui.QHBoxLayout(self)

       


        # Make containers to style backgrounds
        self.pilot_container = QtGui.QFrame()
        self.mouse_container = QtGui.QFrame()
        self.param_container = QtGui.QFrame()
        self.pilot_container.setObjectName("pilot_container")
        self.mouse_container.setObjectName("mouse_container")
        self.param_container.setObjectName("param_container")
        self.pilot_container.setStyleSheet("#pilot_container {background-color:blue;}")
        self.mouse_container.setStyleSheet("#mouse_container {background-color:green;}")
        self.param_container.setStyleSheet("#param_container {background-color:pink;}")

        # Create vertical layouts to hold buttons
        self.pilot_layout = QtGui.QVBoxLayout()
        self.mouse_layout = QtGui.QVBoxLayout()
        self.parameter_frame = Parameters()

        self.pilot_container.setLayout(self.pilot_layout)
        self.mouse_container.setLayout(self.mouse_layout)
        self.param_container.setLayout(self.parameter_frame)

        # Get dict of pilots
        # Dummy for now
        self.pilots = {0:{"ip":12345,"mice":[1000,2000,3000,4000]},
                       1:{"ip":12345,"mice":[1000,2000,3000,4000]}}

        self.create_pilot_buttons()
        self.create_mouse_buttons(0)

        # Nest them in an hbox
        
        
        self.layout.addWidget(self.pilot_container, stretch=1)
        self.layout.addWidget(self.mouse_container, stretch=2)
        self.layout.addWidget(self.param_container, stretch=2)

        self.setLayout(self.layout)
        self.show()

        # Create buttons for mice

    def create_pilot_buttons(self):
        self.pilot_buttons = []
        for p in self.pilots.keys():
            self.pilot_buttons.append(QtGui.QPushButton(str(p)))
            self.pilot_layout.addWidget(self.pilot_buttons[-1])

        # Make an add pilot button
        self.add_pilot_button = QtGui.QPushButton("+")
        self.pilot_layout.addWidget(self.add_pilot_button)
        self.pilot_layout.addStretch(1)


    def create_mouse_buttons(self, pilot_ind):
        # Create the buttons for each mouse that a pilot owns
        self.clear_layout(self.mouse_layout)

        self.mouse_buttons = []
        for m in self.pilots[pilot_ind]['mice']:
            self.mouse_buttons.append(QtGui.QPushButton(str(m)))
            self.mouse_layout.addWidget(self.mouse_buttons[-1])

        self.mouse_layout.addStretch(1)

    def clear_layout(self, layout):
        while layout.count():
            child = layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()




    def create_pilot(self):
        # When create_pilot button is pressed...
        pass

class DataView(QtGui.QFrame):
    def __init__(self):
        QtGui.QFrame.__init__(self)
        #Temporary frame for demo...
        self.setObjectName("dataview")
        self.setStyleSheet("#dataview {background-color:orange;}")



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
        # Init widgets
        self.pilot_widget = Pilots()
        self.dataview = DataView()




        h_layout = QtGui.QHBoxLayout()
        h_layout.addWidget(self.pilot_widget, stretch=1)
        h_layout.addWidget(self.dataview, stretch=2)

        self.setLayout(h_layout)
        self.show()


if __name__ == '__main__':
    app = QtGui.QApplication(sys.argv)
    ex = Terminal()
    sys.exit(app.exec_())


