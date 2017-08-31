# Classes for plots
from PySide import QtGui
from PySide import QtCore
import pyqtgraph as pg


class Plot_Widget(QtGui.QWidget):
    # Widget that frames multiple plots
    # TODO: Use pyqtgraph for this: http://www.pyqtgraph.org/
    # TODO: Spawn widget in own process, spawn each plot in own thread with subscriber and loop
    def __init__(self):
        QtGui.QWidget.__init__(self)

        # We should get passed an odict of pilots to keep ourselves in order after initing
        self.pilots = None

        # Dict to store handles to plot windows by mouse
        self.plots = {}

        # Main Layout
        self.layout = QtGui.QVBoxLayout(self)

        # Containers to style backgrounds
        self.container = QtGui.QFrame()
        self.container.setObjectName("data_container")
        self.container.setStyleSheet("#data_container {background-color:orange;}")

        # Plot Selection Buttons
        self.plot_select = self.create_plot_buttons()

        # Create empty plots
        self.plot_layout = QtGui.QVBoxLayout()
        #self.plot_layout.addStretch(1)
        #self.container.setLayout(self.plot_layout)

        # Assemble buttons and plots
        self.layout.addWidget(self.plot_select)
        self.layout.addLayout(self.plot_layout)
        self.setLayout(self.layout)


        #self.show()

    def init_plots(self, pilot_list):
        self.pilots = pilot_list

        # Make a plot for each pilot.

        for p in self.pilots:
            # three columns, pilot label, mouse label, plot
            p_label = QtGui.QLabel(p)
            p_label.setFixedWidth(50)
            m_label = QtGui.QLabel()
            plot = pg.PlotWidget()

            # Make row
            hlayout = QtGui.QHBoxLayout()
            hlayout.addWidget(p_label)
            hlayout.addWidget(m_label)
            hlayout.addWidget(plot)

            self.plot_layout.addLayout(hlayout)

    def create_plots(self):
        vlayout = QtGui.QVBoxLayout()

        return vlayout





    def create_plot_buttons(self):
        groupbox = QtGui.QGroupBox()
        groupbox.setFlat(True)
        groupbox.setFixedHeight(30)
        groupbox.setContentsMargins(0,0,0,0)
        #groupbox.setAlignment(QtCore.Qt.AlignBottom)

        check1 = QtGui.QCheckBox("Targets")
        check1.setChecked(True)
        check2 = QtGui.QCheckBox("Responses")
        check2.setChecked(True)
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

class VLabel(QtGui.QWidget):
    # Vertically oriented label
    # https://stackoverflow.com/questions/34080798/pyqt-draw-a-vertical-label
    def __init__(self, text=None):
        super(VLabel, self).__init__()
        self.text = text

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setPen(QtCore.Qt.black)
        painter.rotate(-90)
        if self.text:
            painter.drawText(0,0, self.text)
        painter.end()

    def setText(self, newText):
        self.text = newText
