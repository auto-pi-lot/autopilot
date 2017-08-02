# Classes for network communication.
# Following http://zguide.zeromq.org/py:all#toc46

import logging
import threading
import zmq
from zmq.eventloop.ioloop import IOLoop, PeriodicCallback
from zmq.eventloop.zmqstream import ZMQStream



class Terminal_Networking:
    ctx          = None    # Context
    kvmap        = None    # Key-value store
    loop         = None    # IOLoop
    pub_port     = None    # Publisher Port
    listen_port  = None    # Listener Port
    message_port = None    # Messenger Port
    publisher    = None    # Publisher Handler
    listener     = None    # Listener Handler
    messenger    = None    # Messenger Handler

    def __init__(self, prefs):
        self.pub_port = prefs['PUBPORT']
        self.listen_port = prefs['LISTENPORT']
        self.message_port = prefs['MESSAGEPORT']

        self.context = zmq.Context()
        self.kvmap = {}
        self.loop = IOLoop.instance()
        # Publisher sends commands to Pilots
        # Subscriber listens for data from Pilots
        # Sync ensures pilots are ready for publishing
        self.publisher  = self.context.socket(zmq.PUB)
        self.listener = self.context.socket(zmq.PULL)
        self.messenger = self.context.socket(zmq.PAIR)
        self.publisher.bind('tcp://*:{}'.format(self.pub_port))
        self.listener.bind('tcp://*:{}'.format(self.listen_port))
        self.messenger.bind('tcp://*:{}'.format(self.message_port))

        # Wrap as ZMQStreams
        self.publisher = ZMQStream(self.publisher)
        self.listener  = ZMQStream(self.listener)
        self.messenger = ZMQStream(self.messenger)

        # Log formatting
        logging.basicConfig(format="%(asctime)s %(message)s",
                            datefmt="%Y-%m-%d %H:%M%:S",
                            level=logging.INFO)

        # TODO: Get KVMsg from zexamples repo

    def start(self):
        try:
            self.loop.start()
        except KeyboardInterrupt:
            pass


    def handle_publish(self, message):
        # If it's to all... use "X" or other nonspecific sub pattern
        # Otherwise send a message to a specific pi
        if len(message) != 3:
            print("Bad Message to Publish: {}".format(message))
            return
        elif len(message) == 3:
            # should have pi, a message field and the value
            
        pass

    def handle_listen(self):
        pass

    def handle_message(self):
        pass






        # Start listening thread

    def init_pilots(self):



    def listen(self):
        [addr, reply] = self.listener.recv_multipart()
        #[addr, reply] = QtGui.QMessageBox.information(self, "Message", message)
        print(addr, reply)

