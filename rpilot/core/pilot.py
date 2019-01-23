#!/usr/bin/python2.7

'''
Drives the Raspberry Pi

Sets up & coordinates the multiple threads needed to function as a standalone taskontrol client
    -State Control: Managing box I/O and the state matrix
    -Audio Server
    -Communication w/ home terminal via TCP/IP
'''

__version__ = '0.2'
__author__ = 'Jonny Saunders <jsaunder@uoregon.edu>'

import os
import sys
import datetime
import logging
import json
import argparse
import threading
import time
import socket

import tables

# TODO: This is lazy, make the paths work.
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import prefs

if __name__ == '__main__':
    # Parse arguments - this should have been called with a .json prefs file passed
    # We'll try to look in the default location first
    parser = argparse.ArgumentParser(description="Run an RPilot")
    parser.add_argument('-f', '--prefs', help="Location of .json prefs file (created during setup_terminal.py)")
    args = parser.parse_args()

    if not args.prefs:
        prefs_file = '/usr/rpilot/prefs.json'

        if not os.path.exists(prefs_file):
            raise Exception("No Prefs file passed, and file not in default location")

        raise Warning('No prefs file passed, loaded from default location. Should pass explicitly with -p')

    else:
        prefs_file = args.prefs

    prefs.init(prefs_file)
    sys.path.append(os.path.dirname(prefs.REPODIR))

    if hasattr(prefs, 'AUDIOSERVER'):
        if prefs.AUDIOSERVER == 'pyo':
            pass
        elif prefs.AUDIOSERVER == 'jack':
            from rpilot.stim.sound import jackclient, pyoserver

from networking import Pilot_Networking, Net_Node
from rpilot import tasks, prefs
import hardware


########################################

class RPilot:
    logger = None
    log_handler = None
    log_formatter = None

    # Events for thread handling
    running = None
    stage_block = None
    file_block = None

    # networking - our internal and external messengers
    node = None
    networking = None

    def __init__(self):
        self.name = prefs.NAME

        self.init_logging()

        # Locks, etc. for threading
        self.running = threading.Event() # Are we running a task?
        self.stage_block = threading.Event() # Are we waiting on stage triggers?
        self.file_block = threading.Event() # Are we waiting on file transfer?

        # Init audio server
        if hasattr(prefs, 'AUDIOSERVER'):
            self.init_audio()

        # Init Networking
        # Listen dictionary - what do we do when we receive different messages?
        self.listens = {
            'START': self.l_start, # We are being passed a task and asked to start it
            'STOP' : self.l_stop, # We are being asked to stop running our task
            'PARAM': self.l_param, # A parameter is being changes
            'LVLUP': self.l_levelup, # The mouse has leveled up! (combines stop/start)
        }

        # spawn_network gives us the independent message-handling process
        self.networking = Pilot_Networking()
        self.networking.start()
        self.node = Net_Node(id = "_{}".format(self.name),
                             upstream = self.name,
                             port = prefs.MSGPORT,
                             listens = self.listens,
                             instance=False)

        # if we need to set pins pulled up or down, do that now
        self.pulls = []
        if hasattr(prefs, 'PULLUPS'):
            for pin in prefs.PULLUPS:
                self.pulls.append(hardware.Pull(int(pin), pud=int(1)))
        if hasattr(prefs, 'PULLDOWNS'):
            for pin in prefs.PULLDOWNS:
                self.pulls.append(hardware.Pull(int(pin), pud=int(0)))

        # Set and update state
        self.state = 'IDLE' # or 'Running'
        self.update_state()

        # Since we're starting up, handshake to introduce ourselves
        self.ip = self.get_ip()
        self.handshake()

        #self.blank_LEDs()

        # TODO Synchronize system clock w/ time from terminal.

    def init_logging(self):
        # Start Logging
        timestr = datetime.datetime.now().strftime('%y%m%d_%H%M%S')
        log_file = os.path.join(prefs.LOGDIR, 'Pilots_Log_{}.log'.format(timestr))

        self.logger = logging.getLogger('main')
        self.log_handler = logging.FileHandler(log_file)
        self.log_formatter = logging.Formatter("%(asctime)s %(levelname)s : %(message)s")
        self.log_handler.setFormatter(self.log_formatter)
        self.logger.addHandler(self.log_handler)
        self.logger.setLevel(logging.INFO)
        self.logger.info('Pilot Logging Initiated')

    #################################################################
    # Networking
    #################################################################

    def get_ip(self):
        # shamelessly stolen from https://www.w3resource.com/python-exercises/python-basic-exercise-55.php
        # variables are badly named because this is just a rough unwrapping of what was a monstrous one-liner

        # get ips that aren't the loopback
        unwrap00 = [ip for ip in socket.gethostbyname_ex(socket.gethostname())[2] if not ip.startswith("127.")][:1]
        # ???
        unwrap01 = [[(s.connect(('8.8.8.8', 53)), s.getsockname()[0], s.close()) for s in [socket.socket(socket.AF_INET, socket.SOCK_DGRAM)]][0][1]]

        unwrap2 = [l for l in (unwrap00,unwrap01) if l][0][0]

        return unwrap2

    def handshake(self):
        # send the terminal some information about ourselves
        hello = {'pilot':self.name, 'ip':self.ip}
        self.node.send('T', 'ALIVE', value=hello)

    def update_state(self):
        self.node.send('T', 'STATE', self.state)

    def l_start(self, value):
        """
        Args:
            value:
        """
        # TODO: If any of the sounds are 'file,' make sure we have them. If not, request them.
        # Value should be a dict of protocol params
        # The networking object should have already checked that we have all the files we need

        # Get the task object by its type
        task_class = tasks.TASK_LIST[value['task_type']]
        # Instantiate the task
        self.stage_block.clear()
        self.task = task_class(stage_block=self.stage_block, **value)

        # Make a group for this mouse if we don't already have one
        self.mouse = value['mouse']

        # Run the task and tell the terminal we have
        self.running.set()
        threading.Thread(target=self.run_task).start()

        self.state = 'RUNNING'
        self.update_state()

        # TODO: Send a message back to the terminal with the runtime if there is one so it can handle timed stops

    def l_stop(self, value):
        """
        Args:
            value:
        """
        # Let the terminal know we're stopping
        # (not stopped yet because we'll still have to sync data, etc.)
        self.state = 'STOPPING'
        self.update_state()

        # We just clear the stage block and reset the running flag here
        # and call the cleanup routine from run_task so it can exit cleanly
        self.running.clear()
        self.stage_block.set()


        # TODO: Cohere here before closing file
        if hasattr(self, 'h5f'):
            self.h5f.close()

    def l_param(self, value):
        """
        Args:
            value:
        """
        pass

    def l_levelup(self, value):
        """
        Args:
            value:
        """
        pass

    #################################################################
    # Hardware Init
    #################################################################

    def init_audio(self):
        if prefs.AUDIOSERVER == 'pyo':
            self.server = pyoserver.pyo_server()
            self.logger.info("pyo server started")
        elif prefs.AUDIOSERVER == 'jack':
            self.server = jackclient.JackClient()
            self.server.start()

    def blank_LEDs(self):
        # TODO: For some reason this dont work
        if 'LEDS' not in prefs.PINS.keys():
            return

        for position, pins in prefs.PINS['LEDS'].items():
            led = hardware.LED_RGB(pins=pins)
            time.sleep(1.)
            led.set_color(col=[0,0,0])
            led.release()

    #################################################################
    # Trial Running and Management
    #################################################################
    def open_file(self):
        # Setup a table to store data locally
        # Get data table descriptor
        table_descriptor = self.task.TrialData

        local_file = os.path.join(prefs.DATADIR, 'local.h5')
        h5f = tables.open_file(local_file, mode='a')

        try:
            h5f.create_group("/", self.mouse, "Local Data for {}".format(self.mouse))
        except tables.NodeError:
            # already made it
            pass
        mouse_group = h5f.get_node('/', self.mouse)

        # Make a table for today's data, appending a conflict-avoidance int if one already exists
        datestring = datetime.date.today().isoformat()
        conflict_avoid = 0
        while datestring in mouse_group:
            conflict_avoid += 1
            datestring = datetime.date.today().isoformat() + '-' + str(conflict_avoid)

        table = h5f.create_table(mouse_group, datestring, table_descriptor,
                                           "Mouse {} on {}".format(self.mouse, datestring))

        # The Row object is what we write data into as it comes in
        row = table.row
        return h5f, table, row

    def run_task(self):
        # TODO: give a net node to the Task class and let the task run itself.
        # Run as a separate thread, just keeps calling next() and shoveling data

        # do we expect TrialData?
        trial_data = False
        if hasattr(self.task, 'TrialData'):
            trial_data = True

        # Open local file for saving
        h5f, table, row = self.open_file()

        # TODO: Init sending continuous data here


        while True:
            # Calculate next stage data and prep triggers
            data = self.task.stages.next()() # Double parens because next just gives us the function, we still have to call it

            # Send data back to terminal (mouse is identified by the networking object)
            self.node.send('T', 'DATA', data)

            # Store a local copy
            # the task class has a class variable DATA that lets us know which data the row is expecting
            if trial_data:
                for k, v in data.items():
                    if k in self.task.TrialData.columns.keys():
                        row[k] = v

            # If the trial is over (either completed or bailed), flush the row
            if 'TRIAL_END' in data.keys():
                row.append()
                table.flush()

            # Wait on the stage lock to clear
            self.stage_block.wait()

            # If the running flag gets set, we're closing.
            if not self.running.is_set():
                self.task.end()
                self.task = None
                row.append()
                table.flush()
                break

        h5f.flush()
        h5f.close()

if __name__ == "__main__":

    a = RPilot()








