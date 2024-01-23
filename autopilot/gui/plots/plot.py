from functools import wraps
from itertools import count

import numpy as np
import pyqtgraph as pg
from PySide6 import QtCore, QtWidgets

import autopilot
from autopilot import prefs
from autopilot.utils.loggers import init_logger
from autopilot.gui.plots.video import Video
from autopilot.gui.plots.info import Timer
from autopilot.gui.plots.geom import Roll_Mean, HLine, PLOT_LIST
from autopilot.networking import Net_Node
from autopilot.utils.invoker import get_invoker, InvokeEvent


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
        QtCore.QCoreApplication.postEvent(get_invoker(), InvokeEvent(fn, *args, **kwargs))
    return wrapper_gui_event


class Plot_Widget(QtWidgets.QWidget):
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
        QtWidgets.QWidget.__init__(self)

        self.logger = init_logger(self)


        # We should get passed a list of pilots to keep ourselves in order after initing
        self.pilots = None

        # Dict to store handles to plot windows by pilot
        self.plots = {}

        # Main Layout
        self.layout = QtWidgets.QVBoxLayout(self)
        self.layout.setContentsMargins(0,0,0,0)
        self.layout.setSpacing(0)

        # Plot Selection Buttons
        # TODO: Each plot bar should have an option panel, because different tasks have different plots
        #self.plot_select = self.create_plot_buttons()

        # Create empty plot container
        self.plot_layout = QtWidgets.QVBoxLayout()

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
            plot = Plot(pilot=p, parent=self)
            self.plot_layout.addWidget(plot)
            self.plot_layout.addWidget(HLine())
            self.plots[p] = plot


class Plot(QtWidgets.QWidget):
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

        infobox (:class:`QtWidgets.QFormLayout`): Box to plot basic task information like trial number, etc.
        info (dict): Widgets in infobox:

            * 'N Trials': :class:`QtWidgets.QLabel`,
            * 'Runtime' : :class:`.Timer`,
            * 'Session' : :class:`QtWidgets.QLabel`,
            * 'Protocol': :class:`QtWidgets.QLabel`,
            * 'Step'    : :class:`QtWidgets.QLabel`

        plot (:class:`pyqtgraph.PlotWidget`): The widget where we draw our plots
        plot_params (dict): A dictionary of plot parameters we receive from the Task class
        data (dict): A dictionary of the data we've received
        plots (dict): The collection of plots we instantiate based on `plot_params`
        node (:class:`.Net_Node`): Our local net node where we listen for data.
        state (str): state of the pilot, used to keep plot synchronized.
    """

    def __init__(self, pilot, x_width=50, parent=None):
        """
        Args:
            pilot (str): The name of our pilot
            x_width (int): How many trials in the past should we plot?
        """
        #super(Plot, self).__init__(QtOpenGL.QGLFormat(QtOpenGL.QGL.SampleBuffers), parent)
        super(Plot, self).__init__()

        self.logger = init_logger(self)

        self.parent = parent
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
        self.video = None
        self.videos = []

        self.invoker = get_invoker()

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
            'CONTINUOUS': self.l_data,
            'STOP' : self.l_stop,
            'PARAM': self.l_param, # changing some param
            'STATE': self.l_state
        }

        self.node = Net_Node(id='P_{}'.format(self.pilot),
                             upstream="T",
                             port=prefs.get('MSGPORT'),
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

        self.layout = QtWidgets.QHBoxLayout()
        self.layout.setContentsMargins(2,2,2,2)
        self.setLayout(self.layout)

        # A little infobox to keep track of running time, trials, etc.
        self.infobox = QtWidgets.QFormLayout()
        self.n_trials = count()
        self.session_trials = 0
        self.info = {
            'N Trials': QtWidgets.QLabel(),
            'Runtime' : Timer(),
            'Session' : QtWidgets.QLabel(),
            'Protocol': QtWidgets.QLabel(),
            'Step'    : QtWidgets.QLabel()
        }
        for k, v in self.info.items():

            self.infobox.addRow(k, v)

        #self.infobox.setS


        self.layout.addLayout(self.infobox, 2)

        # The plot that we own :)
        self.plot = pg.PlotWidget()
        self.plot.setContentsMargins(0,0,0,0)

        self.layout.addWidget(self.plot, 8)

        self.xrange = range(self.last_trial - self.x_width + 1, self.last_trial + 1)
        self.plot.setXRange(self.xrange[0], self.xrange[-1])

        # self.plot.getPlotItem().hideAxis('left')
        self.plot.setBackground(None)
        self.plot.getPlotItem().getAxis('bottom').setPen({'color':'k'})
        self.plot.getPlotItem().getAxis('bottom').setTickFont('FreeMono')
        self.plot.setXRange(self.xrange[0], self.xrange[1])
        self.plot.enableAutoRange(y=True)
        # self.plot
        # self.plot.setYRange(0, 1)

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

        if self.state in ("RUNNING", "INITIALIZING"):
            return

        self.state = "INITIALIZING"


        # set infobox stuff
        self.n_trials = count()
        self.session_trials = 0
        self.info['N Trials'].setText(str(value['current_trial']))
        self.info['Runtime'].start_timer()
        self.info['Step'].setText(str(value['step']))
        self.info['Session'].setText(str(value['session']))
        self.info['Protocol'].setText(value['step_name'])

        # We're sent a task dict, we extract the plot params and send them to the plot object
        self.plot_params = autopilot.get_task(value['task_type']).PLOT

        # if we got no plot params, that's fine, just set as running and return
        if not self.plot_params:
            self.logger.warning(f"No plot params for task {value['task_type']}")
            self.state = "RUNNING"
            return

        if 'continuous' in self.plot_params.keys():
            if self.plot_params['continuous']:
                self.continuous = True
            else:
                self.continuous = False
        else:
            self.continuous = False





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

        self.x_width = self.plot_params.get('x_width', self.x_width)
        if 'y_range' in self.plot_params:
            self.plot.setYRange(*self.plot_params['y_range'])

        # Make plot items for each data type
        for data, plot in self.plot_params.get('data', {}).items():
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
            self.videos = self.plot_params['video']
            self.video = Video(self.plot_params['video'])
            #self.video.start()


        self.state = 'RUNNING'



    @gui_event
    def l_data(self, value):
        """
        Receive some data, if we were told to plot it, stash the data
        and update the assigned plot.

        Args:
            value (dict): Value field of a data message sent during a task.
        """
        self.logger.debug(f'got data {value}')

        if self.state == "INITIALIZING":
            return

        #pdb.set_trace()
        if 'trial_num' in value.keys():
            v = value.pop('trial_num')
            if v >= self.last_trial:
                self.session_trials = next(self.n_trials)
            elif v < self.last_trial:
                self.logger.exception('Shouldnt be going back in time!')
            self.last_trial = v
            # self.last_trial = v
            self.info['N Trials'].setText("{}/{}".format(self.session_trials, v))
            if not self.continuous:
                self.xrange = range(v - self.x_width + 1, v + 1)
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
                self.video.update_frame(k, v)



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

        if self.video is not None:
            self.video.release()
            self.video.close()
            del self.video
            del self.videos
            self.video = None
            self.videos = []

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
            #self.l_stop({})
            pass