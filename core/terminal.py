# The terminal is the user-facing GUI that controls the Pis

__version__ = '0.1'
__author__  = 'Jonny Saunders <JLSaunders987@gmail.com'

import argparse
import json
import sys
import os
import datetime
import copy
import logging
import threading
import multiprocessing
import time
from collections import OrderedDict as odict
from PySide import QtCore
from PySide import QtGui
from pprint import pprint
import pyqtgraph as pg
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
from gui import Control_Panel, Protocol_Wizard

# TODO: Oh holy hell just rewrite all the inter-widget communication as zmq
# TODO: Be more complete about generating logs
# TODO: Make exit graceful
# TODO: Make 'edit mouse' button
# TODO: Make experiment tags, save and populate?

# http://zetcode.com/gui/pysidetutorial/layoutmanagement/
# https://wiki.qt.io/PySide_Tutorials


class Terminal(QtGui.QWidget):
    '''
    GUI for RPilot Terminal
    '''

    def __init__(self, prefs):
        # Initialize the superclass (QtGui.QWidget)
        QtGui.QWidget.__init__(self)

        # Get prefs dict
        self.prefs = prefs

        # Load pilots db
        with open(self.prefs['PILOT_DB']) as pilot_file:
            self.pilots = json.load(pilot_file, object_pairs_hook=odict)

        # Declare attributes
        self.context = None
        self.loop    = None
        self.pusher = None
        self.listener  = None
        self.networking = None
        self.rows = None #handles to row writing functions
        self.networking_ok = False
        self.mice = {} # Dict of our open mouse objects
        self.current_mouse = None # ID of mouse currently in params panel

        # Start Logging
        timestr = datetime.datetime.now().strftime('%y%m%d_%H%M%S')
        log_file = os.path.join(prefs['LOGDIR'], 'Terminal_Log_{}.log'.format(timestr))

        self.logger = logging.getLogger('main')
        self.log_handler = logging.FileHandler(log_file)
        self.log_formatter = logging.Formatter("%(asctime)s %(levelname)s : %(message)s")
        self.log_handler.setFormatter(self.log_formatter)
        self.logger.addHandler(self.log_handler)
        self.logger.setLevel(logging.INFO)
        self.logger.info('Terminal Logging Initiated')

        # Make invoker object to send GUI events back to the main thread
        self.invoker = Invoker()

        # Start GUI
        self.setWindowTitle('Terminal')
        self.initUI() # Has to be before networking so plot listeners are caught by IOLoop

        # Start Networking

        self.init_network()
        self.spawn_network() # Has to be after init_network so it makes a new context

        time.sleep(1)

        #self.check_network()

    def initUI(self):
        # Main panel layout
        self.panel_layout = QtGui.QHBoxLayout()
        #self.panel_layout.setContentsMargins(0,0,0,0)

        # Init main panels and add to layout
        self.control_panel = Control_Panel(pilots=self.pilots,
                                           mice=self.mice,
                                           msg_fn=self.send_message,
                                           prefs=self.prefs)
        self.data_panel = Plot_Widget(prefs=self.prefs,
                                      invoker=self.invoker)
        self.data_panel.init_plots(self.pilots.keys())
        self.panel_layout.addWidget(self.control_panel)
        # Set a high stretch so it fills all space that control panel doesn't take up
        self.panel_layout.addWidget(self.data_panel, 10)

        # add logo and new protocol button in top strip
        self.logo = QtGui.QLabel()
        self.logo.setPixmap(QtGui.QPixmap(prefs['REPODIR']+'/graphics/logo.png').scaled(265,40))
        self.logo.setFixedHeight(40)
        self.logo.setAlignment(QtCore.Qt.AlignRight)
        self.new_protocol_button = QtGui.QPushButton("New Protocol")
        self.new_protocol_button.clicked.connect(self.new_protocol)
        self.new_protocol_button.setFixedHeight(40)
        self.connect_pilots_button = QtGui.QPushButton("Connect to Pilots")
        self.connect_pilots_button.clicked.connect(self.init_pilots)
        self.connect_pilots_button.setFixedHeight(40)
        top_strip = QtGui.QHBoxLayout()
        top_strip.setContentsMargins(0,0,0,0)
        top_strip.addWidget(self.new_protocol_button)
        top_strip.addWidget(self.connect_pilots_button)
        top_strip.addStretch(1)
        top_strip.addWidget(self.logo)

        # Combine all in main layout
        self.layout = QtGui.QVBoxLayout()
        self.layout.setContentsMargins(0,0,0,0)
        self.layout.addLayout(top_strip)
        self.layout.addLayout(self.panel_layout)
        self.setLayout(self.layout)

        # Set size of window to be fullscreen without maximization
        # Until a better solution is found, if not set large enough, the pilot tabs will
        # expand into infinity. See the Expandable_Tabs class
        titleBarHeight = self.style().pixelMetric(QtGui.QStyle.PM_TitleBarHeight,
            QtGui.QStyleOptionTitleBar(), self)
        winsize = app.desktop().availableGeometry()
        # Then subtract height of titlebar
        winsize.setHeight(winsize.height()-titleBarHeight*4)
        self.setGeometry(winsize)

        self.show()
        logging.info('UI Initialized')

    def mouse_start_toggled(self, toggled):
        # Get object for current mouse
        mouse = self.mice[self.current_mouse]
        pilot = bytes(self.pilot_panel.pilot)

        # If toggled=True we are starting the mouse
        if toggled:
            # Set mouse to running
            mouse.prepare_run()
            # Get protocol and send it to the pi
            task = mouse.current[mouse.step]
            # Dress up the protocol dict with some extra values that the pilot needs
            task['mouse'] = mouse.name
            # TODO: Get last trial number and insert in dict
            self.send_message('START', pilot, task)
            # TODO: Spawn dataview widget
            # TODO: Spawn timer thread to trigger stop after run duration

        # Or else we are stopping the mouse
        else:
            mouse.running = False
            self.send_message('STOP', pilot)
            mouse.h5f.flush()
            # TODO: Destroy dataview widget



    def stop_mouse(self):
        # TODO flush table, handle coherence checking, close .h5f
        pass

    ##########################3
    # NETWORKING METHODS

    def spawn_network(self):
        # Start external communications in own process
        self.networking = Terminal_Networking()
        self.networking.start()

    def init_network(self):
        # Start internal communications
        #self.context = zmq.Context()
        self.context = zmq.Context.instance()
        self.loop = IOLoop.instance()

        # Messenger to send messages to networking class
        # Subscriber to receive return messages
        self.pusher      = self.context.socket(zmq.PUSH)
        self.subscriber  = self.context.socket(zmq.SUB)

        self.pusher.connect('tcp://localhost:{}'.format(prefs['MSGPORT']))
        self.subscriber.connect('tcp://localhost:{}'.format(prefs['PUBPORT']))
        self.subscriber.setsockopt(zmq.SUBSCRIBE, b'T')
        self.subscriber.setsockopt(zmq.SUBSCRIBE, b'X')

        # Setup subscriber for looping
        self.subscriber = ZMQStream(self.subscriber, self.loop)
        self.subscriber.on_recv(self.handle_listen)

        # Listen dictionary - which methods to call for different messages
        self.listens = {
            'ALIVE': self.l_alive, # A Pi is telling us that it is alive
            'DEAD' : self.l_dead, # A Pi we requested is not responding
            'STATE': self.l_state, # A Pi has changed state
            'LISTENING': self.l_listening, # The networking object tells us it's online
            'PING' : self.l_ping, # Someone wants to know if we're alive
            'FILE' : self.l_file, # A pi needs some files to run its protocol
            'DATA' : self.l_data,
            'START': self.l_start # A mouse has been started
        }

        # Start IOLoop in daemon thread
        self.loop_thread = threading.Thread(target=self.threaded_loop)
        self.loop_thread.daemon = True
        self.loop_thread.start()

        self.logger.info("Networking Initiated")

    def threaded_loop(self):
        while True:
            self.logger.info("Starting IOLoop")
            self.loop.start()

    def check_network(self):
        # Let's see if the network is alive
        self.logger.info("Contacting Networking Object")
        attempts = 0
        while not self.networking_ok and attempts < 10:
            self.send_message('LISTENING')
            attempts += 1
            time.sleep(1)

        if not self.networking_ok:
            self.logger.warning("No response from network object")

    def init_pilots(self):
        self.logger.info('Initializing Pilots')
        self.send_message('INIT', value=self.pilots.keys())

    def handle_listen(self, msg):
        # Listens are multipart target-msg messages
        # target = msg[0]
        message = json.loads(msg[1])

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

        msg_thread = threading.Thread(target= self.pusher.send_json, args=(json.dumps(msg),))
        msg_thread.start()

        self.logger.info("MESSAGE SENT - Target: {}, Key: {}, Value: {}".format(target, key, value))

    def l_alive(self, value):
        # Change icon next to appropriate pilot button
        # If we have the value in our list of pilots...
        self.logger.info('arrived at gui setting, value: {}, pilots: {}'.format(value, self.pilots.keys()))
        if value in self.pilots.keys():
            self.logger.info('boolean passed')
            self.gui_event(self.pilot_panel.buttons[value].setStyleSheet, "background-color:green")
            self.logger.info('passed GUI setting')
            # TODO: maintain list of responsive pilots, only try to send 'start' to connected pilots
            #self.pilot_panel.buttons[value].setStyleSheet("background-color:green")
        else:
            self.logger.info('boolean failed, returning')
            return

    def l_dead(self, value):
        # Change icon next to appropriate pilot button
        # If we have the value in our list of pilots...
        if value in self.pilots.keys():
            self.gui_event(self.pilot_panel.buttons[value].setStyleSheet, "background-color:red")
            #self.pilot_panel.buttons[value].setStyleSheet("background-color:red")
        else:
            return

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

    def l_listening(self, value):
        self.networking_ok = True
        self.logger.info('Networking responds as alive')

    def l_ping(self, value):
        self.send_message('ALIVE', value=b'T')

        # TODO: Give params window handle to mouse panel's update params function
        # TODO: Give params window handle to Terminal's delete params function

    def l_file(self, value):
        pass

    def l_start(self, value):
        # Let the plot widget know we're starting a mouse
        self.data_panel.start_plotting(value)


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

    def gui_event(self, fn, *args, **kwargs):
        # Don't ask me how this works, stolen from
        # https://stackoverflow.com/a/12127115
        QtCore.QCoreApplication.postEvent(self.invoker, InvokeEvent(fn, *args, **kwargs))

    def closeEvent(self, event):
        # do stuff
        # TODO: Check if any mice are currently running, pop dialog asking if we want to stop

        # Close all mice files
        for m in self.mice.values():
            m.close_h5f()

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


