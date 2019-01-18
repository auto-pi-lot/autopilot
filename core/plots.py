# Classes for plots
import sys
import json
import logging
import os
from collections import deque as dq
import numpy as np
import PySide
import pandas as pd
from PySide import QtGui
from PySide import QtCore
import pyqtgraph as pg
import zmq
from zmq.eventloop.ioloop import IOLoop
from zmq.eventloop.zmqstream import ZMQStream
import threading
from time import time
from itertools import count
import functools
pg.setConfigOptions(antialias=True)

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import tasks
from utils import InvokeEvent, Invoker
from core.networking import Net_Node
import prefs

############
# Plot list at the bottom!
###########

def gui_event(fn):
    def wrapper_gui_event(*args, **kwargs):
        QtCore.QCoreApplication.postEvent(prefs.INVOKER, InvokeEvent(fn, *args, **kwargs))
    return wrapper_gui_event

class Plot_Widget(QtGui.QWidget):
    # Widget that frames multiple plots
    def __init__(self, invoker):
        QtGui.QWidget.__init__(self)

        self.logger = logging.getLogger('main')

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

        self.setContentsMargins(0, 0, 0, 0)

    def init_plots(self, pilot_list):
        self.pilots = pilot_list

        # Make a plot for each pilot.
        for p in self.pilots:
            plot = Plot(pilot=p, invoker=self.invoker,
                        subport=prefs.PUBPORT,
                        msgport=prefs.MSGPORT)
            self.plot_layout.addWidget(plot)
            self.plot_layout.addWidget(HLine())
            self.plots[p] = plot

    def create_plot_buttons(self):
        groupbox = QtGui.QGroupBox()
        groupbox.setFlat(False)
        groupbox.setFixedHeight(40)
        groupbox.setContentsMargins(0,0,0,0)
        #groupbox.setAlignment(QtCore.Qt.AlignBottom)

        # TODO: Actually make these hooked up to something...
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


class Plot(QtGui.QWidget):

    def __init__(self, pilot, invoker, x_width=50):
        super(Plot, self).__init__()

        self.logger = logging.getLogger('main')

        self.layout = QtGui.QHBoxLayout()
        self.setLayout(self.layout)

        # The name of our pilot, used to listen for events
        self.pilot = pilot

        self.invoker = invoker

        # A little infobox to keep track of running time, trials, etc.
        self.infobox = QtGui.QFormLayout()
        self.n_trials = count()
        self.session_trials = 0
        self.info = {
            'N Trials': QtGui.QLabel(),
            'Runtime' : Timer(),
            'Session' : QtGui.QLabel(),
            'Protocol': QtGui.QLabel(),
            'Step'    : QtGui.QLabel()
        }
        for k, v in self.info.items():
            self.infobox.addRow(k, v)

        self.layout.addLayout(self.infobox, 1)

        # The plot that we own :)
        self.plot = pg.PlotWidget()
        self.layout.addWidget(self.plot, 8)

        # Set initial x-value, will update when data starts coming in
        self.x_width = x_width
        self.last_trial = self.x_width
        self.xrange = xrange(self.last_trial-self.x_width+1, self.last_trial+1)
        self.plot.setXRange(self.xrange[0], self.xrange[-1])

        # Inits the basic widget settings
        self.init_plots

        self.plot_params = {}
        self.data = {} # Keep a dict of the data we are keeping track of, will be instantiated on start
        self.plots = {}

        ## Networking
        # Start the listener, subscribes to terminal_networking that will broadcast data
        self.listens = {
            'START' : self.l_start, # Receiving a new task
            'DATA' : self.l_data, # Receiving a new datapoint
            'STOP' : self.l_stop,
            'PARAM': self.l_param # changing some param
        }

        self.msgport = prefs.MSGPORT
        self.node = Net_Node(id='P_{}'.format(self.pilot),
                             upstream="T",
                             port=self.msgport,
                             listens=self.listens,
                             instance=True)


    @gui_event
    def init_plots(self):
        # This is called to make the basic plot window,
        # each task started should then send us params to populate afterwards
        #self.getPlotItem().hideAxis('bottom')
        self.plot.getPlotItem().hideAxis('left')
        self.plot.setBackground(None)
        self.plot.setXRange(self.xrange[0], self.xrange[1])
        self.plot.setYRange(0, 1)

    @gui_event
    def l_start(self, value):
        # We're sent a task dict, we extract the plot params and send them to the plot object
        self.plot_params = tasks.TASK_LIST[value['task_type']].PLOT

        # set infobox stuff
        self.n_trials = count()
        self.session_trials = 0
        self.info['N Trials'].setText(str(value['current_trial']))
        self.info['Runtime'].start_timer()
        self.info['Step'].setText(str(value['step']))
        self.info['Session'].setText(str(value['session']))
        self.info['Protocol'].setText(value['step_name'])


        # TODO: Make this more general, make cases for each non-'data' key
        try:
            if self.plot_params['chance_bar']:
                self.plot.getPlotItem().addLine(y=0.5, pen=(255,0,0))
        except KeyError:
            # No big deal, chance bar wasn't set
            pass

        # Make plot items for each data type
        for data, plot in self.plot_params['data'].items():
            # TODO: Better way of doing params for plots, might just have to suck it up and make dict another level
            if plot == 'rollmean' and 'roll_window' in self.plot_params.keys():
                self.plots[data] = Roll_Mean(winsize=self.plot_params['roll_window'])
                self.plot.addItem(self.plots[data])
                self.data[data] = np.zeros((0,2), dtype=np.float)
            else:
                self.plots[data] = PLOT_LIST[plot]()
                self.plot.addItem(self.plots[data])
                self.data[data] = np.zeros((0,2), dtype=np.float)

    @gui_event
    def l_data(self, value):
        if 'trial_num' in value.keys():
            v = value.pop('trial_num')
            if v != self.last_trial:
                self.session_trials = self.n_trials.next()
            self.last_trial = v
            # self.last_trial = v
            self.info['N Trials'].setText("{}/{}".format(self.session_trials, v))
            self.xrange = xrange(v - self.x_width + 1, v + 1)
            self.plot.setXRange(self.xrange[0], self.xrange[-1])

        for k, v in value.items():
            if k in self.data.keys():
                self.data[k] = np.vstack((self.data[k], (self.last_trial, v)))
                #self.gui_event(self.plots[k].update, *(self.data[k],))
                self.plots[k].update(self.data[k])

    @gui_event
    def l_stop(self, value):
        self.data = {}
        self.plots = {}
        self.plot.clear()
        try:
            if isinstance(value, str) or ('graduation' not in value.keys()):
                self.info['Runtime'].stop_timer()
        except:
            self.info['Runtime'].stop_timer()

        self.info['N Trials'].setText('')
        self.info['Step'].setText('')
        self.info['Session'].setText('')
        self.info['Protocol'].setText('')

    def l_param(self, value):
        pass
    #
    # def gui_event(self, fn):
    #     # Don't ask me how this works, stolen from
    #     # https://stackoverflow.com/a/12127115
    #     # turn it into a decorator so we can use Net_Node's handling function
    #     QtCore.QCoreApplication.postEvent(self.invoker, InvokeEvent(fn, *args, **kwargs))





###################################
# Curve subclasses
class Point(pg.PlotDataItem):
    def __init__(self, color=(0,0,0), size=5):
        super(Point, self).__init__()

        self.brush = pg.mkBrush(color)
        self.pen   = pg.mkPen(color, width=size)
        self.size  = size

    def update(self, data):
        # data should come in as an n x 2 array,
        # 0th column - trial number (x), 1st - (y) value

        data[data=="R"] = 1
        data[data=="C"] = 0.5
        data[data=="L"] = 0
        data = data.astype(np.float)

        self.scatter.setData(x=data[...,0], y=data[...,1], size=self.size,
                             brush=self.brush, symbol='o', pen=self.pen)


class Segment(pg.PlotDataItem):
    def __init__(self):
        super(Segment, self).__init__()

    def update(self, data):
        # data should come in as an n x 2 array,
        # 0th column - trial number (x), 1st - (y) value
        data[data=="R"] = 1
        data[data=="L"] = 0
        data[data=="C"] = 0.5
        data = data.astype(np.float)

        xs = np.repeat(data[...,0],2)
        ys = np.repeat(data[...,1],2)
        ys[::2] = 0.5

        self.curve.setData(xs, ys, connect='pairs', pen='k')


class Roll_Mean(pg.PlotDataItem):
    def __init__(self, winsize=10):
        super(Roll_Mean, self).__init__()

        self.winsize = winsize

        self.setFillLevel(0.5)

        self.series = pd.Series()

        self.brush = pg.mkBrush((0,0,0,100))
        self.setBrush(self.brush)


    def update(self, data):
        # data should come in as an n x 2 array,
        # 0th column - trial number (x), 1st - (y) value
        data = data.astype(np.float)

        self.series = pd.Series(data[...,1])
        ys = self.series.rolling(self.winsize, min_periods=0).mean().as_matrix()

        #print(ys)

        self.curve.setData(data[...,0], ys, fillLevel=0.5)


class Timer(QtGui.QLabel):
    def __init__(self):
        super(Timer, self).__init__()

        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self.update_time)

        self.start_time = None

    def start_timer(self, update_interval=1000):
        self.start_time = time()
        self.timer.start(update_interval)

    def stop_timer(self):
        self.timer.stop()
        self.setText("")

    def update_time(self):
        secs_elapsed = int(np.floor(time()-self.start_time))
        self.setText("{:02d}:{:02d}:{:02d}".format(secs_elapsed/3600, (secs_elapsed/60)%60, secs_elapsed%60))


class Highlight():
    # TODO Implement me
    pass


class HLine(QtGui.QFrame):
    def __init__(self):
        super(HLine, self).__init__()
        self.setFrameShape(QtGui.QFrame.HLine)
        self.setFrameShadow(QtGui.QFrame.Sunken)

PLOT_LIST = {
    'point':Point,
    'segment':Segment,
    'rollmean':Roll_Mean,
    'highlight':Highlight
}