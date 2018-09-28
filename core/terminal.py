# The terminal is the user-facing GUI that controls the Pis

__version__ = '0.1'
__author__  = 'Jonny Saunders <JLSaunders987@gmail.com'

import argparse
import json
import sys
import os
import datetime
import logging
import threading
import time
from collections import OrderedDict as odict
import numpy as np

from PySide import QtCore, QtGui
import zmq
from zmq.eventloop.ioloop import IOLoop
from zmq.eventloop.zmqstream import ZMQStream

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mouse import Mouse
from plots import Plot_Widget
from networking import Terminal_Networking
import tasks
import sounds
from utils import InvokeEvent, Invoker
from gui import Control_Panel, Protocol_Wizard, Popup, Weights

# TODO: Oh holy hell just rewrite all the inter-widget communication as zmq
# TODO: Be more complete about generating logs
# TODO: Make exit graceful
# TODO: Make 'edit mouse' button
# TODO: Make experiment tags, save and populate?

# http://zetcode.com/gui/pysidetutorial/layoutmanagement/
# https://wiki.qt.io/PySide_Tutorials


class Terminal(QtGui.QMainWindow):
    '''
    GUI for RPilot Terminal
    '''
    ## Declare attributes
    prefs = None

    # networking
    context       = None
    loop          = None
    pusher        = None
    listener      = None
    networking    = None
    networking_ok = False

    # data
    rows = None  # handles to row writing functions
    mice = {}  # Dict of our open mouse objects
    current_mouse = None  # ID of mouse currently in params panel
    pilots = None

    # gui
    widget = None

    def __init__(self, prefs):
        # Initialize the superclass (QtGui.QWidget)
        super(Terminal, self).__init__()

        # set central widget
        self.widget = QtGui.QWidget()
        self.setCentralWidget(self.widget)

        # Get prefs dict
        self.prefs = prefs

        # Load pilots db as ordered dictionary
        with open(self.prefs['PILOT_DB']) as pilot_file:
            self.pilots = json.load(pilot_file, object_pairs_hook=odict)



        # Start Logging
        timestr = datetime.datetime.now().strftime('%y%m%d_%H%M%S')
        log_file = os.path.join(prefs['LOGDIR'], 'Terminal_Log_{}.log'.format(timestr))

        self.logger        = logging.getLogger('main')
        self.log_handler   = logging.FileHandler(log_file)
        self.log_formatter = logging.Formatter("%(asctime)s %(levelname)s : %(message)s")
        self.log_handler.setFormatter(self.log_formatter)
        self.logger.addHandler(self.log_handler)
        self.logger.setLevel(logging.INFO)
        self.logger.info('Terminal Logging Initiated')

        # Listen dictionary - which methods to call for different messages
        # Methods are spawned in new threads using handle_message
        self.listens = {
            'STATE': self.l_state, # A Pi has changed state
            'PING' : self.l_ping,  # Someone wants to know if we're alive
            'FILE' : self.l_file,  # A pi needs some files to run its protocol
            'DATA' : self.l_data,   # data 4 us!
            'ALIVE': self.l_alive  # pi is responding to our ping, or telling us its info
        }

        # Make invoker object to send GUI events back to the main thread
        self.invoker = Invoker()

        # Start GUI
        self.layout = QtGui.QGridLayout()
        self.layout.setSpacing(0)
        self.layout.setContentsMargins(0,0,0,0)
        self.widget.setLayout(self.layout)

        self.setWindowTitle('Terminal')
        self.initUI() # Has to be before networking so plot listeners are caught by IOLoop


        # Start Networking
        # Networking is in two parts,
        # "internal" networking for messages sent to and from the Terminal object itself
        # "external" networking for messages to and from all the other components,
        # The split is so the external networking can run in another process, do potentially time-consuming tasks
        # like resending & confirming message delivery without blocking or missing messages
        self.init_network()  # start "internal" networking
        self.spawn_network() # Has to be after init_network so it makes a new context

        self.popups = []
        #time.sleep(1)



    def initUI(self):
        # Main panel layout
        #self.panel_layout.setContentsMargins(0,0,0,0)

        # Init toolbar
        # File menu
        self.file_menu = self.menuBar().addMenu("&File")
        new_pilot_act = QtGui.QAction("New &Pilot", self, triggered=self.new_pilot)
        new_prot_act  = QtGui.QAction("New Pro&tocol", self, triggered=self.new_protocol)
        batch_create_mice = QtGui.QAction("Batch &Create Mice", self, triggered=self.batch_mice)
        # TODO: Update pis
        self.file_menu.addAction(new_pilot_act)
        self.file_menu.addAction(new_prot_act)
        self.file_menu.addAction(batch_create_mice)

        # Tools menu
        self.tool_menu = self.menuBar().addMenu("&Tools")
        mouse_weights_act = QtGui.QAction("View Mouse &Weights", self, triggered=self.mouse_weights)
        update_protocol_act = QtGui.QAction("Update Protocols", self, triggered=self.update_protocols)
        self.tool_menu.addAction(mouse_weights_act)
        self.tool_menu.addAction(update_protocol_act)

        # Set size of window to be fullscreen without maximization
        # Until a better solution is found, if not set large enough, the pilot tabs will
        # expand into infinity. See the Expandable_Tabs class
        titleBarHeight = self.style().pixelMetric(QtGui.QStyle.PM_TitleBarHeight,
            QtGui.QStyleOptionTitleBar(), self)
        winsize = app.desktop().availableGeometry()
        # Then subtract height of titlebar
        winheight = winsize.height()-titleBarHeight*2
        winsize.setHeight(winheight)
        self.setGeometry(winsize)
        self.setSizePolicy(QtGui.QSizePolicy.Maximum,QtGui.QSizePolicy.Maximum)

        ## Init main panels and add to layout
        # Control panel sits on the left, controls pilots & mice
        self.control_panel = Control_Panel(pilots=self.pilots,
                                           mice=self.mice,
                                           msg_fn=self.send_message,
                                           prefs=self.prefs)

        # Data panel sits on the right, plots stuff.
        self.data_panel = Plot_Widget(prefs=self.prefs,
                                      invoker=self.invoker)
        self.data_panel.init_plots(self.pilots.keys())

        # Set heights on control panel and data panel
        self.control_panel.setMaximumHeight(winheight)
        self.data_panel.setMaximumHeight(winheight)

        # Logo goes up top
        self.logo = QtGui.QLabel()
        self.logo.setPixmap(QtGui.QPixmap(prefs['REPODIR']+'/graphics/logo.png').scaled(265,40))
        self.logo.setFixedHeight(40)
        self.logo.setAlignment(QtCore.Qt.AlignLeft)

        # Combine all in main layout
        self.layout.addWidget(self.logo, 0,0,1,1)
        self.layout.addWidget(self.control_panel, 1,0,1,1)
        self.layout.addWidget(self.data_panel, 0,1,2,1)
        self.layout.setColumnStretch(0, 2)
        self.layout.setColumnStretch(1, 10)

        self.show()
        logging.info('UI Initialized')

    def reset_ui(self):
        self.layout = QtGui.QGridLayout()
        self.layout.setSpacing(0)
        self.layout.setContentsMargins(0,0,0,0)
        self.widget.setLayout(self.layout)
        self.setCentralWidget(self.widget)
        self.initUI()


    ##########################
    # MOUSE DATA METHODS
    #
    # def mouse_start_toggled(self, toggled):
    #     # Get object for current mouse
    #     mouse = self.mice[self.current_mouse]
    #     pilot = bytes(self.pilot_panel.pilot)
    #
    #     # If toggled=True we are starting the mouse
    #     if toggled:
    #         # Set mouse to running
    #         mouse.prepare_run()
    #         # Get protocol and send it to the pi
    #         task = mouse.current[mouse.step]
    #         # Dress up the protocol dict with some extra values that the pilot needs
    #         task['mouse'] = mouse.name
    #         # TODO: Get last trial number and insert in dict
    #         self.send_message('START', pilot, task)
    #         # TODO: Spawn timer thread to trigger stop after run duration
    #
    #     # Or else we are stopping the mouse
    #     else:
    #         mouse.running = False
    #         self.send_message('STOP', pilot)
    #         mouse.h5f.flush()
    #         # TODO: Destroy dataview widget

    # def stop_mouse(self):
    #     # TODO flush table, handle coherence checking, close .h5f
    #     pass

    ##########################3
    # NETWORKING METHODS

    def spawn_network(self):
        # Start external communications in own process
        self.networking = Terminal_Networking()
        self.networking.start()

    def init_network(self):
        # Start internal communications
        self.context = zmq.Context.instance()
        self.loop = IOLoop.instance()

        # Messenger to send messages to networking class
        # Subscriber to receive return messages
        self.pusher      = self.context.socket(zmq.PUSH)
        self.subscriber  = self.context.socket(zmq.SUB)

        self.pusher.connect('tcp://localhost:{}'.format(prefs['MSGPORT']))
        self.subscriber.connect('tcp://localhost:{}'.format(prefs['PUBPORT']))
        self.subscriber.setsockopt(zmq.SUBSCRIBE, b'T') # Subscribe as "T"erminal
        self.subscriber.setsockopt(zmq.SUBSCRIBE, b'X') # Subscribe to All

        # Setup subscriber for looping
        self.subscriber = ZMQStream(self.subscriber, self.loop)
        self.subscriber.on_recv(self.handle_listen)

        # Start IOLoop in daemon thread
        self.loop_thread = threading.Thread(target=self.threaded_loop)
        self.loop_thread.daemon = True
        self.loop_thread.start()

        self.logger.info("Networking Initiated")

    def threaded_loop(self):
        while True:
            self.logger.info("Starting IOLoop")
            self.loop.start()

    def handle_listen(self, msg):
        # Listens are multipart target-msg messages
        # target = msg[0]
        # 'key' determines which method is called, 'value' is passed to the method.
        try:
            message = json.loads(msg[1])
        except ValueError:
            self.logger.exception('TERMINAL: Error decoding message')
            return

        if not all(i in message.keys() for i in ['key', 'value']):
            self.logger.warning('LISTEN Improperly formatted: {}'.format(msg))
            return

        self.logger.info('LISTEN {} - KEY: {}, VALUE: {}'.format(message['id'], message['key'], message['value']))

        listen_funk = self.listens[message['key']]
        listen_thread = threading.Thread(target=listen_funk, args=(message['value'],))
        listen_thread.start()

        # Tell the networking process that we got it
        self.send_message('RECVD', value=message['id'])

    def send_message(self, key, target='', value=''):
        msg = {'key': key, 'target': target, 'value': value}

        # Send in own thread -- sending via pusher blocks
        msg_thread = threading.Thread(target= self.pusher.send_json, args=(json.dumps(msg),))
        msg_thread.start()

        self.logger.info("MESSAGE SENT - Target: {}, Key: {}, Value: {}".format(target, key, value))

    ############################
    # MESSAGE HANDLING METHODS

    def l_state(self, value):
        # A Pi has changed state
        # TODO: If we are stopping, we enter into a cohere state
        # TODO: If we are stopped, close the mouse object.
        # TODO: Also tell the relevant dataview to clear
        pass

    def l_data(self, value):
        # A Pi has sent us data, let's save it huh?
        mouse_name = value['mouse']
        self.mice[mouse_name].save_data(value)
        if self.mice[mouse_name].did_graduate.is_set() is True:
            self.send_message('STOP', value['pilot'], {'graduation':True})
            self.mice[mouse_name].stop_run()
            self.mice[mouse_name].graduate()
            self.mice[mouse_name].prepare_run()

            protocol = self.mice[mouse_name].current
            step = self.mice[mouse_name].step
            task = protocol[step]
            task['mouse'] = mouse_name
            task['pilot'] = value['pilot']
            task['step'] = step
            task['current_trial'] = self.mice[mouse_name].current_trial
            task['session'] = self.mice[mouse_name].session
            self.send_message('START', value['pilot'], task)

    def l_ping(self, value):
        # TODO Not this
        pass
        #self.send_message('ALIVE', value=b'T')

    def l_file(self, value):
        pass

    def l_alive(self, value):
        if value['pilot'] in self.pilots.keys():
            self.pilots[value['pilot']]['ip'] = value['ip']

        else:
            self.new_pilot(name=value['pilot'], ip=value['ip'])

        self.control_panel.update_db()

    #############################
    # GUI & etc. methods

    def new_pilot(self, ip='', name=None):
        if name is None:
            name, ok = QtGui.QInputDialog.getText(self, "Pilot ID", "Pilot ID:")

        # make sure we won't overwrite ourself
        if name in self.pilots.keys():
            # TODO: Pop a window confirming we want to overwrite
            pass

        if name != '':
            self.pilots[name] = {'mice':[], 'ip':ip}
            self.control_panel.update_db()
            self.reset_ui()
        else:
            # Idk maybe pop a dialog window but i don't really see why
            pass

    def new_protocol(self):
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
                save_steps.append(param_values)

            # Name the protocol
            name, ok = QtGui.QInputDialog.getText(self, "Name Protocol", "Protocol Name:")
            if ok and name != '':
                protocol_file = os.path.join(prefs['PROTOCOLDIR'], name + '.json')
                with open(protocol_file, 'w') as pfile_open:
                    json.dump(save_steps, pfile_open)
            elif name == '' or not ok:
                placeholder_name = 'protocol_created_{}'.format(datetime.date.today().isoformat())
                protocol_file = os.path.join(prefs['PROTOCOLDIR'], placeholder_name + '.json')
                with open(protocol_file, 'w') as pfile_open:
                    json.dump(save_steps, pfile_open)

    def batch_mice(self):
        # TODO: Implement me...
        pass

    def list_mice(self):
        mice = []
        for pilot, vals in self.pilots.items():
            mice.extend(vals['mice'])
        return mice

    def mouse_weights(self):
        mice = self.list_mice()

        # open objects if not already
        for mouse in mice:
            if mouse not in self.mice.keys():
                self.mice[mouse] = Mouse(mouse)

        # for each mouse, get weight
        weights = []
        for mouse in mice:
            weight = self.mice[mouse].get_weight(include_baseline=True)
            weight['mouse'] = mouse
            weights.append(weight)

        self.weight_widget = Weights(weights)
        self.weight_widget.show()

    def update_protocols(self):
        # If we change the protocol file, update the stored version in mouse files

        # get list of protocol files
        protocols = os.listdir(self.prefs['PROTOCOLDIR'])
        protocols = [p for p in protocols if p.endswith('.json')]


        mice = self.list_mice()
        for mouse in mice:
            if mouse not in self.mice.keys():
                self.mice[mouse] = Mouse(mouse)

            protocol_bool = [self.mice[mouse].protocol_name == p.strip('.json') for p in protocols]
            if any(protocol_bool):
                which_prot = np.where(protocol_bool)[0][0]
                protocol = protocols[which_prot]
                self.mice[mouse].assign_protocol(os.path.join(self.prefs['PROTOCOLDIR'], protocol), step_n=self.mice[mouse].step)

        msgbox = QtGui.QMessageBox()
        msgbox.setText("Mouse Protocols Updated")
        msgbox.exec_()







    def gui_event(self, fn, *args, **kwargs):
        # Don't ask me how this works, stolen from
        # https://stackoverflow.com/a/12127115
        QtCore.QCoreApplication.postEvent(self.invoker, InvokeEvent(fn, *args, **kwargs))

    def closeEvent(self, event):
        # do stuff
        # TODO: Check if any mice are currently running, pop dialog asking if we want to stop

        # Close all mice files
        for m in self.mice.values():
            if m.running is True:
                m.stop_run()

        # Stop networking
        # send message to kill networking process
        self.send_message('KILL')

        #if can_exit:
        #    event.accept() # let the window close
        #else:
        #    event.ignore()

if __name__ == '__main__':
    # Parse arguments - this should have been called with a .json prefs file passed
    # We'll try to look in the default location first
    parser = argparse.ArgumentParser(description="Run an RPilot Terminal")
    parser.add_argument('-f', '--prefs', help="Location of .json prefs file (created during setup_terminal.py)")
    args = parser.parse_args()

    if not args.prefs:
        prefs_file = '/usr/rpilot/prefs.json'

        if not os.path.exists(prefs_file):
            raise Exception("No Prefs file passed, and file not in default location")

        raise Warning('No prefs file passed, loaded from default location. Should pass explicitly with -p')

    else:
        prefs_file = args.prefs

    with open(prefs_file) as prefs_file_open:
        prefs = json.load(prefs_file_open)

    app = QtGui.QApplication(sys.argv)
    app.setStyle('plastique') # Keeps some GTK errors at bay
    ex = Terminal(prefs=prefs)
    sys.exit(app.exec_())


