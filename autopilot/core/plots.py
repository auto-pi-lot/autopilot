"""
Classes to plot data in the GUI.

.. todo::

    Add all possible plot objects and options in list.

Note:
    Plot objects need to be added to :data:`~.plots.PLOT_LIST` in order to be reachable.


"""

# Classes for plots
import sys
import logging
import os
import numpy as np
import PySide # have to import to tell pyqtgraph to use it
import pandas as pd
from PySide import QtGui
from PySide import QtCore
import pyqtgraph as pg
from time import time
from itertools import count
from functools import wraps
from Queue import Queue, Empty
pg.setConfigOptions(antialias=True)

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from autopilot import tasks, prefs
from autopilot.core import styles
from utils import InvokeEvent, Invoker
from autopilot.core.networking import Net_Node


############
# Plot list at the bottom!
###########

def gui_event(fn):
    """
    Wrapper/decorator around an event that posts GUI events back to the main
    thread that our window is running in.

    Args:
        fn (callable): a function that does something to the GUI
    """
    @wraps(fn)
    def wrapper_gui_event(*args, **kwargs):
        # type: (object, object) -> None
        """

        Args:
            *args (): 
            **kwargs (): 
        """
        QtCore.QCoreApplication.postEvent(prefs.INVOKER, InvokeEvent(fn, *args, **kwargs))
    return wrapper_gui_event


class Plot_Widget(QtGui.QWidget):
    """
    Main plot widget that holds plots for all pilots

    Essentially just a container to give plots a layout and handle any
    logic that should apply to all plots.

    Attributes:
        logger (`logging.Logger`): The 'main' logger
        plots (dict): mapping from pilot name to :class:`.Plot`
    """
    # Widget that frames multiple plots
    def __init__(self):
        # type: () -> None
        QtGui.QWidget.__init__(self)

        self.logger = logging.getLogger('main')


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
        #self.plot_select = self.create_plot_buttons()

        # Create empty plot container
        self.plot_layout = QtGui.QVBoxLayout()

        # Assemble buttons and plots
        #self.layout.addWidget(self.plot_select)
        self.layout.addLayout(self.plot_layout)

        self.setLayout(self.layout)

        self.setContentsMargins(0, 0, 0, 0)

    def init_plots(self, pilot_list):
        """
        For each pilot, instantiate a :class:`.Plot` and add to layout.

        Args:
            pilot_list (list): the keys from :attr:`.Terminal.pilots`
        """
        self.pilots = pilot_list

        # Make a plot for each pilot.
        for p in self.pilots:
            plot = Plot(pilot=p)
            self.plot_layout.addWidget(plot)
            self.plot_layout.addWidget(HLine())
            self.plots[p] = plot


class Plot(QtGui.QWidget):
    """
    Widget that hosts a :class:`pyqtgraph.PlotWidget` and manages
    graphical objects for one pilot depending on the task.

    **listens**

    +-------------+------------------------+-------------------------+
    | Key         | Method                 | Description             |
    +=============+========================+=========================+
    | **'START'** | :meth:`~.Plot.l_start` | starting a new task     |
    +-------------+------------------------+-------------------------+
    | **'DATA'**  | :meth:`~.Plot.l_data`  | getting a new datapoint |
    +-------------+------------------------+-------------------------+
    | **'STOP'**  | :meth:`~.Plot.l_stop`  | stop the task           |
    +-------------+------------------------+-------------------------+
    | **'PARAM'** | :meth:`~.Plot.l_param` | change some parameter   |
    +-------------+------------------------+-------------------------+

    **Plot Parameters**

    The plot is built from the ``PLOT={data:plot_element}`` mappings described in the :class:`~autopilot.tasks.task.Task` class.
    Additional parameters can be specified in the ``PLOT`` dictionary. Currently:

    * **continuous** (bool): whether the data should be plotted against the trial number (False or NA) or against time (True)
    * **chance_bar** (bool): Whether to draw a red horizontal line at chance level (default: 0.5)
    * **chance_level** (float): The position in the y-axis at which the ``chance_bar`` should be drawn
    * **roll_window** (int): The number of trials :class:`~.Roll_Mean` take the average over.

    Attributes:
        pilot (str): The name of our pilot, used to set the identity of our socket, specifically::

            'P_{pilot}'

        infobox (:class:`QtGui.QFormLayout`): Box to plot basic task information like trial number, etc.
        info (dict): Widgets in infobox:

            * 'N Trials': :class:`QtGui.QLabel`,
            * 'Runtime' : :class:`.Timer`,
            * 'Session' : :class:`QtGui.QLabel`,
            * 'Protocol': :class:`QtGui.QLabel`,
            * 'Step'    : :class:`QtGui.QLabel`

        plot (:class:`pyqtgraph.PlotWidget`): The widget where we draw our plots
        plot_params (dict): A dictionary of plot parameters we receive from the Task class
        data (dict): A dictionary of the data we've received
        plots (dict): The collection of plots we instantiate based on `plot_params`
        node (:class:`.Net_Node`): Our local net node where we listen for data.
        state (str): state of the pilot, used to keep plot synchronized.
    """

    def __init__(self, pilot, x_width=50):
        """
        Args:
            pilot (str): The name of our pilot
            x_width (int): How many trials in the past should we plot?
        """
        super(Plot, self).__init__()

        self.logger = logging.getLogger('main')

        self.layout = None
        self.infobox = None
        self.n_trials = None
        self.session_trials = 0
        self.info = {}
        self.plot = None
        self.xrange = None
        self.plot_params = {}
        self.data = {} # Keep a dict of the data we are keeping track of, will be instantiated on start
        self.plots = {}
        self.state = "IDLE"
        self.continuous = False
        self.last_time = 0

        self.invoker = prefs.INVOKER

        # The name of our pilot, used to listen for events
        self.pilot = pilot

        # Set initial x-value, will update when data starts coming in
        self.x_width = x_width
        self.last_trial = self.x_width

        # Inits the basic widget settings
        self.init_plots()

        ## Station
        # Start the listener, subscribes to terminal_networking that will broadcast data
        self.listens = {
            'START' : self.l_start, # Receiving a new task
            'DATA' : self.l_data, # Receiving a new datapoint
            'STOP' : self.l_stop,
            'PARAM': self.l_param, # changing some param
            'STATE': self.l_state
        }

        self.node = Net_Node(id='P_{}'.format(self.pilot),
                             upstream="T",
                             port=prefs.MSGPORT,
                             listens=self.listens,
                             instance=True)


    @gui_event
    def init_plots(self):
        """
        Make pre-task GUI objects and set basic visual parameters of `self.plot`
        """

        # This is called to make the basic plot window,
        # each task started should then send us params to populate afterwards
        #self.getPlotItem().hideAxis('bottom')

        self.layout = QtGui.QHBoxLayout()
        self.layout.setContentsMargins(2,2,2,2)
        self.setLayout(self.layout)

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

        #self.infobox.setS


        self.layout.addLayout(self.infobox, 2)

        # The plot that we own :)
        self.plot = pg.PlotWidget()
        self.plot.setContentsMargins(0,0,0,0)

        self.layout.addWidget(self.plot, 8)

        self.xrange = xrange(self.last_trial - self.x_width + 1, self.last_trial + 1)
        self.plot.setXRange(self.xrange[0], self.xrange[-1])

        self.plot.getPlotItem().hideAxis('left')
        self.plot.setBackground(None)
        self.plot.getPlotItem().getAxis('bottom').setPen({'color':'k'})
        self.plot.getPlotItem().getAxis('bottom').setTickFont('FreeMono')
        self.plot.setXRange(self.xrange[0], self.xrange[1])
        self.plot.setYRange(0, 1)

    @gui_event
    def l_start(self, value):
        """
        Starting a task, initialize task-specific plot objects described in the
        :attr:`.Task.PLOT` attribute.

        Matches the data field name (keys of :attr:`.Task.PLOT` ) to the plot object
        that represents it, eg, to make the standard nafc plot::

            {'target'   : 'point',
             'response' : 'segment',
             'correct'  : 'rollmean'}

        Args:
            value (dict): The same parameter dictionary sent by :meth:`.Terminal.toggle_start`, including

                * current_trial
                * step
                * session
                * step_name
                * task_type
        """
        # We're sent a task dict, we extract the plot params and send them to the plot object
        self.plot_params = tasks.TASK_LIST[value['task_type']].PLOT

        if 'continuous' in self.plot_params.keys():
            if self.plot_params['continuous']:
                self.continuous = True
            else:
                self.continuous = False
        else:
            self.continuous = False



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
                if self.plot_params['chance_level']:
                    try:
                        chance_level = float(self.plot_params['chance_level'])
                    except ValueError:
                        chance_level = 0.5
                        # TODO: Log this.

                    self.plot.getPlotItem().addLine(y=chance_level, pen=(255, 0, 0))

                else:
                    self.plot.getPlotItem().addLine(y=0.5, pen=(255, 0, 0))
        except KeyError:
            # No big deal, chance bar wasn't set
            pass

        # Make plot items for each data type
        for data, plot in self.plot_params['data'].items():
            # TODO: Better way of doing params for plots, redo when params are refactored
            if plot == 'rollmean' and 'roll_window' in self.plot_params.keys():
                self.plots[data] = Roll_Mean(winsize=self.plot_params['roll_window'])
                self.plot.addItem(self.plots[data])
                self.data[data] = np.zeros((0,2), dtype=np.float)
            else:
                self.plots[data] = PLOT_LIST[plot](continuous=self.continuous)
                self.plot.addItem(self.plots[data])
                self.data[data] = np.zeros((0,2), dtype=np.float)

        if 'video' in self.plot_params.keys():
            self.video = Video(self.plot_params['video'])
            self.videos = self.plot_params['video']

        self.state = 'RUNNING'



    @gui_event
    def l_data(self, value):
        """
        Receive some data, if we were told to plot it, stash the data
        and update the assigned plot.

        Args:
            value (dict): Value field of a data message sent during a task.
        """
        if 'trial_num' in value.keys():
            v = value.pop('trial_num')
            if v != self.last_trial:
                self.session_trials = self.n_trials.next()
            self.last_trial = v
            # self.last_trial = v
            self.info['N Trials'].setText("{}/{}".format(self.session_trials, v))
            if not self.continuous:
                self.xrange = xrange(v - self.x_width + 1, v + 1)
                self.plot.setXRange(self.xrange[0], self.xrange[-1])


        if 't' in value.keys():
            self.last_time = value.pop('t')
            if self.continuous:
                self.plot.setXRange(self.last_time-self.x_width, self.last_time+1)


        if self.continuous:
            x_val = self.last_time
        else:
            x_val = self.last_trial

        for k, v in value.items():
            if k in self.data.keys():
                self.data[k] = np.vstack((self.data[k], (x_val, v)))
                # gui_event_fn(self.plots[k].update, *(self.data[k],))
                self.plots[k].update(self.data[k])
            elif k in self.videos:
                self.video.update(k, v)






        sys.stdout.flush()

    @gui_event
    def l_stop(self, value):
        """
        Clean up the plot objects.

        Args:
            value (dict): if "graduation" is a key, don't stop the timer.
        """
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

        self.state = 'IDLE'

    def l_param(self, value):
        """
        Warning:
            Not implemented

        Args:
            value:
        """
        pass

    def l_state(self, value):
        """
        Pilot letting us know its state has changed. Mostly for the case where
        we think we're running but the pi doesn't.

        Args:
            value (:attr:`.Pilot.state`): the state of our pilot

        """

        if (value in ('STOPPING', 'IDLE')) and self.state == 'RUNNING':
            self.l_stop({})





###################################
# Curve subclasses
class Point(pg.PlotDataItem):
    """
    A simple point.

    Attributes:
        brush (:class:`QtGui.QBrush`)
        pen (:class:`QtGui.QPen`)
    """

    def __init__(self, color=(0,0,0), size=5, **kwargs):
        """
        Args:
            color (tuple): RGB color of points
            size (int): width in px.
        """
        super(Point, self).__init__()

        self.continuous = False
        if 'continuous' in kwargs.keys():
            self.continuous = kwargs['continuous']

        self.brush = pg.mkBrush(color)
        self.pen   = pg.mkPen(color, width=size)
        self.size  = size

    def update(self, data):
        """
        Args:
            data (:class:`numpy.ndarray`): an x_width x 2 array where
                column 0 is trial number and column 1 is the value,
                where value can be "L", "C", "R" or a float.
        """
        # data should come in as an n x 2 array,
        # 0th column - trial number (x), 1st - (y) value

        data[data=="R"] = 1
        data[data=="C"] = 0.5
        data[data=="L"] = 0
        data = data.astype(np.float)

        self.scatter.setData(x=data[...,0], y=data[...,1], size=self.size,
                             brush=self.brush, symbol='o', pen=self.pen)


class Segment(pg.PlotDataItem):
    """
    A line segment that draws from 0.5 to some endpoint.
    """
    def __init__(self, **kwargs):
        # type: () -> None
        super(Segment, self).__init__()

    def update(self, data):
        """
        data is doubled and then every other value is set to 0.5,
        then :meth:`~pyqtgraph.PlotDataItem.curve.setData` is used with
        `connect='pairs'` to make line segments.

        Args:
            data (:class:`numpy.ndarray`): an x_width x 2 array where
                column 0 is trial number and column 1 is the value,
                where value can be "L", "C", "R" or a float.
        """
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
    """
    Shaded area underneath a rolling average.

    Typically used as a rolling mean of corrects, so area above and below 0.5 is drawn.
    """
    def __init__(self, winsize=10, **kwargs):
        # type: (int) -> None
        """
        Args:
            winsize (int): number of trials in the past to take a rolling mean of
        """
        super(Roll_Mean, self).__init__()

        self.winsize = winsize

        self.setFillLevel(0.5)

        self.series = pd.Series()

        self.brush = pg.mkBrush((0,0,0,100))
        self.setBrush(self.brush)

    def update(self, data):
        """
        Args:
            data (:class:`numpy.ndarray`): an x_width x 2 array where
                column 0 is trial number and column 1 is the value.
        """
        # data should come in as an n x 2 array,
        # 0th column - trial number (x), 1st - (y) value
        data = data.astype(np.float)

        self.series = pd.Series(data[...,1])
        ys = self.series.rolling(self.winsize, min_periods=0).mean().as_matrix()

        #print(ys)

        self.curve.setData(data[...,0], ys, fillLevel=0.5)

class Shaded(pg.PlotDataItem):
    """
    Shaded area for a continuous plot
    """

    def __init__(self, **kwargs):
        super(Shaded, self).__init__()

        #self.dur = float(dur) # duration of time to display points in seconds
        self.setFillLevel(0)
        self.series = pd.Series()

        self.getBoundingParents()


        self.brush = pg.mkBrush((0,0,0,100))
        self.setBrush(self.brush)

        self.max_num = 0


    def update(self, data):
        """
        Args:
            data (:class:`numpy.ndarray`): an x_width x 2 array where
                column 0 is time and column 1 is the value.
        """
        # data should come in as an n x 2 array,
        # 0th column - trial number (x), 1st - (y) value
        data = data.astype(np.float)

        self.max_num = float(np.abs(np.max(data[:,1])))

        if self.max_num > 1.0:
            data[:,1] = (data[:,1]/(self.max_num*2.0))+0.5
        #print(ys)

        self.curve.setData(data[...,0], data[...,1], fillLevel=0)




class Timer(QtGui.QLabel):
    """
    A simple timer that counts... time...

    Uses a :class:`QtCore.QTimer` connected to :meth:`.Timer.update_time` .
    """
    def __init__(self):
        # type: () -> None
        super(Timer, self).__init__()

        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self.update_time)

        self.start_time = None

    def start_timer(self, update_interval=1000):
        """
        Args:
            update_interval (float): How often (in ms) the timer should be updated.
        """
        self.start_time = time()
        self.timer.start(update_interval)

    def stop_timer(self):
        """
        you can read the sign ya punk
        """
        self.timer.stop()
        self.setText("")

    def update_time(self):
        """
        Called every (update_interval) milliseconds to set the text of the timer.

        """
        secs_elapsed = int(np.floor(time()-self.start_time))
        self.setText("{:02d}:{:02d}:{:02d}".format(secs_elapsed/3600, (secs_elapsed/60)%60, secs_elapsed%60))

class Video(QtGui.QWidget):
    def __init__(self, videos, fps=30):
        super(Video, self).__init__()

        self.videos = videos
        self._newframe = None
        self.last_update = 0
        self.fps = fps
        self.ifps = 1.0/fps


        self.init_gui()

    def init_gui(self):
        self.layout = QtGui.QGridLayout()
        self.vid_widgets = {}
        if len(self.videos)<2:
            # single row
            for i, vid in enumerate(self.videos):
                vid_label = QtGui.QLabel(vid)
                self.vid_widgets[vid] = pg.ImageView()
                self.layout.addWidget(0,i,vid_label)
                self.layout.addWidget(1,i,vid_label)
        self.show()

    def update(self, video, data):
        if (time()-self.last_update)>self.ifps:
            try:
                self.vid_widgets[video].setImage(data)
            except KeyError:
                return
            self.last_update = time()




# class Highlight():
#     # TODO Implement me
#     def __init__(self):
#         pass
#
#     pass


class HLine(QtGui.QFrame):
    """
    A Horizontal line.
    """
    def __init__(self):
        # type: () -> None
        super(HLine, self).__init__()
        self.setFrameShape(QtGui.QFrame.HLine)
        self.setFrameShadow(QtGui.QFrame.Sunken)


PLOT_LIST = {
    'point':Point,
    'segment':Segment,
    'rollmean':Roll_Mean,
    'shaded':Shaded
    # 'highlight':Highlight
}
"""
A dictionary connecting plot keys to objects.

TODO:
    Just reference the plot objects.
"""