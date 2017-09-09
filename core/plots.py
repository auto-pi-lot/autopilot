# Classes for plots
import sys
from collections import deque as dq
import PySide
from PySide import QtGui
from PySide import QtCore
import pyqtgraph as pg
import zmq
from zmq.eventloop.ioloop import IOLoop
from zmq.eventloop.zmqstream import ZMQStream
import threading
pg.setConfigOptions(antialias=True)

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import tasks

############
# Plot list at the bottom!
###########
# TODO Have to have update methods happen with invoker
# TODO: Add data panel on the right for summary stats, n days run, task, step, etc.

class Plot_Widget(QtGui.QWidget):
    # Widget that frames multiple plots
    # TODO: Use pyqtgraph for this: http://www.pyqtgraph.org/
    # TODO: Spawn widget in own process, spawn each plot in own thread with subscriber and loop
    def __init__(self, prefs, invoker):
        QtGui.QWidget.__init__(self)

        # store prefs
        self.prefs = prefs

        # store invoker to give to children
        self.invoker = invoker

        # We should get passed a list of pilots to keep ourselves in order after initing
        self.pilots = None

        # Dict to store handles to plot windows by pilot
        self.plots = {}

        # Main Layout
        self.layout = QtGui.QVBoxLayout(self)
        self.layout.setContentsMargins(0,0,0,0)
        self.layout.setSpacing(0)

        # Containers to style backgrounds
        #self.container = QtGui.QFrame()
        #self.container.setObjectName("data_container")
        #self.container.setStyleSheet("#data_container {background-color:orange;}")

        # Plot Selection Buttons
        # TODO: Each plot bar should have an option panel, because different tasks have different plots
        self.plot_select = self.create_plot_buttons()

        # Create empty plot container
        self.plot_layout = QtGui.QVBoxLayout()
        #self.plot_layout.addStretch(1)
        #self.container.setLayout(self.plot_layout)

        # Assemble buttons and plots
        self.layout.addWidget(self.plot_select)
        self.layout.addLayout(self.plot_layout)
        self.setLayout(self.layout)

        # Set size policy to expand horizontally
        #self.setSizePolicy(QtGui.QSizePolicy.Expanding, QtGui.QSizePolicy.Expanding)

    def init_plots(self, pilot_list):
        self.pilots = pilot_list

        # Make a plot for each pilot.
        for p in self.pilots:
            plot = Plot(pilot=p, invoker=self.invoker,
                        subport=self.prefs['PUBPORT'])
            self.plot_layout.addWidget(plot)
            self.plots[p] = plot

    def create_plot_buttons(self):
        groupbox = QtGui.QGroupBox()
        groupbox.setFlat(False)
        groupbox.setFixedHeight(30)
        groupbox.setContentsMargins(0,0,0,0)
        #groupbox.setAlignment(QtCore.Qt.AlignBottom)

        # TODO: Make these each independent plotting classes, list and create boxes depending on a dict like all the others

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

    def start_plotting(self, value):
        # We're sent a task dict, we extract the plot params and send them to the plot object
        plot_params = tasks.TASK_LIST[value['task_type']].PLOT
        self.plots[value['pilot']].init_plots(plot_params)

class Plot(pg.PlotWidget):

    def __init__(self, pilot, invoker, subport, xrange=None):
        super(Plot, self).__init__()

        # The name of our pilot, used to listen for events
        self.pilot = pilot

        self.invoker = invoker

        # The port that the terminal networking object will send data from
        self.subport = subport

        # TODO: Put inside of update function, use a counter init'd with the first trial
        self.xrange = xrange or 50

        #self.setXRange(0, 50)
        self.getPlotItem().hideAxis('bottom')
        self.getPlotItem().hideAxis('left')
        self.setBackground(None)

        self.data = {} # Keep a dict of the data we are keeping track of, will be instantiated in init_plots

        # Start the listener, subscribes to terminal_networking that will broadcast data
        self.context = None
        self.subscriber = None
        self.loop = None
        self.init_listener()


    def init_plots(self, plots):
        # TODO Make this dependent on task plot params
        self.getPlotItem().addLine(y=0.5, pen=(255, 0, 0))

        self.addItem(Target())
        self.addItem(Response())
        pass

    def init_listener(self):
        self.context = zmq.Context.instance()
        self.loop = IOLoop.instance()
        # TODO START HERE 9/11/17
        pass

###################################
# Curve subclasses

class Target(pg.PlotDataItem):
    def __init__(self, winsize = 50, spot_color=(0,0,0), spot_size=5):
        #super(Targets, self).__init__(symbolBrush=symbolBrush, symbolPen=symbolPen, symbolSize=symbolSize, connect="pairs")
        super(Target, self).__init__()

        self.winsize=winsize


        self.spot_brush = pg.mkBrush(spot_color)
        self.spot_pen   = pg.mkPen(spot_color, width=spot_size)
        self.spot_size  = spot_size

        # Make a queue to hold values, double the size because we plot duplets of data
        # each couple has 0.5 and the value (0, 1) to use the 'connect' kwarg in setData
        self.spot_queue = dq(maxlen=self.winsize)

        self.spot_queue.extend([1,0,1,0,1])
        self.update(0)

    def update(self, y):
        #TODO: Change this to replace .setData and then just .setData with the y series from Plot()
        # Y should be an int 0 or 1 for right/left, but just to be sure...
        if y > 0.5:
            y = 1.
        else:
            y = 0.

        self.spot_queue.append(y)

        spot_xs = range(self.winsize-len(self.spot_queue)+1, self.winsize+1)

        self.scatter.setData(x=spot_xs, y=list(self.spot_queue), size=self.spot_size,
                             brush=self.spot_brush, symbol='o', pen=self.spot_pen)

    def change_window(self, winsize):
        self.winsize = winsize
        new_queue = dq(maxlen=self.winsize*2)
        new_queue.extend(self.queue)
        self.queue = new_queue

class Response(pg.PlotDataItem):
    def __init__(self, winsize=50, spot_color=(0, 0, 0), spot_size=5):
        # super(Targets, self).__init__(symbolBrush=symbolBrush, symbolPen=symbolPen, symbolSize=symbolSize, connect="pairs")
        super(Response, self).__init__()

        self.winsize = winsize

        self.spot_brush = pg.mkBrush(spot_color)
        self.spot_pen = pg.mkPen(spot_color, width=spot_size)
        self.spot_size = spot_size

        # Make a queue to hold values, double the size because we plot duplets of data
        # each couple has 0.5 and the value (0, 1) to use the 'connect' kwarg in setData
        self.line_queue = dq(maxlen=self.winsize * 2)

        self.line_queue.extend([0.5, 1, 0.5, 0, 0.5, 1, 0.5, 1])
        self.update(None)

    def update(self, y=None):
        # TODO: Change this to replace .setData and then just .setData with the y series from Plot()
        # TODO: X-axis shifting is probably better done by changing the XRange in the Plot window, that also lets us append x in a less awkward way
        # Y should be an int 0 or 1 for right/left, but just to be sure...
        if not y:
            line_xs = [i for i in range((self.winsize - len(self.line_queue) / 2), self.winsize) for _ in
                       range(2)]
        else:
            self.line_queue.extend([0.5, y])
            line_xs = [i for i in range((self.winsize - len(self.line_queue) / 2) + 1, self.winsize + 1) for _ in range(2)]

        self.curve.setData(line_xs, list(self.line_queue), connect='pairs', pen='k')

    def change_window(self, winsize):
        self.winsize = winsize
        new_queue = dq(maxlen=self.winsize * 2)
        new_queue.extend(self.queue)
        self.queue = new_queue

class Correct_Roll():
    pass

class Bail():
    pass


PLOT_LIST = {
    'target':Target,
    'response':Response,
    'correct_roll':Correct_Roll,
    'bail':Bail
}


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
