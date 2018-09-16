#!/usr/bin/python2.7

'''
Drives the Raspberry Pi

Sets up & coordinates the multiple threads needed to function as a standalone taskontrol client
    -State Control: Managing box I/O and the state matrix
    -Audio Server
    -Communication w/ home terminal via TCP/IP
'''

__version__ = '0.1'
__author__ = 'Jonny Saunders <jsaunder@uoregon.edu>'

import os
import sys
import datetime
import logging
import json
import argparse
import threading
import time
import multiprocessing
import socket

import pyo
import tables

import zmq
from zmq.eventloop.ioloop import IOLoop
from zmq.eventloop.zmqstream import ZMQStream

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from networking import Pilot_Networking
import tasks

########################################

class RPilot:

    def __init__(self, prefs=None):
        # If we weren't handed prefs, try to load them from the default location
        if not prefs:
            prefs_file = '/usr/rpilot/prefs.json'
            if not os.path.exists(prefs_file):
                raise RuntimeError("No prefs file passed and none found in {}".format(prefs_file))

            with open(prefs_file) as prefs_file_open:
                prefs = json.load(prefs_file_open)
                raise Warning('No prefs file passed, loaded from default location. Should pass explicitly')

        self.prefs = prefs
        self.name = self.prefs['NAME']

        # Start Logging
        timestr = datetime.datetime.now().strftime('%y%m%d_%H%M%S')
        log_file = os.path.join(self.prefs['LOGDIR'], 'Pilots_Log_{}.log'.format(timestr))

        self.logger = logging.getLogger('main')
        self.log_handler = logging.FileHandler(log_file)
        self.log_formatter = logging.Formatter("%(asctime)s %(levelname)s : %(message)s")
        self.log_handler.setFormatter(self.log_formatter)
        self.logger.addHandler(self.log_handler)
        self.logger.setLevel(logging.INFO)
        self.logger.info('Pilot Logging Initiated')

        # Open .h5 used to store local copies of data
        # NOTE: THESE ARE NOT TO BE RELIED ON FOR STORAGE,
        # Their purpose is to compare with the terminal at the end of running a task
        # in case the terminal missed us sending any events.
        #local_file = os.path.join(self.prefs['DATADIR'], 'local.h5')
        #self.h5f = tables.open_file(local_file, mode='a')
        #self.logger.info('Local file opened: {}'.format(local_file))

        # Locks, etc. for threading
        self.running = threading.Event() # Are we running a task?
        self.stage_block = threading.Event() # Are we waiting on stage triggers?
        self.file_block = threading.Event()

        # Init pyo server
        self.init_pyo()

        # Init Networking
        # Listen dictionary - what do we do when we receive different messages?
        self.listens = {
            'START': self.l_start, # We are being passed a task and asked to start it
            'STOP' : self.l_stop, # We are being asked to stop running our task
            'PARAM': self.l_param, # A parameter is being changes
            'LVLUP': self.l_levelup, # The mouse has leveled up! (combines stop/start)
        }
        self.context = None
        self.loop    = None
        self.pusher = None
        self.listener = None
        self.spawn_network()
        self.init_network()

        # Set and update state
        self.state = 'IDLE' # or 'Running'
        self.update_state()

        # Since we're starting up, handshake to introduce ourselves
        self.ip = self.get_ip()
        self.handshake()

        # TODO Synchronize system clock w/ time from terminal.


    #################################################################
    # Networking
    #################################################################

    def spawn_network(self):
        # Spawn the networking object as a separate process
        self.networking = Pilot_Networking(name=self.name, prefs=self.prefs)
        self.networking.start()

    def init_network(self):
        # Start internal communications
        self.context = zmq.Context()
        self.loop = IOLoop.instance()

        # Pusher sends messages to the network object
        # listener receives them
        self.pusher = self.context.socket(zmq.PUSH)
        self.listener  = self.context.socket(zmq.PULL)

        self.pusher.connect('tcp://localhost:{}'.format(self.prefs['MSGINPORT']))
        self.listener.connect('tcp://localhost:{}'.format(self.prefs['MSGOUTPORT']))

        # Setup listener for looping
        self.listener = ZMQStream(self.listener, self.loop)
        self.listener.on_recv(self.handle_listen)

        # Start IOLoop in daemon thread
        self.loop_thread = threading.Thread(target=self.loop.start)
        self.loop_thread.daemon = True
        self.loop_thread.start()

        self.logger.info("Networking Initialized")

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
        self.send_message('ALIVE', target='T', value=hello)

    def handle_listen(self, msg):
        # Messages are single part json-encoded messages
        msg = json.loads(msg[0])
        if isinstance(msg, unicode or basestring):
            msg = json.loads(msg)

        if not all(i in msg.keys() for i in ['key', 'value']):
            self.logger.warning('MESSAGE Improperly formatted: {}'.format(msg))
            return

        self.logger.info('MESSAGE - KEY: {}, VALUE: {}'.format(msg['key'], msg['value']))

        listen_funk = self.listens[msg['key']]
        listen_thread = threading.Thread(target=listen_funk, args=(msg['value'],))
        listen_thread.start()

    def send_message(self, key, target='', value=''):
        msg = {'key':key, 'target':target, 'value':value}

        msg_thread = threading.Thread(target=self.pusher.send_json, args=(json.dumps(msg),))
        msg_thread.start()

        self.logger.info("MESSAGE SENT - Target: {}, Key: {}, Value: {}".format(key, target, value))


    def l_start(self, value):
        # TODO: If any of the sounds are 'file,' make sure we have them. If not, request them.
        # Value should be a dict of protocol params
        # The networking object should have already checked that we have all the files we need

        # Get the task object by its type
        task_class = tasks.TASK_LIST[value['task_type']]
        # Instantiate the task
        self.task = task_class(prefs=self.prefs, stage_block=self.stage_block, **value)

        # Setup a table to store data locally
        # Get data table descriptor
        table_descriptor = self.task.TrialData

        # Make a group for this mouse if we don't already have one
        self.mouse = value['mouse']
        local_file = os.path.join(self.prefs['DATADIR'], 'local.h5')
        self.h5f = tables.open_file(local_file, mode='a')

        try:
            self.h5f.create_group("/", self.mouse, "Local Data for {}".format(self.mouse))
        except tables.NodeError:
            # already made it
            pass
        mouse_group = self.h5f.get_node('/', self.mouse)

        # Make a table for today's data, appending a conflict-avoidance int if one already exists
        datestring = datetime.date.today().isoformat()
        conflict_avoid = 0
        while datestring in mouse_group:
            conflict_avoid += 1
            datestring = datetime.date.today().isoformat() + '-' + str(conflict_avoid)

        self.table = self.h5f.create_table(mouse_group, datestring, table_descriptor,
                                           "Mouse {} on {}".format(self.mouse, datestring))

        # The Row object is what we write data into as it comes in
        self.row = self.table.row

        # Run the task and tell the terminal we have
        self.running.set()
        threading.Thread(target=self.run_task).start()

        self.state = 'RUNNING'
        self.update_state()

        # TODO: Send a message back to the terminal with the runtime if there is one so it can handle timed stops



    def l_stop(self, value):
        # Let the terminal know we're stopping
        # (not stopped yet because we'll still have to sync data, etc.)
        self.state = 'STOPPING'
        self.update_state()

        # We just clear the stage block and reset the running flag here
        # and call the cleanup routine from run_task so it can exit cleanly
        self.running.clear()
        self.stage_block.set()

        # TODO: Cohere here before closing file
        self.h5f.close()


    def l_param(self, value):
        pass

    def l_levelup(self, value):
        pass


    def update_state(self):
        self.send_message('STATE', target='T', value = self.state)
    #################################################################
    # Hardware Init
    #################################################################

    def init_pyo(self):
        # Jackd should already be running from the launch script created by setup_pilot, we we just
        self.pyo_server = pyo.Server(audio='jack', nchnls=int(self.prefs['NCHANNELS']), duplex=0)

        # Deactivate MIDI because we don't use it and it's expensive
        self.pyo_server.deactivateMidi()

        # We have to set pyo to not automatically try to connect to inputs when there aren't any
        self.pyo_server.setJackAuto(False, True)

        # Then boot and start
        self.pyo_server.boot()
        self.pyo_server.start()

        self.logger.info("pyo server started")

    #################################################################
    # Trial Running and Management
    #################################################################
    def run_task(self):
        # Run as a separate thread, just keeps calling next() and shoveling data

        # do we expect TrialData?
        trial_data = False
        if hasattr(self.task, 'TrialData'):
            trial_data = True

        # TODO: Init sending continuous data here


        while True:
            # Calculate next stage data and prep triggers
            data = self.task.stages.next()() # Double parens because next just gives us the function, we still have to call it

            # Send data back to terminal (mouse is identified by the networking object)
            self.send_message('DATA', target='T', value=data)

            # Store a local copy
            # the task class has a class variable DATA that lets us know which data the row is expecting
            if trial_data:
                for k, v in data.items():
                    if k in self.task.TrialData.columns.keys():
                        self.row[k] = v

            # If the trial is over (either completed or bailed), flush the row
            if 'TRIAL_END' in data.keys():
                self.row.append()
                self.table.flush()

            # Wait on the stage lock to clear
            self.stage_block.wait()

            # If the running flag gets set, we're closing.
            if not self.running.is_set():
                # TODO: Call task shutdown method
                self.row.append()
                self.table.flush()
                break


class Pyo_Process(multiprocessing.Process):
    def __init__(self, channels=2):
        super(Pyo_Process, self).__init__()
        self.channels = channels
        self.daemon = False
        self.kill_event = multiprocessing.Event()
        self.server = None

    def run(self):
        self.start_server()
        #self.keep_alive_thread = threading.Thread(target=self.keep_alive)
        #self.keep_alive_thread.start()
        #self.keep_alive_thread.join()
        while not self.kill_event.is_set():
            time.sleep(1)

        self.server.stop()
        print('pyo server process has been killed')


    def start_server(self):
        self.server = pyo.Server(audio='jack', nchnls=self.channels, duplex=0)
        self.server.setJackAuto(False, True)
        self.server.boot()
        self.server.start()
        # keep alive
        #threading.Timer(1, self.keep_alive).start()
        #self.live_thread = threading.Thread(target=self.keep_alive)
        #self.live_thread.start()

        #while not self.kill:
        #    time.sleep(1)

    def keep_alive(self):
        while not self.kill_event.is_set():
            time.sleep(1)

    def kill(self):
        self.kill_event.set()






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

    with open(prefs_file) as prefs_file_open:
        prefs = json.load(prefs_file_open)

    a = RPilot(prefs)








