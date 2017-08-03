# Classes for network communication.
# Following http://zguide.zeromq.org/py:all#toc46

import json
import logging
import threading
import zmq
from zmq.eventloop.ioloop import IOLoop, PeriodicCallback
from zmq.eventloop.zmqstream import ZMQStream

# Message structure:
# Messages flow from the Terminal class to the raspberry pi
# {key: {target, value}}
# key - what type of message is this (byte string)
# target - where should it go (json encoded on receipt, converted to byte string)
# value - what is the message (json encoded)
# This structure allows us to sensibly 'unwrap' messages:
# the handler function for each socket passes the target and value to the appropriate function for a given key
# the key function will do whatever it needs to do with value and send it on to target

# Listens
# Listens flow from the raspberry pi to the terminal, so same structure but no need for target

# TODO: Periodically ping pis to check that they are still responsive

class Terminal_Networking:
    # Internal Variables/Objects to the Networking Object
    ctx          = None    # Context
    kvmap        = None    # Key-value store
    loop         = None    # IOLoop
    pub_port     = None    # Publisher Port
    listen_port  = None    # Listener Port
    message_port = None    # Messenger Port
    publisher    = None    # Publisher Handler - For sending messages to the pis
    listener     = None    # Listener Handler - For receiving data from the pis
    messenger    = None    # Messenger Handler - For receiving messages from the Terminal Class


    def __init__(self, prefs):
        self.pub_port = prefs['PUBPORT']
        self.listen_port = prefs['LISTENPORT']
        self.message_port = prefs['MESSAGEPORT']

        self.context = zmq.Context.instance()
        self.kvmap = {}
        self.loop = IOLoop.instance()
        # Publisher sends commands to Pilots
        # Subscriber listens for data from Pilots
        # Sync ensures pilots are ready for publishing
        self.publisher  = self.context.socket(zmq.PUB)
        self.listener = self.context.socket(zmq.PULL)
        self.messenger = self.context.socket(zmq.PAIR)
        #self.publisher.bind('tcp://*:{}'.format(self.pub_port))
        self.listener.connect('tcp://localhost:{}'.format(self.listen_port))
        self.messenger.connect('tcp://localhost:{}'.format(self.message_port))

        # Wrap as ZMQStreams
        #self.publisher = ZMQStream(self.publisher)
        self.listener  = ZMQStream(self.listener)
        self.messenger = ZMQStream(self.messenger)

        # Set on_recv action to handle data and messages
        self.listener.on_recv(self.handle_listen)
        self.messenger.on_recv(self.handle_message)

        # Message dictionary - What method to call for each type of message received by the terminal class
        self.messages = {
            'PING': self.m_ping,    # We are asked to confirm that we are alive
            'INIT': self.m_init,    # We should ask all the pilots to confirm that they are alive
            'START': self.m_start_task,  # Upload task to a pilot
            'CHANGE': self.m_change,  # Change a parameter on the Pi
            'STOP': self.m_stop,
            'STOPALL': self.m_stopall
        }

        # Listen dictionary - What to do with pushes from the raspberry pis
        self.listens = {
            'DATA': self.l_data, # Stash incoming data from an rpilot
            'ALIVE': self.l_alive, # A Pi is responding to our periodic query of whether it remains alive
            'EVENT': self.l_event # Stash a single event (not a whole trial's data)
        }

        self.mice_data = {} # maps the running mice to methods to stash their data

        # Log formatting
        logging.basicConfig(format="%(asctime)s %(message)s",
                            datefmt="%Y-%m-%d %H:%M%:S",
                            level=logging.INFO)

        # TODO: Get KVMsg from zexamples repo
        # TODO: Be passed method to write rows of data to mouse files

    def start(self):
        try:
            self.thread = threading.Thread(target=self.loop.start)
            self.thread.start()
        except KeyboardInterrupt:
            pass

    def stop(self):
        try:
            self.thread.stop()
        except:
            pass

    def publish(self, message):
        # If it's to all... use "X" or other nonspecific sub pattern
        # Otherwise send a message to a specific pi
        if len(message) != 3:
            print("Bad Message to Publish: {}".format(message))
            return
        elif len(message) == 3:
            # should have pi, a message field and the value

            pass

    def handle_listen(self, msg):
        # listens are always json encoded, single-part messages
        print(msg[0])
        msg = json.loads(msg[0])
        print(msg)
        self.listens[msg['key']](msg['value'])

    def handle_message(self):
        # messages are always json encoded, single-part messages.
        msg = json.loads(msg)
        self.messages[msg['key']](msg['target'], msg['value'])



    ##########################
    # Message Handling Methods

    def m_ping(self, target, value):
        print(target, value)

    def m_init(self, target, value):
        pass


    def m_start_task(self, target, value):
        pass


        # Start listening thread

    def m_change(self, target, value):
        pass


    def m_stop(self, target, value):
        # also pop mouse value from data function dict
        pass

    def m_stopall(self, target, value):
        pass

    def l_data(self,value):
        pass

    def l_alive(self, value):
        print(value)

    def l_event(self, value):
        pass

