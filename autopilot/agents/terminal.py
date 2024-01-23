"""Methods for running the Terminal GUI"""
import typing
import argparse
import json
import sys
import os
from pathlib import Path
from pprint import pformat
import time

import datetime
import logging
import threading
from collections import OrderedDict as odict
import numpy as np

from PySide6 import QtCore, QtGui, QtWidgets

from autopilot import prefs
from autopilot.gui import styles

if __name__ == '__main__':
    # Parse arguments - this should have been called with a .json prefs file passed
    # We'll try to look in the default location first
    parser = argparse.ArgumentParser(description="Run an autopilot Terminal")
    parser.add_argument('-f', '--prefs', help="Location of .json prefs file (created during setup_autopilot.py)")
    args = parser.parse_args()

    if not args.prefs:
        prefs_file = '/usr/autopilot/prefs.json'

        if not os.path.exists(prefs_file):
            raise Exception("No Prefs file passed, and file not in default location")

        raise Warning('No prefs file passed, loaded from default location. Should pass explicitly with -p')

    else:
        prefs_file = args.prefs

    # init prefs for module access
    prefs.init(prefs_file)

from autopilot.data.subject import Subject
from autopilot.gui.plots.plot import Plot_Widget
from autopilot.networking import Net_Node, Terminal_Station
from autopilot.utils.invoker import get_invoker
from autopilot.gui.dialog import pop_dialog
from autopilot.gui.menus.swarm import Stream_Video
from autopilot.gui.menus.plugins import Plugins
from autopilot.gui.menus.tools import Calibrate_Water, Reassign, Weights
from autopilot.gui.menus.tests import Bandwidth_Test
from autopilot.gui.menus.file import Protocol_Wizard
from autopilot.gui.widgets.terminal import Control_Panel
from autopilot.utils.loggers import init_logger

# Try to import viz, but continue if that doesn't work
IMPORTED_VIZ = False
VIZ_ERROR = None
try:
    from autopilot import viz
    IMPORTED_VIZ = True
except ImportError as e:
    VIZ_ERROR = str(e)

_TERMINAL = None

class Terminal(QtWidgets.QMainWindow):
    """
    Central host to a swarm of :class:`.Pilot` s and user-facing
    :mod:`.gui` objects.

    Called as a module with the -f flag to give the location of a prefs file, eg::

        python terminal.py -f prefs_file.json

    if the -f flag is not passed, looks in the default location for prefs
    (ie. `/usr/autopilot/prefs.json`)

    **Listens used by the internal :class:`.Net_Node` **

    +---------------+--------------------------------+--------------------------------------------------------+
    | Key           | Method                         | Description                                            |
    +===============+================================+========================================================+
    | `'STATE'`     | :meth:`~.Terminal.l_state`     | A Pi has changed state                                 |
    +---------------+--------------------------------+--------------------------------------------------------+
    | `'PING'`      | :meth:`~.Terminal.l_ping`      |  Someone wants to know if we're alive                  |
    +---------------+--------------------------------+--------------------------------------------------------+
    | `'DATA'`      | :meth:`~.Terminal.l_data`      | Receiving data to store                                |
    +---------------+--------------------------------+--------------------------------------------------------+
    | `'HANDSHAKE'` | :meth:`~.Terminal.l_handshake` | Pilot first contact, telling us it's alive and its IP  |
    +---------------+--------------------------------+--------------------------------------------------------+


    .. note::

        See :mod:`autopilot.prefs` for full list of prefs needed by terminal!

    .. note::

        The Terminal class is currently a subclass of :class:`PySide6.QtWidgets.QMainWindow` -- it will be refactored to
        inherit from :class:`~autopilot.agents.base.Agent` as the agent system is formalized.

    Attributes:
        node (:class:`~.networking.Net_Node`): Our Net_Node we use to communicate with our main networking object
        networking (:class:`~.networking.Terminal_Station`): Our networking object to communicate with the outside world
        subjects (dict): A dictionary mapping subject ID to :class:`~.subject.Subject` object.
        layout (:class:`QtWidgets.QGridLayout`): Layout used to organize widgets
        control_panel (:class:`~.gui.Control_Panel`): Control Panel to manage pilots and subjects
        data_panel (:class:`~.plots.Plot_Widget`): Plots for each pilot and subject.
        logo (:class:`QtWidgets.QLabel`): Label holding our beautiful logo ;X
        logger (:class:`logging.Logger`): Used to log messages and network events.
        settings (:class:`PySide2.QtCore.QSettings`): QSettings used to store pyside configuration like window size,
            stored in ``prefs.get("TERMINAL_SETTINGS_FN")``
    """

    def __init__(self, warn_defaults=True):
        super(Terminal, self).__init__()

        if warn_defaults:
            os.environ['AUTOPILOT_WARN_DEFAULTS'] = '1'

        # store instance
        globals()['_TERMINAL'] = self

        # Load settings
        # Currently, the only setting is "geometry", but loading here
        # in case we start to use other ones in the future
        self.settings = QtCore.QSettings(prefs.get("TERMINAL_SETTINGS_FN"),
                                         QtCore.QSettings.NativeFormat)

        # networking
        self.node = None
        self.networking = None
        self.heartbeat_dur = 10 # check every n seconds whether our pis are around still

        # data
        self.subjects = {}  # Dict of our open subject objects

        # gui
        self.layout = None
        self.widget = None
        self.file_menu = None
        self.tool_menu = None
        self.control_panel = None
        self.data_panel = None
        self.logo = None

        # property private attributes
        self._pilots = None

        # logging
        self.logger = init_logger(self)

        # Listen dictionary - which methods to call for different messages
        # Methods are spawned in new threads using handle_message
        self.listens = {
            'STATE': self.l_state, # A Pi has changed state
            'PING' : self.l_ping,  # Someone wants to know if we're alive
            'DATA' : self.l_data,
            'CONTINUOUS': self.l_data, # handle continuous data same way as other data
            'STREAM': self.l_data,
            'HANDSHAKE': self.l_handshake # a pi is making first contact, telling us its IP
        }

        # Make invoker object to send GUI events back to the main thread
        # self.invoker = Invoker()
        self.invoker = get_invoker()
        # prefs.add('INVOKER', self.invoker)

        self.initUI()

        # Start Networking
        # Networking is in two parts,
        # "internal" networking for messages sent to and from the Terminal object itself
        # "external" networking for messages to and from all the other components,
        # The split is so the external networking can run in another process, do potentially time-consuming tasks
        # like resending & confirming message delivery without blocking or missing messages

        # Start external communications in own process
        # Has to be after init_network so it makes a new context
        self.networking = Terminal_Station(self.pilots)
        self.networking.start()
        self.logger.info("Station object Initialized")

        self.node = Net_Node(id="_T", upstream='T', port=prefs.get('MSGPORT'), listens=self.listens, instance=False)
        self.logger.info("Net Node Initialized")

        # send an initial ping looking for our pilots
        self.node.send('T', 'INIT')

        # start beating ur heart
        # self.heartbeat_timer = threading.Timer(self.heartbeat_dur, self.heartbeat)
        # self.heartbeat_timer.daemon = True
        # self.heartbeat_timer.start()
        #self.heartbeat(once=True)
        self.logger.info('Terminal Initialized')

        # if we don't have any pilots, pop a dialogue to declare one
        if len(self.pilots) == 0:
            box = pop_dialog(
                'No Pilots', 'No pilots were found in the pilot_db, add one now?',
                buttons=('Yes', 'No')
            )
            ret = box.exec_()
            if ret == box.Yes:
                self.new_pilot()



    def initUI(self):
        """
        Initializes graphical elements of Terminal.

        Including...

        * Toolbar
        * :class:`.gui.Control_Panel`
        * :class:`.plots.Plot_Widget`
        """
        # Set central widget
        self.widget = QtWidgets.QWidget()
        self.setCentralWidget(self.widget)

        # Set the layout
        self.layout = QtWidgets.QGridLayout()
        self.layout.setSpacing(0)
        self.layout.setContentsMargins(0,0,0,0)
        self.widget.setLayout(self.layout)

        # Set title
        self.setWindowTitle('Terminal')
        #self.menuBar().setFixedHeight(40)

        # This is the pixel resolution of the entire screen
        if 'pytest' in sys.modules:
            primary_display = None
            terminal_winsize_behavior = 'custom'
            custom_size=[0,0,1000,480]
        else:
            terminal_winsize_behavior = prefs.get('TERMINAL_WINSIZE_BEHAVIOR')
            custom_size = prefs.get('TERMINAL_CUSTOM_SIZE')
            app = QtWidgets.QApplication.instance()
            screensize = app.primaryScreen().size()

            # This is the available geometry of the primary screen, excluding
            # window manager reserved areas such as task bars and system menus.
            primary_display = app.primaryScreen().availableGeometry()

        ## Initalize the menuBar
        # Linux: Set the menuBar to a fixed height
        # Darwin: Don't worry about menuBar
        if sys.platform == 'darwin':
            bar_height = 0
        else:
            if primary_display is None:
                self.menuBar().setFixedHeight(30)
            else:
                bar_height = (primary_display.height()/30)+5
                self.menuBar().setFixedHeight(bar_height)

        # Create a File menu
        self.file_menu = self.menuBar().addMenu("&File")
        self.file_menu.setObjectName("file")

        # Add "New Pilot" and "New Protocol" actions to File menu
        new_pilot_act = QtGui.QAction("New &Pilot", self, triggered=self.new_pilot)
        new_prot_act  = QtGui.QAction("New Pro&tocol", self, triggered=self.new_protocol)
        new_subject = QtGui.QAction("New &Subject", self, triggered=self.new_subject)
        #batch_create_subjects = QtGui.QAction("Batch &Create subjects", self, triggered=self.batch_subjects)
        # TODO: Update pis
        self.file_menu.addAction(new_pilot_act)
        self.file_menu.addAction(new_prot_act)
        self.file_menu.addAction(new_subject)
        #self.file_menu.addAction(batch_create_subjects)

        # Create a Tools menu
        self.tool_menu = self.menuBar().addMenu("&Tools")

        # Add actions to Tools menu
        subject_weights_act = QtGui.QAction("View Subject &Weights", self, triggered=self.subject_weights)
        update_protocol_act = QtGui.QAction("Update Protocols", self, triggered=self.update_protocols)
        reassign_act = QtGui.QAction("Batch Reassign Protocols", self, triggered=self.reassign_protocols)
        calibrate_act = QtGui.QAction("Calibrate &Water Ports", self, triggered=self.calibrate_ports)
        self.tool_menu.addAction(subject_weights_act)
        self.tool_menu.addAction(update_protocol_act)
        self.tool_menu.addAction(reassign_act)
        self.tool_menu.addAction(calibrate_act)

        # Swarm menu
        # (tools 4 administering and interacting with agents in swarm)
        self.swarm_menu = self.menuBar().addMenu("S&warm")
        stream_video = QtGui.QAction("Stream Video", self, triggered=self.stream_video)
        self.swarm_menu.addAction(stream_video)

        # Plots menu
        self.plots_menu = self.menuBar().addMenu("&Plots")
        psychometric = QtGui.QAction("Psychometric Curve", self, triggered=self.plot_psychometric)
        self.plots_menu.addAction(psychometric)

        # Create a Tests menu and add a Test Bandwidth action
        self.tests_menu = self.menuBar().addMenu("Test&s")
        bandwidth_test_act = QtGui.QAction("Test Bandwidth", self, triggered=self.test_bandwidth)
        self.tests_menu.addAction(bandwidth_test_act)

        # Create a Plugins menu to manage plugins and provide a hook to give them additional terminal actions
        self.plugins_menu = self.menuBar().addMenu("Plugins")
        plugin = QtGui.QAction("Manage Plugins", self, triggered=self.manage_plugins)
        self.plugins_menu.addAction(plugin)


        ## Init main panels and add to layout
        # Control panel sits on the left, controls pilots & subjects
        self.control_panel = Control_Panel(pilots=self.pilots,
                                           subjects=self.subjects,
                                           start_fn=self.toggle_start,
                                           ping_fn=self.ping_pilot)

        # Data panel sits on the right, plots stuff.
        self.data_panel = Plot_Widget()
        self.data_panel.init_plots(self.pilots.keys())

        # Set logo to corner widget
        # if sys.platform != 'darwin':
        #     self.menuBar().setCornerWidget(self.logo, QtCore.Qt.TopRightCorner)
        #     self.menuBar().adjustSize()

        # Add Control Panel and Data Panel to main layout
        #self.layout.addWidget(self.logo, 0,0,1,2)
        self.layout.addWidget(self.control_panel, 0,0,1,1)
        self.layout.addWidget(self.data_panel, 0,1,1,1)
        self.layout.setColumnStretch(0, 1)
        self.layout.setColumnStretch(1, 3)


        ## Set window size
        # The window size behavior depends on TERMINAL_WINSIZE_BEHAVIOR pref
        # If 'remember': restore to the geometry from the last close
        # If 'maximum': restore to fill the entire screen
        # If 'moderate': restore to a reasonable size of (1000, 400) pixels

        # Set geometry according to pref
        if terminal_winsize_behavior == 'maximum':
            # Set geometry to available geometry
            self.setGeometry(primary_display)

            # Set SizePolicy to maximum
            self.setSizePolicy(
                QtWidgets.QSizePolicy.Maximum, QtWidgets.QSizePolicy.Maximum)

            # Move to top left corner of primary display
            self.move(primary_display.left(), primary_display.top())

            # Also set the maximum height of each panel
            self.control_panel.setMaximumHeight(primary_display.height())
            self.data_panel.setMaximumHeight(primary_display.height())

        elif terminal_winsize_behavior == 'remember':
            # Attempt to restore previous geometry
            if self.settings.value("geometry") is None:
                # It was never saved, for instance, this is the first time
                # this app has been run
                # So default to the moderate size
                self.move(primary_display.left(), primary_display.top())
                self.resize(1000, 400)
            else:
                # It was saved, so restore the last geometry
                self.restoreGeometry(self.settings.value("geometry"))

        elif terminal_winsize_behavior == "custom":
            self.move(custom_size[0], custom_size[1])
            self.resize(custom_size[2], custom_size[3])
        else:
            if terminal_winsize_behavior != 'moderate':
                self.logger.warning(f'TERMINAL_WINSIZE_BEHAVIOR {terminal_winsize_behavior} is not implemented, defaulting to "moderate"')

            # The moderate size
            self.move(primary_display.left(), primary_display.top())
            self.resize(1000, 400)


        ## Finalize some aesthetics
        # set stylesheet for main window
        self.setStyleSheet(styles.TERMINAL)

        ## Show, and log that initialization is complete
        self.show()
        logging.info('UI Initialized')

    def reset_ui(self):
        """
        Clear Layout and call :meth:`~.Terminal.initUI` again
        """

        # type: () -> None
        self.layout = QtWidgets.QGridLayout()
        self.layout.setSpacing(0)
        self.layout.setContentsMargins(0,0,0,0)
        self.widget.setLayout(self.layout)
        self.setCentralWidget(self.widget)
        self.initUI()

    ################
    # Properties

    @property
    def pilots(self) -> odict:
        """
        A dictionary mapping pilot ID to its attributes, including a list of its subjects assigned to it, its IP, etc.

        Returns:
            dict: like ``self.pilots['pilot_id'] = {'subjects': ['subject_0', 'subject_1'], 'ip': '192.168.0.101'}``
        """

        # try to load, if none exists make one
        if self._pilots is None:

            pilot_db_fn = Path(prefs.get('PILOT_DB'))

            # if pilot file doesn't exist, make blank one
            if not pilot_db_fn.exists():
                self.logger.warning(f'No pilot_db.json file was found at {pilot_db_fn}, creating a new one')
                self._pilots = odict()
                with open(pilot_db_fn, 'w') as pilot_file:
                    json.dump(self._pilots, pilot_file)

            # otherwise, try to load it
            else:
                try:
                    # Load pilots db as ordered dictionary
                    with open(pilot_db_fn, 'r') as pilot_file:
                        self._pilots = json.load(pilot_file, object_pairs_hook=odict)
                    self.logger.info(f'successfully loaded pilot_db.json file from {pilot_db_fn}')
                    self.logger.debug(pformat(self._pilots))
                except Exception as e:
                    self.logger.exception((f"Exception opening pilot_db.json file at {pilot_db_fn}, got exception: {e}.\n",
                                           "Not proceeding to prevent possibly overwriting corrupt pilot_db.file"))
                    raise e

        return self._pilots


    @property
    def protocols(self) -> list:
        """
        List of protocol names available in ``PROTOCOLDIR``

        Returns:
            list: list of protocol names in ``prefs.get('PROTOCOLDIR')``
        """
        # get list of protocol files
        protocols = os.listdir(prefs.get('PROTOCOLDIR'))
        protocols = [os.path.splitext(p)[0] for p in protocols if p.endswith('.json')]
        return protocols

    @property
    def subject_protocols(self) -> dict:
        """

        Returns:
            subject_protocols (dict): a dictionary of subjects: [protocol, step]
        """
        # get subjects and current protocols
        subjects = self.subject_list
        subjects_protocols = {}
        for subject in subjects:
            if subject not in self.subjects.keys():
                self.subjects[subject] = Subject(subject)

            try:
                subjects_protocols[subject] = [self.subjects[subject].protocol.protocol_name, self.subjects[subject].protocol.step]
            except AttributeError:
                subjects_protocols[subject] = [None, None]
        return subjects_protocols

    @property
    def subject_list(self) -> list:
        """
        Get a list of all subject IDs

        Returns:
            list: list of all subject IDs present in :attr:`.Terminal.pilots`
        """
        subjects = []
        for pilot, vals in self.pilots.items():
            subjects.extend(vals['subjects'])

        # use sets to get a unique list
        subjects = list(set(subjects))

        return subjects

    ##########################3
    # Listens & inter-object methods

    def ping_pilot(self, pilot):
        self.node.send(pilot, 'PING')

    def heartbeat(self, once=False):
        """
        Perioducally send an ``INIT`` message that checks the status of connected pilots

        sent with frequency according to :attr:`.Terminal.heartbeat_dur`

        Args:
            once (bool): if True, do a single heartbeat but don't start a thread to do more.

        """
        self.node.send('T', 'INIT', repeat=False, flags={'NOREPEAT': True})

        if not once:
            self.heartbeat_timer = threading.Timer(self.heartbeat_dur, self.heartbeat)
            self.heartbeat_timer.daemon = True
            self.heartbeat_timer.start()

    def toggle_start(self, starting, pilot, subject=None):
        """Start or Stop running the currently selected subject's task. Sends a
        message containing the task information to the concerned pilot.

        Each :class:`Pilot_Panel` is given a lambda function that calls this
        one with the arguments specified See :class:`Pilot_Button`, as it is
        what calls this function.

        Args:
            starting (bool): Does this button press mean we are starting (True)
                or stopping (False) the task?
            pilot: Which Pilot is starting or stopping?
            subject: Which Subject is currently selected?
        """
        # stopping is the enemy of starting so we put them in the same function to learn about each other
        if starting is True:
            # Get Weights
            start_weight, ok = QtWidgets.QInputDialog.getDouble(self, "Set Starting Weight",
                                                            "Starting Weight:")
            if ok:
                # Ope'nr up if she aint
                if subject not in self.subjects.keys():
                    self.subjects[subject] = Subject(subject)


                self.subjects[subject].update_weights(start=float(start_weight))
                task = self.subjects[subject].prepare_run()
                task['pilot'] = pilot

                self.node.send(to=pilot, key="START", value=task)
                # also let the plot know to start
                self.node.send(to="P_{}".format(pilot), key="START", value=task)

            else:
                # pressed cancel, don't start
                return

        else:
            # Send message to pilot to stop running,
            self.node.send(to=pilot, key="STOP")
            # also let the plot know to start
            self.node.send(to="P_{}".format(pilot), key="STOP")
            # TODO: Start coherence checking ritual
            # TODO: Auto-select the next subject in the list.
            # Get Weights
            stop_weight, ok = QtWidgets.QInputDialog.getDouble(self, "Set Stopping Weight",
                                                               "Stopping Weight:")

            self.subjects[subject].stop_run()
            self.subjects[subject].update_weights(stop=float(stop_weight))



    ############################
    # MESSAGE HANDLING METHODS

    def l_data(self, value):
        """
        A Pilot has sent us data.

        `value` field of message should have `subject` and `pilot` added to dictionary for identification.

        Any key in `value` that matches a column in the subject's trial data table will be saved.

        If the subject graduates after receiving this piece of data, stop the current
        task running on the Pilot and send the new one.

        Args:
            value (dict): A dict of field-value pairs to save
        """
        # A Pi has sent us data, let's save it huh?
        subject_name = value['subject']
        self.subjects[subject_name].save_data(value)
        if self.subjects[subject_name].did_graduate.is_set() is True:
            self.node.send(to=value['pilot'], key="STOP", value={'graduation':True})
            self.subjects[subject_name].stop_run()
            self.subjects[subject_name]._graduate()
            task = self.subjects[subject_name].prepare_run()
            task['pilot'] = value['pilot']

            # FIXME: Don't hardcode wait time, wait until we get confirmation that the running task has fully unloaded
            time.sleep(5)

            self.node.send(to=value['pilot'], key="START", value=task)

    def l_ping(self, value):
        """
        TODO:
            Reminder to implement heartbeating.

        Note:
            Currently unused, as Terminal Net_Node stability hasn't been
            a problem and no universal system of heartbeating has been
            established (global stability has not been an issue).

        Args:
            value: (unused)
        """
        # Only our Station object should ever ping us, because
        # we otherwise want it handling any pings on our behalf.

        # self.send_message('ALIVE', value=b'T')
        pass



    def l_state(self, value):
        """A Pilot has changed state, keep track of it.

        Args:
            value (dict): dict containing `state` .
        """
        # TODO: If we are stopping, we enter into a cohere state
        # TODO: If we are stopped, close the subject object.
        # TODO: Also tell the relevant dataview to clear

        # update the pilot button
        self.logger.debug(f'updating pilot state: {value}')
        if value['pilot'] not in self.pilots.keys():
            self.logger.info('Got state info from an unknown pilot, adding...')
            self.new_pilot(name=value['pilot'])

        self.pilots[value['pilot']]['state'] = value['state']
        self.control_panel.panels[value['pilot']].button.set_state(value['state'])

    def l_handshake(self, value):
        """
        Pilot is sending its IP and state on startup.

        If we haven't heard of this pilot before, make a new entry in :attr:`~.Terminal.pilots`
        and :meth:`.gui.Control_Panel.update_db` .

        Args:
            value (dict): dict containing `ip` and `state`
        """
        if value['pilot'] in self.pilots.keys():
            self.pilots[value['pilot']]['ip'] = value.get('ip', '')
            self.pilots[value['pilot']]['state'] = value.get('state', '')
            self.pilots[value['pilot']]['prefs'] = value.get('prefs', {})

        else:
            self.new_pilot(name=value['pilot'],
                           ip=value.get('ip', ''),
                           pilot_prefs=value.get('prefs', {}))

        # update the pilot button
        if value['pilot'] in self.control_panel.panels.keys():
            self.control_panel.panels[value['pilot']].button.set_state(value['state'])


        self.control_panel.update_db()

    #############################
    # GUI & etc. methods

    def new_pilot(self,
                  name:typing.Optional[str]=None,
                  ip:str='',
                  pilot_prefs:typing.Optional[dict]=None):
        """
        Make a new entry in :attr:`.Terminal.pilots` and make appropriate
        GUI elements.

        Args:
            ip (str): Optional. if given, stored in db.
            name (str): If None, prompted for a name, otherwise used for entry in pilot DB.
        """
        if name is None:
            name, ok = QtWidgets.QInputDialog.getText(self, "Pilot ID", "Pilot ID:")
            if not ok or not name:
                self.logger.info('Cancel button clicked, not adding new pilot')
                return

        # Warn if we're going to overwrite
        if name in self.pilots.keys():
            self.logger.warning(f'pilot with id {name} already in pilot db, overwriting...')

        if pilot_prefs is None:
            pilot_prefs = {}

        self.control_panel.add_pilot(name)
        new_pilot = {name:{'subjects':[], 'ip':ip, 'prefs':pilot_prefs}}
        self.control_panel.update_db(new=new_pilot)
        self.logger.info(f'added new pilot {name}')

    def new_protocol(self):
        """
        Open a :class:`.gui.Protocol_Wizard` to create a new protocol.

        Prompts for name of protocol, then saves in `prefs.get('PROTOCOLDIR')`
        """
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
                    elif k == 'stim':
                        # TODO: Super hacky - don't do this. Refactor params already.
                        param_values[k] = {}
                        for stimtype, stim in v.items():
                            param_values[k][stimtype] = stim
                save_steps.append(param_values)

            # Name the protocol
            name, ok = QtWidgets.QInputDialog.getText(self, "Name Protocol", "Protocol Name:")
            if ok and name != '':
                protocol_file = os.path.join(prefs.get('PROTOCOLDIR'), name + '.json')
                with open(protocol_file, 'w') as pfile_open:
                    json.dump(save_steps, pfile_open, indent=4, separators=(',', ': '), sort_keys=True)
            elif name == '' or not ok:
                placeholder_name = 'protocol_created_{}'.format(datetime.date.today().isoformat())
                protocol_file = os.path.join(prefs.get('PROTOCOLDIR'), placeholder_name + '.json')
                with open(protocol_file, 'w') as pfile_open:
                    json.dump(save_steps, pfile_open, indent=4, separators=(',', ': '), sort_keys=True)

    def new_subject(self):
        pop_dialog("Not Implemented", details="Creating subjects from the File menu needs some cleaning up, in the meantime use the + button within a Pilot control panel",
                   msg_type="warning").exec_()
        # new_subject = New_Subject_Wizard()
        # new_subject.exec_()

    def subject_weights(self):
        """
        Gets recent weights from all :attr:`~.Terminal.subjects` and
        open a :class:`.gui.Weights` window to view or set weights.
        """
        subjects = self.subject_list

        # open objects if not already
        for subject in subjects:
            if subject not in self.subjects.keys():
                self.subjects[subject] = Subject(subject)

        # for each subject, get weight
        weights = []
        for subject in subjects:
            weight = self.subjects[subject].get_weight(include_baseline=True)
            weight['subject'] = subject
            weights.append(weight)

        self.weight_widget = Weights(weights, self.subjects)
        self.weight_widget.show()

    def update_protocols(self):
        """
        If we change the protocol file, update the stored version in subject files
        """
        #
        # get list of protocol files
        protocols = os.listdir(prefs.get('PROTOCOLDIR'))
        protocols = [p for p in protocols if p.endswith('.json')]

        updated_subjects = []
        subjects = self.subject_list
        for subject in subjects:
            if subject not in self.subjects.keys():
                self.subjects[subject] = Subject(subject)

            protocol_bool = [self.subjects[subject].protocol_name == os.path.splitext(p)[0] for p in protocols]
            if any(protocol_bool):
                which_prot = np.where(protocol_bool)[0][0]
                protocol = protocols[which_prot]
                self.subjects[subject].assign_protocol(os.path.join(prefs.get('PROTOCOLDIR'), protocol), step_n=self.subjects[subject].step)
                updated_subjects.append(subject)

        msgbox = QtWidgets.QMessageBox()
        msgbox.setText("Subject Protocols Updated for:")
        msgbox.setDetailedText("\n".join(sorted(updated_subjects)))
        msgbox.exec_()

    def reassign_protocols(self):
        """
        Batch reassign protocols and steps.

        Opens a :class:`.gui.Reassign` window after getting protocol data,
        and applies any changes made in the window.
        """

        reassign_window = Reassign(self.subject_protocols, self.protocols)
        reassign_window.exec_()

        if reassign_window.result() == 1:
            subject_protocols = reassign_window.subjects

            for subject, protocol in subject_protocols.items():
                step = protocol[1]
                protocol = protocol[0]

                if not protocol:
                    self.logger.info(f'Protocol for {subject} set to blank, not setting')
                    continue

                self.subjects[subject].assign_protocol(protocol, step)
                self.logger.debug(f"Assigned protocol {protocol}, step {step} to subject {subject}")

        else:
            self.logger.debug('reassign cancelled')

    def calibrate_ports(self):
        """
        Calibrate :class:`.hardware.gpio.Solenoid` objects.

        See :class:`.gui.Calibrate_Water`.

        After calibration routine, send results to pilot for storage.
        """

        calibrate_window = Calibrate_Water(self.pilots)
        calibrate_window.exec_()

        if calibrate_window.result() == 1:
            for pilot, p_widget in calibrate_window.pilot_widgets.items():
                p_results = p_widget.volumes
                # p_results are [port][dur] = {params} so running the same duration will
                # overwrite a previous run. unnest here so pi can keep a record
                unnested_results = {}
                for port, result in p_results.items():
                    unnested_results[port] = []
                    # result is [dur] = {params}
                    for dur, inner_result in result.items():
                        inner_result['dur'] = dur
                        unnested_results[port].append(inner_result)

                # send to pi
                self.node.send(to=pilot, key="CALIBRATE_RESULT",
                               value = unnested_results)

            msgbox = QtWidgets.QMessageBox()
            msgbox.setText("Calibration results sent!")
            msgbox.exec_()

    def test_bandwidth(self):
        """
        Test bandwidth of Pilot connection with variable sized arrays as paylods

        See :class:`.gui.Bandwidth_Test`

        """
        # turn off logging while we run
        # prev_networking_loglevel = self.networking.logger.level
        # prev_node_loglevel = self.node.logger.level
        # self.networking.logger.setLevel(logging.ERROR)
        # self.node.logger.setLevel(logging.ERROR)

        bandwidth_test = Bandwidth_Test(self.pilots)
        bandwidth_test.exec_()

        # self.networking.logger.setLevel(prev_networking_loglevel)
        # self.node.logger.setLevel(prev_node_loglevel)

    def plot_psychometric(self):
        """
        Select subject, step, and variables to plot a psychometric curve

        """

        if not IMPORTED_VIZ:
            _ = pop_dialog("Vizualisation function couldn't be imported!", "error", VIZ_ERROR)
            return

        psychometric_dialog = Psychometric(self.subject_protocols)
        psychometric_dialog.exec_()

        # if user cancels, return
        if psychometric_dialog.result() != 1:
            return

        chart = viz.plot_psychometric(psychometric_dialog.plot_params)

        text, ok = QtGui.QInputDialog.getText(self, 'save plot?', 'what to call this thing')
        if ok:
            chart.save(text)


        #chart.serve()

            #viz.plot_psychometric(self.subjects_protocols)
        #result = psychometric_dialog.exec_()

    def manage_plugins(self):
        plugs = Plugins()
        plugs.exec_()

    def stream_video(self):
        """
        Open a window to stream videos from a connected pilot.

        Choose from connected pilots and configured :class:`~.hardware.cameras.Camera` objects
        (``prefs.json`` sent by Pilots in :meth:`.Pilot.handshake` ). Stream video, save to file.

        .. todo::

            Configure camera parameters!!!
        """

        video_dialog = Stream_Video(self.pilots)

    def closeEvent(self, event):
        """
        When Closing the Terminal Window, close any running subject objects,
        'KILL' our networking object.
        """
        # Save the window geometry, to be optionally restored next time
        self.settings.setValue("geometry", self.saveGeometry())

        # TODO: Check if any subjects are currently running, pop dialog asking if we want to stop

        # Close all subjects files
        for m in self.subjects.values():
            if m.running is True:
                m.stop_run()

        # Stop networking
        # send message to kill networking process
        self.node.send(key="KILL")
        time.sleep(0.5)
        self.node.release()
        self.logger.debug("Released net node and sent kill message to station")

        event.accept()

# Create the QApplication and run it
# Prefs were already loaded at the very top
if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    #app.setGraphicsSystem("opengl")
    app.setStyle('GTK+') # Keeps some GTK errors at bay
    ex = Terminal()
    sys.exit(app.exec())
