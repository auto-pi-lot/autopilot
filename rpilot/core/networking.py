"""
Classes for network communication.

There are two general types of network objects -

* :class:`.Networking` and its children are independent processes that should only be instantiated once
    per piece of hardware. They are used to distribute messages between :class:`.Net_Node` s,
    forward messages up the networking tree, and responding to messages that don't need any input from
    the :class:`~.pilot.Pilot` or :class:`~.terminal.Terminal`.
* :class:`.Net_Node` is a pop-in networking class that can be given to any other object that
    wants to send or receive messages.
"""


import json
import logging
import threading
import zmq
import sys
import datetime
import os
import multiprocessing
import base64
import socket
from tornado.ioloop import IOLoop
from zmq.eventloop.zmqstream import ZMQStream
from itertools import count

from rpilot import prefs

# TODO: Periodically ping pis to check that they are still responsive

class Networking(multiprocessing.Process):
    """
    Independent networking class used for messaging between computers.

    These objects send and handle :class:`.networking.Message` s by using a
    dictionary of :attr:`~.networking.Networking.listens`, or methods
    that are called to respond to different types of messages.

    Each sent message is given an ID, and a thread is spawned to periodically
    resend it (up until some time-to-live, typically 5 times) until confirmation
    is received.

    By default, the only listen these objects have is :meth:`.l_confirm`,
    which responds to message confirmations. Accordingly, `listens` should be added
    by using :meth:`dict.update` rather than reassigning the attribute.

    Networking objects can be made with or without a :attr:`~.networking.Networking.pusher`,
    a :class:`zmq.DEALER` socket that connects to the :class:`zmq.ROUTER`
    socket of an upstream Networking object.

    This class should not be instantiated on its own, but should instead
    be subclassed in order to provide methods used by :meth:`~.Networking.handle_listen`.

    Attributes:
        ctx (:class:`zmq.Context`):  zeromq context
        loop (:class:`tornado.ioloop.IOLoop`): a tornado ioloop
        pusher (:class:`zmq.Socket`): pusher socket - a dealer socket that connects to other routers
        push_ip (str): If we have a dealer, IP to push messages to
        push_port (str):  If we have a dealer, port to push messages to
        push_id (str): :attr:`~zmq.Socket.identity` of the Router we push to
        listener (:class:`zmq.Socket`): The main router socket to send/recv messages
        listen_port (str): Port our router listens on
        logger (:class:`logging.Logger`): Used to log messages and network events.
        log_handler (:class:`logging.FileHandler`): Handler for logging
        log_formatter (:class:`logging.Formatter`): Formats log entries as::

            "%(asctime)s %(levelname)s : %(message)s"

        id (str): What are we known as? What do we set our :attr:`~zmq.Socket.identity` as?
        ip (str): Device IP
        listens (dict): Dictionary of functions to call for different types of messages. keys match the :attr:`.Message.key`.
        senders (dict): Identities of other sockets (keys, ie. directly connected) and their state (values) if they keep one
        outbox (dict): Messages that have been sent but have not been confirmed
        timers (dict): dict of :class:`threading.Timer` s that will check in on outbox messages
        msg_counter (:class:`itertools.count`): counter to index our sent messages
        file_block (:class:`threading.Event`): Event to signal when a file is being received.


    """
    ctx          = None    # Context
    loop         = None    # IOLoop
    push_ip      = None    # IP to push to
    push_port    = None    # Publisher Port
    push_id      = ""      # Identity of the Router we push to
    listen_port  = None    # Listener Port
    pusher       = None    # pusher socket - a dealer socket that connects to other routers
    listener     = None    # Listener socket - a router socket to send/recv messages
    logger       = None    # Logger....
    log_handler  = None
    log_formatter = None
    id           = None    # What are we known as?
    ip           = None    # whatismy
    listens      = {}    # Dictionary of functions to call for different types of messages
    senders      = {} # who has sent us stuff (ie. directly connected) and their state if they keep one
    outbox = {}  # Messages that are out with unconfirmed delivery
    timers = {}  # dict of timer threads that will check in on outbox messages

    def __init__(self):
        super(Networking, self).__init__()
        # Prefs should be passed by the terminal, if not, try to load from default locatio

        self.ip = self.get_ip()

        # Setup logging
        self.init_logging()

        self.file_block = threading.Event() # to wait for file transfer

        # number messages as we send them
        self.msg_counter = count()

        # we have a few builtin listens
        self.listens = {
            'CONFIRM': self.l_confirm
        }

    def run(self):
        """
        A :class:`zmq.Context` and :class:`tornado.IOLoop` are spawned,
        the listener and optionally the pusher are instantiated and
        connected to :meth:`~.Networking.handle_listen` using
        :meth:`~zmq.eventloop.zmqstream.ZMQStream.on_recv` .

        The process is kept open by the :class:`tornado.IOLoop` .
        """
        # init zmq objects
        self.context = zmq.Context()
        self.loop = IOLoop()

        # Our networking topology is treelike:
        # each Networking object binds one Router to
        # send and receive messages from its descendants
        # each Networking object may have one Dealer that
        # connects it with its antecedents.
        self.listener  = self.context.socket(zmq.ROUTER)
        self.listener.identity = self.id.encode('utf-8')
        self.listener.bind('tcp://*:{}'.format(self.listen_port))
        self.listener = ZMQStream(self.listener, self.loop)
        self.listener.on_recv(self.handle_listen)

        if self.pusher is True:
            self.pusher = self.context.socket(zmq.DEALER)
            self.pusher.identity = self.id.encode('utf-8')
            self.pusher.connect('tcp://{}:{}'.format(self.push_ip, self.push_port))
            self.pusher = ZMQStream(self.pusher, self.loop)
            self.pusher.on_recv(self.handle_listen)
            # TODO: Make sure handle_listen knows how to handle ID-less messages

        self.logger.info('Starting IOLoop')
        self.loop.start()

    def prepare_message(self, to, key, value):
        """
        If a message originates with us, a :class:`.Message` class
        is instantiated, given an ID and the rest of its attributes.

        Args:
            to (str): The identity of the socket this message is to
            key (str): The type of message - used to select which method the receiver
                uses to process this message.
            value: Any information this message should contain. Can be any type, but
                must be JSON serializable.
        """
        msg = Message()
        msg.sender = self.id
        msg.to = to
        msg.key = key
        msg.value = value

        msg_num = self.msg_counter.next()
        msg.id = "{}_{}".format(self.id, msg_num)

        return msg


    def send(self, to=None, key=None, value=None, msg=None, repeat=True):
        """
        Send a message via our :attr:`~.Networking.listener` , ROUTER socket.

        Either an already created :class:`.Message` should be passed as `msg`,
        or at least `to` and `key` must be provided for a new message created
        by :meth:`~.Networking.prepare_message` .

        A :class:`threading.Timer` is created to resend the message using
        :meth:`~.Networking.repeat` unless `repeat` is False.

        Args:
            to (str): The identity of the socket this message is to
            key (str): The type of message - used to select which method the receiver
                uses to process this message.
            value: Any information this message should contain. Can be any type, but
                must be JSON serializable.
            msg (`.Message`): An already created message.
            repeat (bool): Should this message be resent if confirmation is not received?
        """

        if not msg and not all([to, key]):
            self.logger.exception('Need either a message or \'to\' and \'key\' fields.\
                Got\nto: {}\nkey: {}\nvalue: {}\nmsg: {}'.format(to, key, value, msg))
            return

        if not msg:
            # we're sending this ourselves, new message.
            msg = self.prepare_message(to, key, value)

        # Make sure our message has everything
        if not msg.validate():
            self.logger.error('Message Invalid:\n{}'.format(str(msg)))

        # encode message
        msg_enc = msg.serialize()

        if not msg_enc:
            self.logger.error('Message could not be encoded:\n{}'.format(str(msg)))
            return

        self.listener.send_multipart([bytes(msg.to), msg_enc])
        self.logger.info('MESSAGE SENT - {}'.format(str(msg)))

        if repeat and not msg.key == "CONFIRM":
            # add to outbox and spawn timer to resend
            self.outbox[msg.id] = msg
            self.timers[msg.id] = threading.Timer(5.0, self.repeat, args=(msg.id,'send'))
            self.timers[msg.id].start()

    def push(self,  to=None, key = None, value = None, msg=None, repeat=True):
        """
        Send a message via our :attr:`~.Networking.pusher` , DEALER socket.

        Unlike :meth:`~.Networking.send` , `to` is not required. Every message
        is always sent to :attr:`~.Networking.push_id` . `to` can be included
        to send a message further up the network tree to a networking object
        we're not directly connected to.

        Either an already created :class:`.Message` should be passed as `msg`,
        or at least `key` must be provided for a new message created
        by :meth:`~.Networking.prepare_message` .

        A :class:`threading.Timer` is created to resend the message using
        :meth:`~.Networking.repeat` unless `repeat` is False.

        Args:
            to (str): The identity of the socket this message is to. If not included,
                sent to :meth:`~.Networking.push_id` .
            key (str): The type of message - used to select which method the receiver
                uses to process this message.
            value: Any information this message should contain. Can be any type, but
                must be JSON serializable.
            msg (`.Message`): An already created message.
            repeat (bool): Should this message be resent if confirmation is not received?
        """
        # send message via the dealer
        # even though we only have one connection over our dealer,
        # we still include 'to' in case we are sending further upstream
        # but can push without 'to', just fill in with upstream id

        if not msg and not key:
            self.logger.exception('Need either a message or a \'key\' field.\
                Got\nto: {}\nkey: {}\nvalue: {}\nmsg: {}'.format(to, key, value, msg))

        if not msg:
            if to is None:
                to = self.push_id
            msg = self.prepare_message(to, key, value)

        # Make sure our message has everything
        if not msg.validate():
            self.logger.error('Message Invalid:\n{}'.format(str(msg)))

        # encode message
        msg_enc = msg.serialize()

        if not msg_enc:
            self.logger.error('Message could not be encoded:\n{}'.format(str(msg)))
            return

        # Even if the message is not to our upstream node, we still send it
        # upstream because presumably our target is upstream.
        self.pusher.send_multipart([bytes(self.push_id), msg_enc])
        self.logger.info('MESSAGE SENT - {}'.format(str(msg)))

        if repeat and not msg.key == 'CONFIRM':
            # add to outbox and spawn timer to resend
            self.outbox[msg.id] = msg
            self.timers[msg.id] = threading.Timer(5.0, self.repeat, args=(msg.id, 'push'))
            self.timers[msg.id].start()

    def repeat(self, msg_id, send_type):
        """
        Called by a :class:`threading.Timer` to resend a message that hasn't
        been confirmed by its recipient.

        TTL is decremented, and messages are resent until their TTL is 0.

        Args:
            msg_id (str): The ID of our message, the key used to store it
                in :attr:`~.Networking.outbox` .
            send_type ('send', 'push'): Should this message be resent with
                our `listener` (send) or pusher?
        """
        # Handle repeated messages
        # If we still have the message in our outbox...
        if msg_id not in self.outbox.keys():
            # TODO: Do we really need this warning? this should be normal behavior...
            self.logger.warning('Republish called for message {}, but missing message'.format(msg_id))
            return

        # decrement ttl
        self.outbox[msg_id].ttl -= 1

        # If our TTL is now zero, delete the message and log its failure
        if int(self.outbox[msg_id].ttl) <= 0:
            self.logger.warning('PUBLISH FAILED {} - {}'.format(msg_id, str(self.outbox[msg_id])))
            del self.outbox[msg_id]
            return

        # Send the message again
        msg = self.outbox[msg_id]
        self.logger.info('REPUBLISH {} - {}'.format(msg_id,str(self.outbox[msg_id])))
        if send_type == 'send':
            self.listener.send_multipart([bytes(msg.sender), msg.serialize()])
        elif send_type == 'push':
            self.pusher.send_multipart([bytes(self.push_id), msg.serialize()])
        else:
            self.logger.exception('Republish called without proper send_type!')

        # Spawn a thread to check in on our message
        self.timers[msg_id] = threading.Timer(5.0, self.repeat, args=(msg_id, send_type))
        self.timers[msg_id].start()

    def l_confirm(self, msg):
        """
        Confirm that a message was received.

        Args:
            msg (:class:`.Message`): The message we are confirming.
        """
        # confirmation that a published message was received
        # value should be the message id

        # delete message from outbox if we still have it
        if msg.value in self.outbox.keys():
            del self.outbox[msg.value]

        # stop a timer thread if we have it
        if msg.value in self.timers.keys():
            self.timers[msg.value].cancel()
            del self.timers[msg.value]

        self.logger.info('CONFIRMED MESSAGE {}'.format(msg.value))

    def handle_listen(self, msg):
        """
        Upon receiving a message, call the appropriate listen method
        in a new thread.

        If the message is :attr:`~.Message.to` us, send confirmation.

        If the message is not :attr:`~.Message.to` us, attempt to forward it.

        Args:
            msg (str): JSON :meth:`.Message.serialize` d message.
        """
        # TODO: This check is v. fragile, pyzmq has a way of sending the stream along with the message
        if len(msg)==1:
            # from our dealer
            send_type = 'dealer'
            msg = json.loads(msg[0])
            msg = Message(**msg)

        elif len(msg)>=2:
            # from the router
            send_type = 'router'
            sender = msg[-3]

            # if this is a new sender, add them to the list
            if sender not in self.senders.keys():
                self.senders[sender] = ""

            # connection pings are blank frames,
            # respond to let them know we're alive
            if msg[-1] == b'':
                self.listener.send_multipart(msg)
                return

            msg = json.loads(msg[-1])
            msg = Message(**msg)
        else:
            self.logger.error('Dont know what this message is:{}'.format(msg))
            return

        # Check if our listen was sent properly
        if not msg.validate():
            self.logger.error('Message failed to validate:\n{}'.format(str(msg)))
            return

        self.logger.info('RECEIVED: {}'.format(str(msg)))

        # if this message is to us, just handle it and return
        if msg.to in [self.id, "_{}".format(self.id)]:
            # Log and spawn thread to respond to listen
            try:
                listen_funk = self.listens[msg.key]
                listen_thread = threading.Thread(target=listen_funk, args=(msg,))
                listen_thread.start()
            except KeyError:
                self.logger.exception('ERROR: No function could be found for msg id {} with key: {}'.format(msg.id, msg.key))

            # send a return message that confirms even if we except
            # don't confirm confirmations
            if msg.key != "CONFIRM":
                if send_type == 'router':
                    self.send(sender, 'CONFIRM', msg.id)
                elif send_type == 'dealer':
                    self.push(msg.sender, 'CONFIRM', msg.id)
            return

        # otherwise, if it's to someone we know about, send it there
        elif msg.to in self.senders.keys():
            self.send(msg=msg)
        # otherwise, if we have a pusher, send it there
        # it's either for them or some other upstream node we don't know about
        elif self.pusher:
            self.push(msg=msg)
        else:
            self.logger.warning('Message to unconfirmed recipient, attempting to send: {}'.format(str(msg)))
            self.send(msg=msg)

        # finally, if there's something we're supposed to do, do it
        # even if the message is not to us,
        # sometimes we do work en passant to reduce effort doubling
        # FIXME Seems like a really bad idea.
        if msg.key in self.listens.keys():
            listen_funk = self.listens[msg.key]
            listen_thread = threading.Thread(target=listen_funk, args=(msg,))
            listen_thread.start()

        # since we return if it's to us before, confirm is repeated down here.
        # FIXME: Inelegant
        if msg.key != "CONFIRM":
            if send_type == 'router':
                self.send(sender, 'CONFIRM', msg.id)
            elif send_type == 'dealer':
                self.push(msg.sender, 'CONFIRM', msg.id)

    def init_logging(self):
        """
        Initialize logging to a timestamped file in `prefs.LOGDIR` .
        """
        # Setup logging
        timestr = datetime.datetime.now().strftime('%y%m%d_%H%M%S')
        log_file = os.path.join(prefs.LOGDIR, 'Networking_Log_{}.log'.format(timestr))

        self.logger = logging.getLogger('networking')
        self.log_handler = logging.FileHandler(log_file)
        self.log_formatter = logging.Formatter("%(asctime)s %(levelname)s : %(message)s")
        self.log_handler.setFormatter(self.log_formatter)
        self.logger.addHandler(self.log_handler)
        self.logger.setLevel(logging.INFO)
        self.logger.info('Networking Logging Initiated')

    def get_ip(self):
        """
        Find our IP address

        returns (str): our IPv4 address.
        """

        # shamelessly stolen from https://www.w3resource.com/python-exercises/python-basic-exercise-55.php
        # variables are badly named because this is just a rough unwrapping of what was a monstrous one-liner
        # (and i don't really understand how it works)

        # get ips that aren't the loopback
        unwrap00 = [ip for ip in socket.gethostbyname_ex(socket.gethostname())[2] if not ip.startswith("127.")][:1]
        # ??? truly dk
        unwrap01 = [[(s.connect(('8.8.8.8', 53)), s.getsockname()[0], s.close()) for s in
                     [socket.socket(socket.AF_INET, socket.SOCK_DGRAM)]][0][1]]

        unwrap2 = [l for l in (unwrap00, unwrap01) if l][0][0]

        return unwrap2

class Terminal_Networking(Networking):
    """
    :class:`~.networking.Networking` object used by :class:`~.Terminal`
    objects.

    Spawned without a :attr:`~.Networking.pusher`.

    **Listens**

    +-------------+-------------------------------------------+-----------------------------------------------+
    | Key         | Method                                    | Description                                   |
    +=============+===========================================+===============================================+
    | 'PING'      | :meth:`~.Terminal_Networking.l_ping`      | We are asked to confirm that we are alive     |
    +-------------+-------------------------------------------+-----------------------------------------------+
    | 'INIT'      | :meth:`~.Terminal_Networking.l_init`      | Ask all pilots to confirm that they are alive |
    +-------------+-------------------------------------------+-----------------------------------------------+
    | 'CHANGE'    | :meth:`~.Terminal_Networking.l_change`    | Change a parameter on the Pi                  |
    +-------------+-------------------------------------------+-----------------------------------------------+
    | 'STOPALL'   | :meth:`~.Terminal_Networking.l_stopall`   | Stop all pilots and plots                     |
    +-------------+-------------------------------------------+-----------------------------------------------+
    | 'KILL'      | :meth:`~.Terminal_Networking.l_kill`      | Terminal wants us to die :(                   |
    +-------------+-------------------------------------------+-----------------------------------------------+
    | 'DATA'      | :meth:`~.Terminal_Networking.l_data`      | Stash incoming data from a Pilot              |
    +-------------+-------------------------------------------+-----------------------------------------------+
    | 'STATE'     | :meth:`~.Terminal_Networking.l_state`     | A Pilot has changed state                     |
    +-------------+-------------------------------------------+-----------------------------------------------+
    | 'HANDSHAKE' | :meth:`~.Terminal_Networking.l_handshake` | A Pi is telling us it's alive and its IP      |
    +-------------+-------------------------------------------+-----------------------------------------------+
    | 'FILE'      | :meth:`~.Terminal_Networking.l_file`      | The pi needs some file from us                |
    +-------------+-------------------------------------------+-----------------------------------------------+

    """

    def __init__(self, pilots):
        """
        Args:
            pilots (dict): The :attr:`.Terminal.pilots` dictionary.
        """
        super(Terminal_Networking, self).__init__()

        # by default terminal doesn't have a pusher, everything connects to it
        self.pusher = False

        # Store some prefs values
        self.listen_port = prefs.MSGPORT
        self.id = b'T'

        # Message dictionary - What method to call for each type of message received by the terminal class
        self.listens.update({
            'PING':      self.l_ping,  # We are asked to confirm that we are alive
            'INIT':      self.l_init,  # We should ask all the pilots to confirm that they are alive
            'CHANGE':    self.l_change,  # Change a parameter on the Pi
            'STOPALL':   self.l_stopall, # Stop all pilots and plots
            'KILL':      self.l_kill,  # Terminal wants us to die :(
            'DATA':      self.l_data,  # Stash incoming data from an rpilot
            'STATE':     self.l_state,  # The Pi is confirming/notifying us that it has changed state
            'HANDSHAKE': self.l_handshake, # initial connection with some initial info
            'FILE':      self.l_file,  # The pi needs some file from us
        })

        # dictionary that keeps track of our pilots
        self.pilots = pilots



    ##########################
    # Message Handling Methods

    def l_ping(self, msg):
        """
        We are asked to confirm that we are alive

        Respond with a blank 'STATE' message.

        Args:
            msg (:class:`.Message`):
        """
        # we are being asked if we're alive
        # respond with blank message since the terminal isn't really stateful
        self.send(msg.sender, 'STATE')

    def l_init(self, msg):
        """
        Ask all pilots to confirm that they are alive

        Sends a "PING" to everyone in the pilots dictionary.

        Args:
            msg (:class:`.Message`):
        """
        # Ping all pis that we are expecting given our pilot db
        # Responses will be handled with l_state so not much needed here

        for p in self.pilots.keys():
            self.send(p, 'PING')


    def l_change(self, msg):
        """
        Change a parameter on the Pi

        Warning:
            Not Implemented

        Args:
            msg (:class:`.Message`):
        """
        # TODO: Should also handle param changes to GUI objects like ntrials, etc.
        pass

    def l_stopall(self, msg):
        """
        Stop all pilots and plots

        Args:
            msg (:class:`.Message`):
        """
        # let all the pilots and plot objects know that they should stop
        for p in self.pilots.keys():
            self.send(p, 'STOP')
            self.send("P_{}".format(p), 'STOP')


    def l_kill(self, msg):
        """
        Terminal wants us to die :(

        Stop the :attr:`.Networking.loop`

        Args:
            msg (:class:`.Message`):
        """
        self.logger.info('Received kill request')

        # Stopping the loop should kill the process, as it's what's holding us in run()
        self.loop.stop()


    def l_data(self, msg):
        """
        Stash incoming data from a Pilot

        Just forward this along to the internal terminal object ('_T')
        and a copy to the relevant plot.

        Args:
            msg (:class:`.Message`):
        """
        # Send through to terminal
        self.send('_T', 'DATA', msg.value)

        # Send to plot widget, which should be listening to "P_{pilot_name}"
        self.send('P_{}'.format(msg.value['pilot']), 'DATA', msg.value)


    def l_state(self, msg):
        """
        A Pilot has changed state.

        Stash in 'state' field of pilot dict and send along to _T

        Args:
            msg (:class:`.Message`):
        """
        if msg.sender in self.pilots.keys():
            if 'state' in self.pilots[msg.sender].keys():
                if msg.value == self.pilots[msg.sender]['state']:
                    # if we've already gotten this one, don't send to terminal
                    return
            self.pilots[msg.sender]['state'] = msg.value

            # Tell the terminal so it can update the pilot_db file
            state = {'state':msg.value, 'pilot':msg.sender}
            self.send('_T', 'STATE', state)

            # Tell the plot
            self.send("P_{}".format(msg.sender), 'STATE', msg.value)

        self.senders[msg.sender] = msg.value

    def l_handshake(self, msg):
        """
        A Pi is telling us it's alive and its IP.

        Send along to _T

        Args:
            msg (:class:`.Message`):
        """
        # only rly useful for our terminal object
        self.send('_T', 'HANDSHAKE', value=msg.value)



    def l_file(self, msg):
        """
        A Pilot needs some file from us.

        Send it back after :meth:`base64.b64encode` ing it.

        TODO:
            Split large files into multiple messages...

        Args:
            msg (:class:`.Message`): The value field of the message should contain some
                relative path to a file contained within `prefs.SOUNDDIR` . eg.
                `'/songs/sadone.wav'` would return `'os.path.join(prefs.SOUNDDIR/songs.sadone.wav'`
        """
        # The <target> pi has requested some file <value> from us, let's send it back
        # This assumes the file is small, if this starts crashing we'll have to split the message...

        full_path = os.path.join(prefs.SOUNDDIR, msg.value)
        with open(full_path, 'rb') as open_file:
            # encode in base64 so json doesn't complain
            file_contents = base64.b64encode(open_file.read())

        file_message = {'path':msg.value, 'file':file_contents}

        self.send(msg.target, 'FILE', file_message)

class Pilot_Networking(Networking):
    """
    :class:`~.networking.Networking` object used by :class:`~.Pilot`
    objects.

    Spawned with a :attr:`~.Networking.pusher` connected back to the 
    :class:`~.Terminal` .

    **Listens**
    
    +-------------+-------------------------------------+-----------------------------------------------+
    | Key         | Method                              | Description                                   |
    +=============+=====================================+===============================================+
    | 'STATE'     | :meth:`~.Pilot_Networking.l_state`  | Pilot has changed state                       |
    | 'COHERE'    | :meth:`~.Pilot_Networking.l_cohere` | Make sure our data and the Terminal's match.  |
    | 'PING'      | :meth:`~.Pilot_Networking.l_ping`   | The Terminal wants to know if we're listening |
    | 'START'     | :meth:`~.Pilot_Networking.l_start`  | We are being sent a task to start             |
    | 'STOP'      | :meth:`~.Pilot_Networking.l_stop`   | We are being told to stop the current task    |
    | 'PARAM'     | :meth:`~.Pilot_Networking.l_change` | The Terminal is changing some task parameter  |
    | 'FILE'      | :meth:`~.Pilot_Networking.l_file`   | We are receiving a file                       |
    +-------------+-------------------------------------+-----------------------------------------------+

    """
    def __init__(self):
        # Pilot has a pusher - connects back to terminal
        self.pusher = True
        if prefs.LINEAGE == 'CHILD':
            self.push_id = prefs.PARENTID
            self.push_port = prefs.PARENTPORT
            self.push_ip = prefs.PARENTIP

        else:
            self.push_id = 'T'
            self.push_port = prefs.PUSHPORT
            self.push_ip = prefs.TERMINALIP

        # Store some prefs values
        self.listen_port = prefs.MSGPORT

        self.id = prefs.NAME.encode('utf-8')
        self.pi_id = "_{}".format(self.id)
        self.mouse = None # Store current mouse ID
        self.state = None # store current pi state
        self.child = False # Are we acting as a child right now?
        self.parent = False # Are we acting as a parent right now?

        super(Pilot_Networking, self).__init__()

        self.listens.update({
            'STATE': self.l_state,  # Confirm or notify terminal of state change
            'COHERE': self.l_cohere, # Sending our temporary data table at the end of a run to compare w/ terminal's copy
            'PING': self.l_ping,  # The Terminal wants to know if we're listening
            'START': self.l_start,  # We are being sent a task to start
            'STOP': self.l_stop,  # We are being told to stop the current task
            'PARAM': self.l_change,  # The Terminal is changing some task parameter
            'FILE': self.l_file,  # We are receiving a file
            'CONTINUOUS': self.l_continuous, # we are sending continuous data to the terminal
            'CHILD': self.l_child,
            'HANDSHAKE': self.l_noop
        })

    ###########################3
    # Message/Listen handling methods

    def l_noop(self, msg):
        pass

    def l_state(self, msg):
        """
        Pilot has changed state

        Stash it and alert the Terminal

        Args:
            msg (:class:`.Message`):
        """
        # Save locally so we can respond to queries on our own, then push 'er on through
        # Value will just have the state, we want to add our name
        self.state = msg.value

        self.push(to="T", key='STATE', value=msg.value)


    def l_cohere(self, msg):
        """
        Send our local version of the data table so the terminal can double check

        Warning:
            Not Implemented

        Args:
            msg (:class:`.Message`):
        """

        pass

    def l_ping(self, msg):
        """
        The Terminal wants to know our status

        Push back our current state.

        Args:
            msg (:class:`.Message`):
        """
        # The terminal wants to know if we are alive, respond with our name and IP
        # don't bother the pi
        self.push(key='STATE', value=self.state)

    def l_start(self, msg):
        """
        We are being sent a task to start

        If we need any files, request them.

        Then send along to the pilot.

        Args:
            msg (:class:`.Message`): value will contain a dictionary containing a task
                description.
        """
        self.mouse = msg.value['mouse']

        # TODO: Refactor into a general preflight check.
        # First make sure we have any sound files that we need
        if 'sounds' in msg.value.keys():
            # nested list comprehension to get value['sounds']['L/R'][0-n]
            f_sounds = [sound for sounds in msg.value['sounds'].values() for sound in sounds
                        if sound['type'] in ['File', 'Speech']]
            if len(f_sounds)>0:
                # check to see if we have these files, if not
                #     def update(self, data):
                #         """
                #         Args:
                #             data (:class:`numpy.ndarray`): an x_width x 2 array where
                #                 column 0 is trial number and column 1 is the value.
                #         """
                #         # data should come in as an n x 2 array,
                #         # 0th column - trial number (x), 1st - (y) value
                #         data = data.astype(np.float)
                #
                #         self.series = pd.Series(data[...,1])
                #         ys = self.series.rolling(self.winsize, min_periods=0).mean().as_matrix()
                #
                #         #print(ys)
                #
                #         self.curve.setData(data[...,0], ys, fillLevel=0.5), request them
                for sound in f_sounds:
                    full_path = os.path.join(prefs.SOUNDDIR, sound['path'])
                    if not os.path.exists(full_path):
                        # We ask the terminal to send us the file and then wait.
                        self.logger.info('REQUESTING SOUND {}'.format(sound['path']))
                        self.push(key='FILE', value=sound['path'])
                        # wait here to get the sound,
                        # the receiving thread will set() when we get it.
                        self.file_block.clear()
                        self.file_block.wait()

        # If we're starting the task as a child, stash relevant params
        if 'child' in msg.value.keys():
            self.child = True
            self.parent_id = msg.value['child']['parent']
            self.mouse = msg.value['child']['mouse']

        else:
            self.child = False


        # once we make sure we have everything, tell the Pilot to start.
        self.send(self.pi_id, 'START', msg.value)

    def l_stop(self, msg):
        """
        Tell the pi to stop the task

        Args:
            msg (:class:`.Message`):
        """
        self.send(self.pi_id, 'STOP')

    def l_change(self, msg):
        """
        The terminal is changing a parameter

        Warning:
            Not implemented

        Args:
            msg (:class:`.Message`):
        """
        # TODO: Changing some task parameter from the Terminal
        pass

    def l_file(self, msg):
        """
        We are receiving a file.

        Decode from b64 and save. Set the file_block.

        Args:
            msg (:class:`.Message`): value will have 'path' and 'file',
                where the path determines where in `prefs.SOUNDDIR` the
                b64 encoded 'file' will be saved.
        """
        # The file should be of the structure {'path':path, 'file':contents}

        full_path = os.path.join(prefs.SOUNDDIR, msg.value['path'])
        # TODO: give Message full deserialization capabilities including this one
        file_data = base64.b64decode(msg.value['file'])
        try:
            os.makedirs(os.path.dirname(full_path))
        except:
            # TODO: Make more specific - only if dir already exists
            pass
        with open(full_path, 'wb') as open_file:
            open_file.write(file_data)

        self.logger.info('SOUND RECEIVED {}'.format(msg.value['path']))

        # If we requested a file, some poor start fn is probably waiting on us
        self.file_block.set()

    def l_continuous(self, msg):
        if self.child:
            msg.value['pilot'] = self.parent_id
            msg.value['mouse'] = self.mouse
            self.send(to='T', key='DATA', value=msg.value, repeat=False)

    def l_child(self, msg):
        """
        Telling our child to run a task.

        Args:
            msg ():

        Returns:

        """

        self.send(to=prefs.CHILDID, key='START', value=msg.value)





#####################################

class Net_Node(object):
    """
    Drop in networking object to be given to any sub-object
    behind some external-facing :class:`.Networking` object.

    These objects are intended to communicate locally, within a piece of hardware,
    though not necessarily within the same process.

    To minimize the complexity of the network topology, Net_Nodes
    must communicate through a :class:`.Networking` ROUTER, rather than
    address each other directly.

    Attributes:
        context (:class:`zmq.Context`):  zeromq context
        loop (:class:`tornado.ioloop.IOLoop`): a tornado ioloop
        sock (:class:`zmq.Socket`): Our DEALER socket.
        id (str): What are we known as? What do we set our :attr:`~zmq.Socket.identity` as?
        upstream (str): The identity of the ROUTER socket used by our upstream :class:`.Networking` object.
        port (int): The port that our upstream ROUTER socket is bound to
        listens (dict): Dictionary of functions to call for different types of messages. keys match the :attr:`.Message.key`.
        outbox (dict): Messages that have been sent but have not been confirmed
        timers (dict): dict of :class:`threading.Timer` s that will check in on outbox messages
        logger (:class:`logging.Logger`): Used to log messages and network events.
        log_handler (:class:`logging.FileHandler`): Handler for logging
        log_formatter (:class:`logging.Formatter`): Formats log entries as::

            "%(asctime)s %(levelname)s : %(message)s"

        msg_counter (:class:`itertools.count`): counter to index our sent messages
        loop_thread (:class:`threading.Thread`): Thread that holds our loop. initialized with `daemon=True`
    """
    context = None
    loop = None
    id = None
    upstream = None # ID of router we connect to
    port = None
    listens = {}
    outbox = {}
    timers = {}
    #connected = False
    logger = None
    log_handler = None
    log_formatter = None
    sock = None
    loop_thread = None

    def __init__(self, id, upstream, port, listens, instance=True):
        """
        Args:
            id (str): What are we known as? What do we set our :attr:`~zmq.Socket.identity` as?
            upstream (str): The identity of the ROUTER socket used by our upstream :class:`.Networking` object.
            port (int): The port that our upstream ROUTER socket is bound to
            listens (dict): Dictionary of functions to call for different types of messages.
                keys match the :attr:`.Message.key`.
            instance (bool): Should the node try and use the existing zmq context and tornado loop?
        """
        if instance:
            self.context = zmq.Context.instance()
            self.loop    = IOLoop.current()
        else:
            self.context = zmq.Context()
            self.loop    = IOLoop()

        # we have a few builtin listens
        self.listens = {
            'CONFIRM': self.l_confirm
        }
        # then add the rest
        self.listens.update(listens)

        self.id = id.encode('utf-8')
        self.upstream = upstream.encode('utf-8')
        self.port = int(port)

        # self.connected = False
        self.msg_counter = count()

        # try to get a logger
        self.init_logging()

        self.init_networking()

    def init_networking(self):
        """
        Creates socket, connects to specified port on localhost,
        and starts the :meth:`~Net_Node.threaded_loop` as a daemon thread.
        """
        self.sock = self.context.socket(zmq.DEALER)
        self.sock.identity = self.id
        #self.sock.probe_router = 1

        # net nodes are local only
        self.sock.connect('tcp://localhost:{}'.format(self.port))

        # wrap in zmqstreams and start loop thread
        self.sock = ZMQStream(self.sock, self.loop)
        self.sock.on_recv(self.handle_listen)

        self.loop_thread = threading.Thread(target=self.threaded_loop)
        self.loop_thread.daemon = True
        self.loop_thread.start()

        #self.connected = True

    def threaded_loop(self):
        """
        Run in a thread, either starts the IOLoop, or if it
        is already started (ie. running in another thread),
        breaks.
        """

        while True:
            try:
                self.loop.start()
            except RuntimeError:
                # loop already started
                break

    def handle_listen(self, msg):
        """
        Upon receiving a message, call the appropriate listen method
        in a new thread and send confirmation it was received.

        Note:
            Unlike :meth:`.Networking.handle_listen` , only the :attr:`.Message.value`
            is given to listen methods. This was initially intended to simplify these
            methods, but this might change in the future to unify the messaging system.

        Args:
            msg (str): JSON :meth:`.Message.serialize` d message.
        """
        # messages from dealers are single frames because we only have one connected partner
        # and that's the dealer spec lol

        msg = json.loads(msg[0])

        msg = Message(**msg)

        # Check if our listen was sent properly
        if not msg.validate():
            if self.logger:
                self.logger.error('Message failed to validate:\n{}'.format(str(msg)))
            return

        if self.logger:
            self.logger.info('{} - RECEIVED: {}'.format(self.id, str(msg)))

        # if msg.key == 'CONFIRM':
        #     if msg.value in self.outbox.keys():
        #         del self.outbox[msg.value]
        #
        #     # stop a timer thread if we have it
        #     if msg.value in self.timers.keys():
        #         self.timers[msg.value].cancel()
        #         del self.timers[msg.value]
        #
        #     self.logger.info('CONFIRMED MESSAGE {}'.format(msg.value))
        # else:
        # Log and spawn thread to respond to listen
        try:
            listen_funk = self.listens[msg.key]
            listen_thread = threading.Thread(target=listen_funk, args=(msg.value,))
            listen_thread.start()
        except KeyError:
            self.logger.error('MSG ID {} - No listen function found for key: {}'.format(msg.id, msg.key))

        if msg.key != "CONFIRM":
            # send confirmation
            self.send(msg.sender, 'CONFIRM', msg.id)

    def send(self, to=None, key=None, value=None, msg=None, repeat=True):
        """
        Send a message via our :attr:`~.Net_Node.sock` , DEALER socket.

        `to` is not required. Every message
        is always sent to :attr:`~.Net_Node.upstream` . `to` can be included
        to send a message further up the network tree to a networking object
        we're not directly connected to.

        Either an already created :class:`.Message` should be passed as `msg`,
        or at least `key` must be provided for a new message created
        by :meth:`~.Net_Node.prepare_message` .

        A :class:`threading.Timer` is created to resend the message using
        :meth:`~.Net_Node.repeat` unless `repeat` is False.

        Args:
            to (str): The identity of the socket this message is to. If not included,
                sent to :meth:`~.Net_Node.upstream` .
            key (str): The type of message - used to select which method the receiver
                uses to process this message.
            value: Any information this message should contain. Can be any type, but
                must be JSON serializable.
            msg (`.Message`): An already created message.
            repeat (bool): Should this message be resent if confirmation is not received?
        """
        # send message via the dealer
        # even though we only have one connection over our dealer,
        # we still include 'to' in case we are sending further upstream
        # but can push without 'to', just fill in with upstream id
        if to is None:
            to = self.upstream

        if (key is None) and (msg is None):
            if self.logger:
                self.logger.error('Push sent without Key')
            return

        if not msg:
            msg = self.prepare_message(to, key, value)

        # Make sure our message has everything
        if not msg.validate():
            if self.logger:
                self.logger.error('Message Invalid:\n{}'.format(str(msg)))
            return

        # encode message
        msg_enc = msg.serialize()

        if not msg_enc:
            self.logger.error('Message could not be encoded:\n{}'.format(str(msg)))
            return

        self.sock.send_multipart([bytes(self.upstream), msg_enc])
        if self.logger:
            self.logger.info("MESSAGE SENT - {}".format(str(msg)))

        if repeat and not msg.key == "CONFIRM":
            # add to outbox and spawn timer to resend
            self.outbox[msg.id] = msg
            self.timers[msg.id] = threading.Timer(5.0, self.repeat, args=(msg.id,))
            self.timers[msg.id].start()

    def repeat(self, msg_id):
        """
        Called by a :class:`threading.Timer` to resend a message that hasn't
        been confirmed by its recipient.

        TTL is decremented, and messages are resent until their TTL is 0.

        Args:
            msg_id (str): The ID of our message, the key used to store it
                in :attr:`~.Net_Node.outbox` .
        """
        # Handle repeated messages
        # If we still have the message in our outbox...
        if msg_id not in self.outbox.keys():
            # TODO: Do we really need this warning? this should be normal behavior...
            self.logger.warning('Republish called for message {}, but missing message'.format(msg_id))
            return

        # decrement ttl
        self.outbox[msg_id].ttl -= 1
        # If our TTL is now zero, delete the message and log its failure
        if int(self.outbox[msg_id].ttl) <= 0:
            self.logger.warning('PUBLISH FAILED {} - {}'.format(msg_id, str(self.outbox[msg_id])))
            del self.outbox[msg_id]
            return


        # Send the message again
        self.logger.info('REPUBLISH {} - {}'.format(msg_id,str(self.outbox[msg_id])))
        msg = self.outbox[msg_id]
        self.sock.send_multipart([bytes(self.upstream), msg.serialize()])

        # Spawn a thread to check in on our message
        self.timers[msg_id] = threading.Timer(5.0, self.repeat, args=(msg_id,))
        self.timers[msg_id].start()

    def l_confirm(self, value):
        """
        Confirm that a message was received.

        Args:
            value (str): The ID of the message we are confirming.
        """
        # delete message from outbox if we still have it
        # msg.value should contain the if of the message that was confirmed
        if value in self.outbox.keys():
            del self.outbox[value]

        # stop a timer thread if we have it
        if value in self.timers.keys():
            self.timers[value].cancel()
            del self.timers[value]

        self.logger.info('CONFIRMED MESSAGE {}'.format(value))

    def prepare_message(self, to, key, value):
        """
        Instantiate a :class:`.Message` class, give it an ID and
        the rest of its attributes.

        Args:
            to (str): The identity of the socket this message is to
            key (str): The type of message - used to select which method the receiver
                uses to process this message.
            value: Any information this message should contain. Can be any type, but
                must be JSON serializable.
        """
        msg = Message()

        # if our name is _{something} and our upstream is {something}, replace sender with our upstream node
        # upstream node should handle all incoming information to those types of nodes
        #if self.id == "_{}".format(self.upstream):
        #    msg.sender = self.upstream
        #else:
        msg.sender = self.id

        msg.to = to
        msg.key = key
        msg.value = value

        msg_num = self.msg_counter.next()
        msg.id = "{}_{}".format(self.id, msg_num)

        return msg

    def init_logging(self):
        """
        Initialize logging to a timestamped file in `prefs.LOGDIR` .

        The logger name will be `'node.{id}'` .
        """
        timestr = datetime.datetime.now().strftime('%y%m%d_%H%M%S')
        log_file = os.path.join(prefs.LOGDIR, 'NetNode_{}_{}.log'.format(self.id, timestr))

        self.logger = logging.getLogger('node.{}'.format(self.id))
        self.log_handler = logging.FileHandler(log_file)
        self.log_formatter = logging.Formatter("%(asctime)s %(levelname)s : %(message)s")
        self.log_handler.setFormatter(self.log_formatter)
        self.logger.addHandler(self.log_handler)
        self.logger.setLevel(logging.INFO)
        self.logger.info('{} Logging Initiated'.format(self.id))



class Message(object):
    """
    A formatted message.

    `id`, `to`, `sender`, and `key` are required attributes,
    but any other key-value pair passed on init is added to the message's attributes
    and included in the message.

    Can be indexed and set like a dictionary (message['key'], etc.)

    Attributes:
        id (str): ID that uniquely identifies a message.
            format {sender.id}_{number}
        to (str): ID of socket this message is addressed to
        sender (str): ID of socket where this message originates
        key (str): Type of message, used to select a listen method to process it
        value: Body of message, can be any type but must be JSON serializable.
        ttl (int): Time-To-Live, each message is sent this many times at max,
            each send decrements ttl.
    """

    # TODO: just make serialization handle all attributes except Files which need to be b64 encoded first.
    id = None # number of message, format {sender.id}_{number}
    to = None
    sender = None
    key = None
    # value is the only attribute that can be left None,
    # ie. with signal-type messages like "STOP"
    value = None
    ttl = 5 # every message starts with 5 retries. only relevant to the sender so not serialized.

    def __init__(self, *args, **kwargs):
        # type: (object, object) -> None
        # Messages don't need to have all attributes on creation,
        # but do need them to serialize
        """
        Args:
            *args:
            **kwargs:
        """
        if len(args)>0:
            Exception("Messages cannot be constructed with positional arguments")

        for k, v in kwargs.items():
            setattr(self, k, v)

    def __str__(self):
        # type: () -> str
        if self.key == 'FILE':
            me_string = "ID: {}; TO: {}; SENDER: {}; KEY: {}".format(self.id, self.to, self.sender, self.key)
        else:
            me_string = "ID: {}; TO: {}; SENDER: {}; KEY: {}; VALUE: {}".format(self.id, self.to, self.sender, self.key, self.value)
        return me_string

    # enable dictionary-like behavior
    def __getitem__(self, key):
        """
        Args:
            key:
        """
        return self.__dict__[key]

    def __setitem__(self, key, value):
        """
        Args:
            key:
            value:
        """
        self.__dict__[key] = value

    def __delitem__(self, key):
        """
        Args:
            key:
        """
        del self.__dict__[key]

    def __contains__(self, key):
        """
        Args:
            key:
        """
        return key in self.__dict__

    def __len__(self):
        return len(self.__dict__)

    def validate(self):
        """
        Checks if `id`, `to`, `sender`, and `key` are all defined.

        Returns:
            bool (True): Does message have all required attributes set?
        """
        if all([self.id, self.to, self.sender, self.key]):
            return True
        else:
            return False

    def serialize(self):
        """
        Serializes all attributes in `__dict__` using json.

        Returns:
            str: JSON serialized message.
        """
        valid = self.validate()
        if not valid:
            Exception("""Message invalid at the time of serialization!\n {}""".format(str(self)))

        # msg = {
        #     'id': self.id,
        #     'to': self.to,
        #     'sender': self.sender,
        #     'key': self.key,
        #     'value': self.value
        # }
        msg = self.__dict__

        try:
            msg_enc = json.dumps(msg)
            return msg_enc
        except:
            return False















































