"""
Classes for network communication.

There are two general types of network objects -

* :class:`.Station` and its children are independent processes that should only be instantiated once
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
import time
import os
import multiprocessing
import base64
import socket
import struct
import blosc
from copy import copy
from tornado.ioloop import IOLoop
from zmq.eventloop.zmqstream import ZMQStream
from itertools import count
import numpy as np
import pdb
#from pudb.remote import set_trace
if sys.version_info >= (3,0):
    import queue
else:
    import Queue as queue

from autopilot import prefs

from pprint import pprint

# TODO: Periodically ping pis to check that they are still responsive

class Station(multiprocessing.Process):
    """
    Independent networking class used for messaging between computers.

    These objects send and handle :class:`.networking.Message` s by using a
    dictionary of :attr:`~.networking.Station.listens`, or methods
    that are called to respond to different types of messages.

    Each sent message is given an ID, and a thread is spawned to periodically
    resend it (up until some time-to-live, typically 5 times) until confirmation
    is received.

    By default, the only listen these objects have is :meth:`.l_confirm`,
    which responds to message confirmations. Accordingly, `listens` should be added
    by using :meth:`dict.update` rather than reassigning the attribute.

    Station objects can be made with or without a :attr:`~.networking.Station.pusher`,
    a :class:`zmq.DEALER` socket that connects to the :class:`zmq.ROUTER`
    socket of an upstream Station object.

    This class should not be instantiated on its own, but should instead
    be subclassed in order to provide methods used by :meth:`~.Station.handle_listen`.

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
    push_outbox = {}  # Messages that are out with unconfirmed delivery
    send_outbox = {}  # Messages that are out with unconfirmed delivery
    timers = {}  # dict of timer threads that will check in on outbox messages
    child = False
    routes = {} # dict of 'to' addressee and the route that should be taken to reach them
    repeat_interval = 5.0 # seconds to wait before retrying messages

    def __init__(self):
        super(Station, self).__init__()
        # Prefs should be passed by the terminal, if not, try to load from default locatio

        try:
            self.ip = self.get_ip()
        except Exception as e:
            Warning("Couldn't get IP!: {}".format(e))
            self.ip = ""


        # Setup logging
        self.init_logging()

        self.file_block = threading.Event() # to wait for file transfer

        # number messages as we send them
        self.msg_counter = count()

        # we have a few builtin listens
        self.listens = {
            'CONFIRM': self.l_confirm,
            'STREAM' : self.l_stream
        }

        # even tthat signals when we are closing
        self.closing = threading.Event()
        self.closing.clear()

        # start thread that periodically resends messages
        self.repeat_thread = threading.Thread(target=self.repeat)
        self.repeat_thread.setDaemon(True)
        self.repeat_thread.start()

    def __del__(self):
        self.closing.set()
        # Stopping the loop should kill the process, as it's what's holding us in run()
        self.loop.stop()

    def run(self):
        """
        A :class:`zmq.Context` and :class:`tornado.IOLoop` are spawned,
        the listener and optionally the pusher are instantiated and
        connected to :meth:`~.Station.handle_listen` using
        :meth:`~zmq.eventloop.zmqstream.ZMQStream.on_recv` .

        The process is kept open by the :class:`tornado.IOLoop` .
        """
        # init zmq objects
        self.context = zmq.Context()
        self.loop = IOLoop()

        # Our networking topology is treelike:
        # each Station object binds one Router to
        # send and receive messages from its descendants
        # each Station object may have one Dealer that
        # connects it with its antecedents.
        self.listener  = self.context.socket(zmq.ROUTER)
        #self.listener.identity = self.id.encode('utf-8')
        #self.listener.identity = self.id
        self.listener.setsockopt_string(zmq.IDENTITY, self.id)
        self.listener.bind('tcp://*:{}'.format(self.listen_port))
        self.listener = ZMQStream(self.listener, self.loop)
        self.listener.on_recv(self.handle_listen)

        if self.pusher is True:
            self.pusher = self.context.socket(zmq.DEALER)
            #self.pusher.identity = self.id.encode('utf-8')
            #self.pusher.identity = self.id
            self.pusher.setsockopt_string(zmq.IDENTITY, self.id)
            self.pusher.connect('tcp://{}:{}'.format(self.push_ip, self.push_port))
            self.pusher = ZMQStream(self.pusher, self.loop)
            self.pusher.on_recv(self.handle_listen)
            # TODO: Make sure handle_listen knows how to handle ID-less messages

        self.logger.info('Starting IOLoop')
        self.loop.start()

    def prepare_message(self, to, key, value, repeat=True, flags=None):
        """
        If a message originates with us, a :class:`.Message` class
        is instantiated, given an ID and the rest of its attributes.

        Args:
            flags:
            repeat:
            to (str): The identity of the socket this message is to
            key (str): The type of message - used to select which method the receiver
                uses to process this message.
            value: Any information this message should contain. Can be any type, but
                must be JSON serializable.
        """
        msg = Message()
        msg.sender = self.id
        try:
            msg.to = to.decode('utf-8')
        except AttributeError:
            msg.to = to

        try:
            msg.key = key.decode('utf-8')
        except AttributeError:
            msg.key = key

        msg.value = value

        msg_num = next(self.msg_counter)
        msg.id = "{}_{}".format(self.id, msg_num)

        if not repeat:
            msg.flags['NOREPEAT'] = True

        if flags:
            for k, v in flags.items():
                msg.flags[k] = v

        return msg


    def send(self, to=None, key=None, value=None, msg=None, repeat=True, flags=None):
        """
        Send a message via our :attr:`~.Station.listener` , ROUTER socket.

        Either an already created :class:`.Message` should be passed as `msg`,
        or at least `to` and `key` must be provided for a new message created
        by :meth:`~.Station.prepare_message` .

        A :class:`threading.Timer` is created to resend the message using
        :meth:`~.Station.repeat` unless `repeat` is False.

        Args:
            flags:
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

        manual_to = False
        if not msg:
            # we're sending this ourselves, new message.
            msg = self.prepare_message(to, key, value, repeat, flags)
        elif to:
            # if given both message and to, send it to our 'to'
            # don't want to force a reserialization of the message
            manual_to = True

        if 'NOREPEAT' in msg.flags.keys():
            repeat = False

        # if we didn't send it, we shouldn't double-confirm it.
        if msg.sender not in [self.name, '_'+self.name]:
            repeat = False

        # Make sure our message has everything
        if not msg.validate():
            self.logger.error('Message Invalid:\n{}'.format(str(msg)))

        # encode message
        msg_enc = msg.serialize()

        # TODO: try/except here
        if not msg_enc:
            #set_trace(term_size=(80,40))
            self.logger.error('Message could not be encoded:\n{}'.format(str(msg)))
            return

        if manual_to:
            self.listener.send_multipart([to.encode('utf-8'), msg_enc])
        else:

            if isinstance(msg.to, list):

                self.listener.send_multipart([msg.to[0].encode('utf-8'), msg_enc])
            else:
                self.listener.send_multipart([msg.to.encode('utf-8'), msg_enc])

        # messages can have a flag that says not to log
        # log_this = True
        # if 'NOLOG' in msg.flags.keys():
        #     log_this = False


        #if msg.key != "CONFIRM":
        self.logger.debug('MESSAGE SENT - {}'.format(str(msg)))

        if repeat and not msg.key == "CONFIRM":
            # add to outbox and spawn timer to resend
            self.send_outbox[msg.id] = (time.time(), msg)
            # self.timers[msg.id] = threading.Timer(5.0, self.repeat, args=(msg.id,'send'))
            # self.timers[msg.id].start()
            #self.outbox.put((msg.id))

    def push(self,  to=None, key = None, value = None, msg=None, repeat=True, flags=None):
        """
        Send a message via our :attr:`~.Station.pusher` , DEALER socket.

        Unlike :meth:`~.Station.send` , `to` is not required. Every message
        is always sent to :attr:`~.Station.push_id` . `to` can be included
        to send a message further up the network tree to a networking object
        we're not directly connected to.

        Either an already created :class:`.Message` should be passed as `msg`,
        or at least `key` must be provided for a new message created
        by :meth:`~.Station.prepare_message` .

        A :class:`threading.Timer` is created to resend the message using
        :meth:`~.Station.repeat` unless `repeat` is False.

        Args:
            flags:
            to (str): The identity of the socket this message is to. If not included,
                sent to :meth:`~.Station.push_id` .
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
            msg = self.prepare_message(to, key, value, repeat, flags)

        if 'NOREPEAT' in msg.flags.keys():
            repeat = False

        log_this = True
        if 'NOLOG' in msg.flags.keys():
            log_this = False

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
        self.pusher.send_multipart([self.push_id, bytes(msg.to, encoding="utf-8"), msg_enc])

        if not (msg.key == "CONFIRM") and log_this:
            self.logger.debug('MESSAGE PUSHED - {}'.format(str(msg)))

        if repeat and not msg.key == 'CONFIRM':
            # add to outbox and spawn timer to resend
            self.push_outbox[msg.id] = (time.time(), msg)
            #self.timers[msg.id] = threading.Timer(5.0, self.repeat, args=(msg.id, 'push'))
            #self.timers[msg.id].start()

    def repeat(self):
        """
        Periodically (according to :attr:`~.repeat_interval`) resend messages that haven't been confirmed

        TTL is decremented, and messages are resent until their TTL is 0.

        """
        while not self.closing.is_set():
            # make local copies
            push_outbox = copy(self.push_outbox)
            send_outbox = copy(self.send_outbox)

            # try to send any outstanding messages and delete if too old
            if len(push_outbox)>0:
                for id in push_outbox.keys():
                    if push_outbox[id][1].ttl <= 0:
                        self.logger.warning('PUBLISH FAILED {} - {}'.format(id, str(push_outbox[id][1])))
                        try:
                            del self.push_outbox[id]
                        except KeyError:
                            # fine, already deleted
                            pass
                    else:
                        # if we didn't just put this message in our outbox
                        if (time.time() - push_outbox[id][0]) > self.repeat_interval*2:

                            self.logger.debug('REPUBLISH {} - {}'.format(id, str(push_outbox[id][1])))
                            self.pusher.send_multipart([self.push_id, push_outbox[id][1].serialize()])
                            self.push_outbox[id][1].ttl -= 1


            
            if len(send_outbox)>0:
                for id in send_outbox.keys():
                    if send_outbox[id][1].ttl <= 0:
                        self.logger.warning('PUBLISH FAILED {} - {}'.format(id, str(send_outbox[id][1])))
                        try:
                            del self.send_outbox[id]
                        except KeyError:
                            # fine, already deleted
                            pass

                    else:
                        # if we didn't just put this message in our outbox
                        if (time.time() - send_outbox[id][0]) > self.repeat_interval*2:

                            self.logger.debug('REPUBLISH {} - {}'.format(id, str(send_outbox[id][1])))
                            self.listener.send_multipart([bytes(send_outbox[id][1].to, encoding="utf-8"), send_outbox[id][1].serialize()])
                            self.send_outbox[id][1].ttl -= 1
                    
            # wait to do it again
            time.sleep(self.repeat_interval)



    def l_confirm(self, msg):
        """
        Confirm that a message was received.

        Args:
            msg (:class:`.Message`): A confirmation message - note that this message has its own unique ID, so the value of this message contains the ID of the message that is being confirmed
        """
        # confirmation that a published message was received
        # value should be the message id

        # delete message from outbox if we still have it
        try:
            if msg.value in self.send_outbox.keys():
                del self.send_outbox[msg.value]
            elif msg.value in self.push_outbox.keys():
                del self.push_outbox[msg.value]
        except KeyError:
            # fine, already deleted
            pass

        # if this is a message to our internal net_node, make sure it gets the memo that shit was confirmed too
        if msg.to == "_{}".format(self.id):
            self.send("_{}".format(self.id), 'CONFIRM', msg.value)


        #self.logger.info('CONFIRMED MESSAGE {}'.format(msg.value))

    def l_stream(self, msg):
        """
        Reconstitute the original stream of messages and call their handling methods

        The ``msg`` should contain an ``inner_key`` that indicates the key, and thus the
        handling method.

        Args:
            msg (dict): Compressed stream sent by :meth:`Net_Node._stream`
        """
        listen_fn = self.listens[msg.value['inner_key']]
        old_value = copy(msg.value)
        delattr(msg, 'value')
        msg.key = old_value['inner_key']
        for v in old_value['payload']:
            if isinstance(v, dict) and ('headers' in old_value.keys()):
                v.update(old_value['headers'])
            msg.value = v
            listen_fn(msg)

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
        #####################33
        # Parse the message


        if len(msg)==1:
            # from our dealer, these are always to us.
            send_type = 'dealer'
            #msg = json.loads(msg[0])
            #msg = Message(**msg)
            msg = Message(msg[0])

        elif len(msg)>=2:
            # from the router
            send_type = 'router'
            sender = msg[0]

            # if this message was a multihop message, store the route
            if len(msg)>4:
                self.routes[sender] = msg[0:-3]

            # # if this is a new sender, add them to the list
            if sender not in self.senders.keys():
                self.senders[sender] = ""
                self.senders[b'_' + sender] = ''

            # connection pings are blank frames,
            # respond to let them know we're alive
            if msg[-1] == b'':
                self.listener.send_multipart(msg)
                return

            # if this message wasn't to us, forward without deserializing
            # the second to last should always be the intended recipient
            unserialized_to = msg[-2]
            if unserialized_to.decode('utf-8') not in [self.id, "_{}".format(self.id)]:
                if unserialized_to not in self.senders.keys() and self.pusher:
                    # if we don't know who they are and we have a pusher, try to push it
                    self.pusher.send_multipart([self.push_id, unserialized_to, msg[-1]])
                else:
                    #if we know who they are or not, try to send it through router anyway.
                    self.listener.send_multipart([unserialized_to, unserialized_to, msg[-1]])

                # self.logger.debug('FORWARDING: to - {}, {}'.format(unserialized_to, msg[-1][:100] if len(msg[-1])>100 else msg[-1]))

                return

            #msg = json.loads(msg[-1])
            #msg = Message(**msg)
            #set_trace(term_size=(80, 24))
            msg = Message(msg[-1])


            # if this is a new sender, add them to the list
            if msg['sender'] not in self.senders.keys():
                self.senders[msg['sender']] = ""
                self.senders['_' + msg['sender']] = ''

        else:
            self.logger.error('Dont know what this message is:{}'.format(msg))
            return

        # Check if our listen was sent properly
        # if not msg.validate():
        #     self.logger.error('Message failed to validate:\n{}'.format(str(msg)))
        #     return




        ###################################
        # Handle the message
        # if this message has a multihop 'to' field, forward it along

        # some messages have a flag not to log them
        # log_this = True
        # if 'NOLOG' in msg.flags.keys():
        #     log_this = False
        
        if isinstance(msg.to, list):
            if len(msg.to) == 1:
                msg.to = msg.to[0]

        if isinstance(msg.to, list):
            # pop ourselves off the list
            _ = msg.to.pop(0)

            # if the next recipient in the list is our push-parent, push it
            if msg.to[0] == self.push_id:
                self.push(msg=msg)
            else:
                self.send(msg=msg)
        # if this message is to us, just handle it and return
        elif msg.to in [self.id, "_{}".format(self.id)]:
            if (msg.key != "CONFIRM"):
                self.logger.debug('RECEIVED: {}'.format(str(msg)))
            # Log and spawn thread to respond to listen
            try:
                listen_funk = self.listens[msg.key]
                listen_thread = threading.Thread(target=listen_funk, args=(msg,))
                listen_thread.start()
            except KeyError:
                self.logger.exception('ERROR: No function could be found for msg id {} with key: {}'.format(msg.id, msg.key))


            # send a return message that confirms even if we except
            # don't confirm confirmations
            if (msg.key != "CONFIRM") and ('NOREPEAT' not in msg.flags.keys()):
                if send_type == 'router':
                    self.send(msg.sender, 'CONFIRM', msg.id)
                elif send_type == 'dealer':
                    self.push(msg.sender, 'CONFIRM', msg.id)
            return

        # otherwise, if it's to someone we know about, send it there
        elif self.child and (msg.to == 'T'):
            # FIXME UGLY HACK
            self.push(msg=msg)
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
        if (msg.key != "CONFIRM") and ('NOREPEAT' not in msg.flags.keys()):
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
        if hasattr(prefs, 'LOGLEVEL'):
            loglevel = getattr(logging, prefs.LOGLEVEL)
        else:
            loglevel = logging.WARNING
        self.logger.setLevel(loglevel)
        self.logger.info('Station Logging Initiated')

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

    def release(self):
        self.closing.set()
        self.terminate()

        # Stopping the loop should kill the process, as it's what's holding us in run()
        #self.loop.stop()


class Terminal_Station(Station):
    """
    :class:`~.networking.Station` object used by :class:`~.Terminal`
    objects.

    Spawned without a :attr:`~.Station.pusher`.

    **Listens**

    +-------------+-------------------------------------------+-----------------------------------------------+
    | Key         | Method                                    | Description                                   |
    +=============+===========================================+===============================================+
    | 'PING'      | :meth:`~.Terminal_Station.l_ping`         | We are asked to confirm that we are alive     |
    +-------------+-------------------------------------------+-----------------------------------------------+
    | 'INIT'      | :meth:`~.Terminal_Station.l_init`         | Ask all pilots to confirm that they are alive |
    +-------------+-------------------------------------------+-----------------------------------------------+
    | 'CHANGE'    | :meth:`~.Terminal_Station.l_change`       | Change a parameter on the Pi                  |
    +-------------+-------------------------------------------+-----------------------------------------------+
    | 'STOPALL'   | :meth:`~.Terminal_Station.l_stopall`      | Stop all pilots and plots                     |
    +-------------+-------------------------------------------+-----------------------------------------------+
    | 'KILL'      | :meth:`~.Terminal_Station.l_kill`         | Terminal wants us to die :(                   |
    +-------------+-------------------------------------------+-----------------------------------------------+
    | 'DATA'      | :meth:`~.Terminal_Station.l_data`         | Stash incoming data from a Pilot              |
    +-------------+-------------------------------------------+-----------------------------------------------+
    | 'STATE'     | :meth:`~.Terminal_Station.l_state`        | A Pilot has changed state                     |
    +-------------+-------------------------------------------+-----------------------------------------------+
    | 'HANDSHAKE' | :meth:`~.Terminal_Station.l_handshake`    | A Pi is telling us it's alive and its IP      |
    +-------------+-------------------------------------------+-----------------------------------------------+
    | 'FILE'      | :meth:`~.Terminal_Station.l_file`         | The pi needs some file from us                |
    +-------------+-------------------------------------------+-----------------------------------------------+

    """

    plot_timer = None
    #send_plot = threading.Event()
    #send_plot.clear()
    # dict of threading events that determine how frequently we send plot updates
    sent_plot = {}

    def __init__(self, pilots):
        """
        Args:
            pilots (dict): The :attr:`.Terminal.pilots` dictionary.
        """
        super(Terminal_Station, self).__init__()

        # by default terminal doesn't have a pusher, everything connects to it
        self.pusher = False

        # Store some prefs values
        self.listen_port = prefs.MSGPORT
        self.id = 'T'

        # Message dictionary - What method to call for each type of message received by the terminal class
        self.listens.update({
            'PING':      self.l_ping,  # We are asked to confirm that we are alive
            'INIT':      self.l_init,  # We should ask all the pilots to confirm that they are alive
            'CHANGE':    self.l_change,  # Change a parameter on the Pi
            'STOPALL':   self.l_stopall, # Stop all pilots and plots
            'KILL':      self.l_kill,  # Terminal wants us to die :(
            'DATA':      self.l_data,  # Stash incoming data from an autopilot
            'CONTINUOUS': self.l_continuous, # handle incoming continuous data
            'STATE':     self.l_state,  # The Pi is confirming/notifying us that it has changed state
            'HANDSHAKE': self.l_handshake, # initial connection with some initial info
            'FILE':      self.l_file,  # The pi needs some file from us
        })

        # dictionary that keeps track of our pilots
        self.pilots = pilots

        # start a timer at the draw FPS of the terminal -- only send
        if hasattr(prefs, 'DRAWFPS'):
            self.data_fps = float(prefs.DRAWFPS)
        else:
            self.data_fps = 20
        self.data_ifps = 1.0/self.data_fps



    def start_plot_timer(self):
        """
        Start a timer that controls how often streamed video frames are sent to
        :class:`.gui.Video` plots.
        """
        self.plot_timer = threading.Thread(target=self._fps_clock)
        self.plot_timer.setDaemon(True)
        self.plot_timer.start()


    def _fps_clock(self):
        while not self.closing.is_set():
            for k, v in self.sent_plot.items():
                try:
                    v.set()
                except:
                    pass
                    # TODO: Too General

            #self.send_plot.set()
            time.sleep(self.data_ifps)


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
        self.send(msg.sender, 'STATE', flags={'NOLOG':True})

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
            self.send(p, 'PING', flags={'NOLOG':True})


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

        Stop the :attr:`.Station.loop`

        Args:
            msg (:class:`.Message`):
        """
        self.logger.info('Received kill request')

        self.closing.set()

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
        #self.send('_T', 'DATA', msg.value, flags=msg.flags)
        self.send(to='_T', msg=msg)

        # Send to plot widget, which should be listening to "P_{pilot_name}"
        #self.send('P_{}'.format(msg.value['pilot']), 'DATA', msg.value, flags=msg.flags)
        self.send(to='P_{}'.format(msg.value['pilot']), msg=msg)

    def l_continuous(self, msg):
        """
        Handle the storage of continuous data

        Forwards all data on to the Terminal's internal :class:`Net_Node`,
        send to :class:`.Plot` according to update rate in ``prefs.DRAWFPS``

        Args:
            msg (dict): A continuous data message
        """

        if not self.plot_timer:
            self.start_plot_timer()

        # Send through to terminal
        #msg.value.update({'continuous':True})
        self.send(to='_T', msg=msg)

        # Send to plot widget, which should be listening to "P_{pilot_name}"
        if msg.sender not in self.sent_plot.keys():
            self.sent_plot[msg.sender] = threading.Event()
        if self.sent_plot[msg.sender].is_set():
            self.send(to='P_{}'.format(msg.value['pilot']), msg=msg)
            self.sent_plot[msg.sender].clear()


    # def l_continuous(self, msg):
    #
    #     # Send through to terminal
    #     msg.value.update({'continuous':True})
    #     self.send('_T', 'DATA', msg.value, flags=msg.flags)
    #
    #     # Send to plot widget, which should be listening to "P_{pilot_name}"
    #     self.send('P_{}'.format(msg.value['pilot']), 'DATA', msg.value, flags=msg.flags)



    def l_state(self, msg):
        """
        A Pilot has changed state.

        Stash in 'state' field of pilot dict and send along to _T

        Args:
            msg (:class:`.Message`):
        """
        if msg.sender in self.pilots.keys():
            #if 'state' in self.pilots[msg.sender].keys():
                # if msg.value == self.pilots[msg.sender]['state']:
                #     # if we've already gotten this one, don't send to terminal
                #     return
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

        self.send(msg.sender, 'FILE', file_message)

class Pilot_Station(Station):
    """
    :class:`~.networking.Station` object used by :class:`~.Pilot`
    objects.

    Spawned with a :attr:`~.Station.pusher` connected back to the
    :class:`~.Terminal` .

    **Listens**
    
    +-------------+-------------------------------------+-----------------------------------------------+
    | Key         | Method                              | Description                                   |
    +=============+=====================================+===============================================+
    | 'STATE'     | :meth:`~.Pilot_Station.l_state`     | Pilot has changed state                       |
    | 'COHERE'    | :meth:`~.Pilot_Station.l_cohere`    | Make sure our data and the Terminal's match.  |
    | 'PING'      | :meth:`~.Pilot_Station.l_ping`      | The Terminal wants to know if we're listening |
    | 'START'     | :meth:`~.Pilot_Station.l_start`     | We are being sent a task to start             |
    | 'STOP'      | :meth:`~.Pilot_Station.l_stop`      | We are being told to stop the current task    |
    | 'PARAM'     | :meth:`~.Pilot_Station.l_change`    | The Terminal is changing some task parameter  |
    | 'FILE'      | :meth:`~.Pilot_Station.l_file`      | We are receiving a file                       |
    +-------------+-------------------------------------+-----------------------------------------------+

    """
    def __init__(self):
        # Pilot has a pusher - connects back to terminal
        self.pusher = True
        if prefs.LINEAGE == 'CHILD':
            self.push_id = prefs.PARENTID.encode('utf-8')
            self.push_port = prefs.PARENTPORT
            self.push_ip = prefs.PARENTIP
            self.child = True

        else:
            self.push_id = b'T'
            self.push_port = prefs.PUSHPORT
            self.push_ip = prefs.TERMINALIP
            self.child = False

        # Store some prefs values
        self.listen_port = prefs.MSGPORT

        #self.id = prefs.NAME.encode('utf-8')
        self.id = prefs.NAME
        self.pi_id = "_{}".format(self.id)
        self.subject = None # Store current subject ID
        self.state = None # store current pi state
        self.child = False # Are we acting as a child right now?
        self.parent = False # Are we acting as a parent right now?

        super(Pilot_Station, self).__init__()

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
            'HANDSHAKE': self.l_noop,
            'CALIBRATE_PORT': self.l_forward,
            'CALIBRATE_RESULT': self.l_forward,
            'BANDWIDTH': self.l_forward
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

        self.push(to=self.push_id, key='STATE', value=msg.value)


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
        self.push(key='STATE', value=self.state, flags={'NOLOG':True})

    def l_start(self, msg):
        """
        We are being sent a task to start

        If we need any files, request them.

        Then send along to the pilot.

        Args:
            msg (:class:`.Message`): value will contain a dictionary containing a task
                description.
        """
        self.subject = msg.value['subject']

        # TODO: Refactor into a general preflight check.
        # First make sure we have any sound files that we need
        # TODO: stim managers need to be able to return list of stimuli and this is a prime reason why
        if 'stim' in msg.value.keys():
            if 'sounds' in msg.value['stim'].keys():

                # nested list comprehension to get value['sounds']['L/R'][0-n]
                f_sounds = [sound for sounds in msg.value['stim']['sounds'].values() for sound in sounds
                            if sound['type'] in ['File', 'Speech']]
            elif 'manager' in msg.value['stim'].keys():
                # we have a manager
                if msg.value['stim']['type'] == 'sounds':
                    f_sounds = []
                    for group in msg.value['stim']['groups']:
                        f_sounds.extend([sound for sounds in group['sounds'].values() for sound in sounds
                                        if sound['type'] in ['File', 'Speech']])
            else:
                f_sounds = []

            if len(f_sounds)>0:
                # check to see if we have these files, if not, request them
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
            self.subject = msg.value['child']['subject']

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
        """
        Forwards continuous data sent by children back to terminal.

        Continuous data sources from this pilot should be streamed directly to the terminal.

        Args:
            msg (:class:`Message`): Continuous data message

        """
        if self.child:
            msg.value['pilot'] = self.parent_id
            msg.value['subject'] = self.subject
            msg.value['continuous'] = True
            self.push(to='T', key='DATA', value=msg.value, repeat=False)
        else:
            self.logger.warning('Received continuous data but no child found, \
                                continuous data should be streamed directly to terminal \
                                from pilot')

    def l_child(self, msg):
        """
        Telling our child to run a task.

        Args:
            msg ():

        Returns:

        """
        if 'KEY' in msg.value.keys():
            KEY = msg.value['keys']
        else:
            KEY = 'START'
        self.send(to=prefs.CHILDID, key=KEY, value=msg.value)

    def l_forward(self, msg):
        """
        Just forward the message to the pi.
        """
        self.send(to=self.pi_id, key=msg.key, value=msg.value)





#####################################

class Net_Node(object):
    """
    Drop in networking object to be given to any sub-object
    behind some external-facing :class:`.Station` object.

    These objects are intended to communicate locally, within a piece of hardware,
    though not necessarily within the same process.

    To minimize the complexity of the network topology, Net_Nodes
    must communicate through a :class:`.Station` ROUTER, rather than
    address each other directly.

    Args:
        id (str): What are we known as? What do we set our :attr:`~zmq.Socket.identity` as?
        upstream (str): The identity of the ROUTER socket used by our upstream :class:`.Station` object.
        port (int): The port that our upstream ROUTER socket is bound to
        listens (dict): Dictionary of functions to call for different types of messages.
            keys match the :attr:`.Message.key`.
        instance (bool): Should the node try and use the existing zmq context and tornado loop?
        upstream_ip (str): If this Net_Node is being used on its own (ie. not behind a :class:`.Station`), it can directly connect to another node at this IP. Otherwise use 'localhost' to connect to a station.
        route_port (int): Typically, Net_Nodes only have a single Dealer socket and receive messages from their encapsulating :class:`.Station`, but
            if you want to take this node offroad and use it independently, an int here binds a Router to the port.

    Attributes:
        context (:class:`zmq.Context`):  zeromq context
        loop (:class:`tornado.ioloop.IOLoop`): a tornado ioloop
        sock (:class:`zmq.Socket`): Our DEALER socket.
        id (str): What are we known as? What do we set our :attr:`~zmq.Socket.identity` as?
        upstream (str): The identity of the ROUTER socket used by our upstream :class:`.Station` object.
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
    repeat_interval = 5 # how many seconds to wait before trying to repeat a message

    def __init__(self, id, upstream, port, listens, instance=True, upstream_ip='localhost',
                 daemon=True, expand_on_receive=True):
        """

        """
        if instance:
            self.context = zmq.Context.instance()
            self.loop    = IOLoop.current()
        else:
            self.context = zmq.Context()
            self.loop    = IOLoop()

        self.closing = threading.Event()
        self.closing.clear()

        # we have a few builtin listens
        self.listens = {
            'CONFIRM': self.l_confirm,
            #'STREAM' : self.l_stream
        }
        # then add the rest
        self.listens.update(listens)

        #self.id = id.encode('utf-8')
        self.id = id
        #self.upstream = upstream.encode('utf-8')
        self.upstream = upstream
        self.port = int(port)

        # self.connected = False
        self.msg_counter = count()

        # try to get a logger
        self.init_logging()

        # If we were given an explicit IP to connect to, stash it
        self.upstream_ip = upstream_ip

        # # If we want to be able to have messages sent to us directly, make a router at this port
        # self.route_port = route_port

        self.daemon = daemon

        self.streams = {}

        self.expand = expand_on_receive

        if hasattr(prefs, 'SUBJECT'):
            self.subject = prefs.SUBJECT.encode('utf-8')
        else:
            self.subject = None

        self.init_networking()

    def __del__(self):
        self.release()

    def init_networking(self):
        """
        Creates socket, connects to specified port on localhost,
        and starts the :meth:`~Net_Node.threaded_loop` as a daemon thread.
        """
        self.sock = self.context.socket(zmq.DEALER)
        #self.sock.identity = self.id
        self.sock.setsockopt_string(zmq.IDENTITY, self.id)
        #self.sock.probe_router = 1

        # if used locally (typical case), connect to localhost
        self.sock.connect('tcp://{}:{}'.format(self.upstream_ip, self.port))

        # wrap in zmqstreams and start loop thread
        self.sock = ZMQStream(self.sock, self.loop)
        self.sock.on_recv(self.handle_listen)

        # if self.route_port:
        #     # if want to directly receive messages, bind a router port
        #     self.router = self.context.socket(zmq.ROUTER)
        #     self.router.identity = self.id
        #     self.router.bind('tcp://*:{}'.format(self.route_port))
        #     self.router = ZMQStream(self.router, self.loop)
        #     self.router.on_recv(self.handle_listen)


        self.loop_thread = threading.Thread(target=self.threaded_loop)
        if self.daemon:
            self.loop_thread.daemon = True
        self.loop_thread.start()

        # self.repeat_thread = threading.Thread(target=self.repeat)
        # if self.daemon:
        #     self.repeat_thread.daemon = True
        # self.repeat_thread.start()

        #self.connected = True

    def threaded_loop(self):
        """
        Run in a thread, either starts the IOLoop, or if it
        is already started (ie. running in another thread),
        breaks.
        """

        while not self.closing.is_set():
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
            Unlike :meth:`.Station.handle_listen` , only the :attr:`.Message.value`
            is given to listen methods. This was initially intended to simplify these
            methods, but this might change in the future to unify the messaging system.

        Args:
            msg (str): JSON :meth:`.Message.serialize` d message.
        """
        # messages from dealers are single frames because we only have one connected partner
        # and that's the dealer spec lol

        #msg = json.loads(msg[0])

        #msg = Message(**msg)
        # Nodes expand arrays by default as they're expected to
        msg = Message(msg[-1], expand_arrays=self.expand)

        # Check if our listen was sent properly
        if not msg.validate():
            if self.logger:
                self.logger.error('Message failed to validate:\n{}'.format(str(msg)))
            return


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

        if isinstance(msg.to, list):
            if len(msg.to) == 1:
                msg.to = msg.to[0]

        if isinstance(msg.to, list):
            # not to us, just keep it going
            _ = msg.to.pop(0)
            self.send(msg=msg, repeat=False)

        try:
            listen_funk = self.listens[msg.key]
            listen_thread = threading.Thread(target=listen_funk, args=(msg.value,))
            listen_thread.start()
        except KeyError:
            if msg.key=="STREAM":
                try:
                    listen_thread = threading.Thread(target=self.l_stream, args=(msg,))
                    listen_thread.start()
                except Exception as e:
                    self.logger.exception(e)

            self.logger.error('MSG ID {} - No listen function found for key: {}'.format(msg.id, msg.key))

        if (msg.key != "CONFIRM") and ('NOREPEAT' not in msg.flags.keys()) :
            # send confirmation
            self.send(msg.sender, 'CONFIRM', msg.id)

        log_this = True
        if 'NOLOG' in msg.flags.keys():
            log_this = False

        if self.logger and log_this:
            self.logger.debug('RECEIVED: {}'.format(str(msg)))


    def send(self, to=None, key=None, value=None, msg=None, repeat=True, flags = None, force_to = False):
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
            to (str, list): The identity of the socket this message is to. If not included,
                sent to :meth:`~.Net_Node.upstream` .
            key (str): The type of message - used to select which method the receiver
                uses to process this message.
            value: Any information this message should contain. Can be any type, but
                must be JSON serializable.
            msg (`.Message`): An already created message.
            repeat (bool): Should this message be resent if confirmation is not received?
            flags (dict):
            force_to (bool): If we really really want to use the 'to' field to address messages
                (eg. node being used for direct communication), overrides default behavior of sending to upstream.
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
            msg = self.prepare_message(to, key, value, repeat, flags)

        log_this = True
        if 'NOLOG' in msg.flags.keys():
            log_this = False

        # Make sure our message has everything
        # if not msg.validate():
        #     if self.logger:
        #         self.logger.error('Message Invalid:\n{}'.format(str(msg)))
        #     return

        # encode message
        msg_enc = msg.serialize()
        #pdb.set_trace()
        if not msg_enc:
            self.logger.error('Message could not be encoded:\n{}'.format(str(msg)))
            return

        if force_to:
            self.sock.send_multipart([bytes(msg.to, encoding="utf-8"), bytes(msg.to, encoding="utf-8"), msg_enc])
        else:
            self.sock.send_multipart([self.upstream.encode('utf-8'), bytes(msg.to, encoding="utf-8"), msg_enc])
        if self.logger and log_this:
            self.logger.debug("MESSAGE SENT - {}".format(str(msg)))

        if repeat and not msg.key == "CONFIRM":
            # add to outbox and spawn timer to resend
            self.outbox[msg.id] = (time.time(), msg)
            # self.timers[msg.id] = threading.Timer(5.0, self.repeat, args=(msg.id,))
            # self.timers[msg.id].start()

    def repeat(self):
        """
        Periodically (according to :attr:`~.repeat_interval`) resend messages that haven't been confirmed

        TTL is decremented, and messages are resent until their TTL is 0.

        """
        while not self.closing.is_set():
            # try to send any outstanding messages and delete if too old
            # make a local copy of dict
            outbox = copy(self.outbox)

            if len(outbox) > 0:
                for id in outbox.keys():
                    if outbox[id][1].ttl <= 0:
                        self.logger.warning('PUBLISH FAILED {} - {}'.format(id, str(outbox[id][1])))
                        try:
                            del self.outbox[id]
                        except KeyError:
                            # fine, already deleted
                            pass
                    else:
                        # if we didn't just put this message in the outbox...
                        if (time.time() - outbox[id][0]) > (self.repeat_interval*2):
                            self.logger.debug('REPUBLISH {} - {}'.format(id, str(outbox[id][1])))
                            self.sock.send_multipart([self.upstream.encode('utf-8'), outbox[id][1].serialize()])
                            self.outbox[id][1].ttl -= 1


            # wait to do it again
            time.sleep(self.repeat_interval)

    def l_confirm(self, value):
        """
        Confirm that a message was received.

        Args:
            value (str): The ID of the message we are confirming.
        """
        # delete message from outbox if we still have it
        # msg.value should contain the if of the message that was confirmed
        try:
            if value in self.outbox.keys():
                del self.outbox[value]
        except KeyError:
            # already deleted
            pass

        # # stop a timer thread if we have it
        # if value in self.timers.keys():
        #     self.timers[value].cancel()
        #     del self.timers[value]


        self.logger.debug('CONFIRMED MESSAGE {}'.format(value))

    def l_stream(self, msg):
        """
        Reconstitute the original stream of messages and call their handling methods

        The ``msg`` should contain an ``inner_key`` that indicates the key, and thus the
        handling method.

        Args:
            msg (dict): Compressed stream sent by :meth:`Net_Node._stream`
        """
        listen_fn = self.listens[msg.value['inner_key']]
        old_value = copy(msg.value)
        delattr(msg, 'value')
        for v in old_value['payload']:
            # if isinstance(v, dict) and ('headers' in old_value.keys()):
            #     v.update(old_value['headers'])
            #msg.value = v
            listen_fn(v)
    #
    # def l_stream(self, value):
    #     listen_fn = self.listens[value['inner_key']]
    #     for v in value['payload']:
    #         listen_fn(v)
    #
    #


    def prepare_message(self, to, key, value, repeat, flags=None):
        """
        Instantiate a :class:`.Message` class, give it an ID and
        the rest of its attributes.

        Args:
            flags:
            repeat:
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

        try:
            msg.to = to.decode('utf-8')
        except AttributeError:
            msg.to = to

        try:
            msg.key = key.decode('utf-8')
        except AttributeError:
            msg.key = key

        msg.value = value

        msg_num = next(self.msg_counter)
        msg.id = "{}_{}".format(self.id, msg_num)

        if not repeat:
            msg.flags['NOREPEAT'] = True


        if flags:
            for k, v in flags.items():
                msg.flags[k] = v


        return msg

    def get_stream(self, id, key, min_size=5, upstream=None, port = None, ip=None, subject=None):
        """

        Make a queue that another object can dump data into that sends on its own socket.
        Smarter handling of continuous data than just hitting 'send' a shitload of times.
        Returns:
            Queue: Place to dump ur data

        """
        if upstream is None:
            upstream = self.upstream

        if port is None:
            port = self.port

        if ip is None:
            ip = self.upstream_ip

        if subject is None:
            if self.subject:
                subject = self.subject
            elif hasattr(prefs, 'SUBJECT'):
                subject = prefs.SUBJECT

        # make a queue
        q = queue.Queue()

        stream_thread = threading.Thread(target=self._stream,
                                         args=(id, key, min_size, upstream, port, ip, subject, q))
        stream_thread.setDaemon(True)
        stream_thread.start()
        self.streams[id] = stream_thread

        self.streams[id] = stream_thread

        self.logger.info(("Stream started with configuration:\n"+
                          "ID: {}\n".format(self.id+"_"+id)+
                          "Key: {}\n".format(key)+
                          "Min Chunk Size: {}\n".format(min_size)+
                          "Upstream ID: {}\n".format(upstream) +
                          "Port: {}\n".format(port) +
                          "IP: {}\n".format(ip) +
                          "Subject: {}\n".format(subject)))



        return q


    def _stream(self, id, msg_key, min_size, upstream, port, ip, subject, q):



        # create a new context and socket
        #context = zmq.Context()
        #loop = IOLoop()
        socket = self.context.socket(zmq.DEALER)
        socket_id = "{}_{}".format(self.id, id)
        #socket.identity = socket_id
        socket.setsockopt_string(zmq.IDENTITY, socket_id)
        socket.connect('tcp://{}:{}'.format(ip, port))

        socket = ZMQStream(socket, self.loop)

        upstream = upstream.encode('utf-8')

        if subject is None:
            if hasattr(prefs, 'SUBJECT'):
                subject = prefs.SUBJECT
            else:
                subject = ""
        if isinstance(subject, bytes):
            subject = subject.decode('utf-8')

        if prefs.LINEAGE == "CHILD":
            # pilot = bytes(prefs.PARENTID, encoding="utf-8")
            pilot = prefs.PARENTID
        else:
            # pilot = bytes(prefs.NAME, encoding="utf-8")
            pilot = prefs.NAME

        msg_counter = count()

        pending_data = []

        if min_size > 1:

            for data in iter(q.get, 'END'):
                if isinstance(data, tuple):
                    # tuples are immutable, so can't serialize numpy arrays they contain
                    data = list(data)

                pending_data.append(data)

                if not socket.sending() and len(pending_data)>=min_size:
                    msg = Message(to=upstream.decode('utf-8'), key="STREAM",
                                  value={'inner_key' : msg_key,
                                         'headers'   : {'subject': subject,
                                                        'pilot'  : pilot,
                                                        'continuous': True},
                                         'payload'   : pending_data},
                                  id="{}_{}".format(id, next(msg_counter)),
                                  flags={'NOREPEAT':True, 'MINPRINT':True},
                                  sender=socket_id).serialize()
                    last_msg = socket.send_multipart((upstream, upstream, msg),
                                                     track=True, copy=True)

                    self.logger.debug("STREAM {}: Sent {} items".format(self.id+'_'+id, len(pending_data)))
                    pending_data = []
        else:
            # just send like normal messags
            for data in iter(q.get, 'END'):
                if isinstance(data, tuple):
                    # tuples are immutable, so can't serialize numpy arrays they contain
                    data = list(data)

                if not socket.sending():
                    msg = Message(to=upstream.decode('utf-8'), key=msg_key,
                                  subject=subject,
                                  pilot=pilot,
                                  continuous=True,
                                  value=data,
                                  flags={'NOREPEAT': True, 'MINPRINT': True},
                                  id="{}_{}".format(id, next(msg_counter)),
                                  sender=socket_id).serialize()
                    last_msg = socket.send_multipart((upstream, upstream, msg),
                                                     track=True, copy=True)

                self.logger.debug("STREAM {}: Sent 1 item".format(self.id + '_' + id))






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
        if hasattr(prefs, 'LOGLEVEL'):
            loglevel = getattr(logging, prefs.LOGLEVEL)
        else:
            loglevel = logging.WARNING
        self.logger.setLevel(loglevel)
        self.logger.info('{} Logging Initiated'.format(self.id))

    def release(self):
        self.closing.set()
        self.loop.stop()



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
        timestamp (str): Timestamp of message creation
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
    timestamp = None
    flags = {}
    ttl = 2 # every message starts with 2 retries. only relevant to the sender so not serialized.
    changed = False
    serialized = None

    def __init__(self, msg=None, expand_arrays = False,  **kwargs):
        # type: (object, object) -> None
        # Messages don't need to have all attributes on creation,
        # but do need them to serialize
        """
        Args:
            *args:
            **kwargs:
        """

        # optional attrs should be instance attributes so they are caught by _-dict__
        self.flags = {}
        self.timestamp = None
        self.ttl = 5

        #set_trace(term_size=(120,40))
        #if len(args)>1:
        #    Exception("Messages can only be constructed with a single positional argument, which is assumed to be a serialized message")
        #elif len(args)>0:
        if msg:
            self.serialized = msg
            if expand_arrays:
                deserialized = json.loads(msg, object_pairs_hook=self._deserialize_numpy)
            else:
                deserialized = json.loads(msg)
            kwargs.update(deserialized)

        for k, v in kwargs.items():
            setattr(self, k, v)
            #self[k] = v

        # if we're not a previous message being recreated, get a timestamp for our creation
        if 'timestamp' not in kwargs.keys():
            self.get_timestamp()

        # self.DETECTED_MINPRINT = False

    def __str__(self):
        # type: () -> str
        # if len(str(self.value))>100:
        #     self.DETECTED_MINPRINT = True
        # TODO: Make verbose/debugging mode, print value in that case.
        if self.key == 'FILE' or ('MINPRINT' in self.flags.keys()):
            me_string = "ID: {}; TO: {}; SENDER: {}; KEY: {}, FLAGS: {}".format(self.id, self.to, self.sender, self.key, self.flags)
        else:
            me_string = "ID: {}; TO: {}; SENDER: {}; KEY: {}; FLAGS: {}; VALUE: {}".format(self.id, self.to, self.sender, self.key, self.flags, self.value)
        #me_string = "ID: {}; TO: {}; SENDER: {}; KEY: {}".format(self.id, self.to, self.sender, self.key)

        return me_string

    # enable dictionary-like behavior
    def __getitem__(self, key):
        """
        Args:
            key:
        """
        #value = self._check_dec(self.__dict__[key])
        # TODO: Recursively walk looking for 'NUMPY ARRAY' and expand before giving
        return self.__dict__[key]

    def __setitem__(self, key, value):
        """
        Args:
            key:
            value:
        """
        # self.changed=True
        #value = self._check_enc(value)
        self.__dict__[key] = value

    # def __setattr__(self, key, value):
    #     self.changed=True
    #     #value = self._check_enc(value)
    #     super(Message, self).__setattr__(self, key, value)
    #     self.__dict__[key] = value

    # def __getattr__(self, key):
    #     #value = self._check_dec(self.__dict__[key])
    #     return self.__dict__[key]
    #
    # def _check_enc(self, value):
    #     if isinstance(value, np.ndarray):
    #         value = json_tricks.dumps(value)
    #     elif isinstance(value, dict):
    #         for k, v in value.items():
    #             value[k] = self._check_enc(v)
    #     elif isinstance(value, list):
    #         value = [self._check_enc(v) for v in value]
    #     return value
    #
    # def _check_dec(self, value):
    #
    #     # if numpy array, reconstitute
    #     if isinstance(value, basestring):
    #         if value.startswith('{"__ndarray__'):
    #             value = json_tricks.loads(value)
    #     elif isinstance(value, dict):
    #         for k, v in value.items():
    #             value[k] = self._check_dec(v)
    #     elif isinstance(value, list):
    #         value = [self._check_dec(v) for v in value]
    #     return value

    def _serialize_numpy(self, array):
        """
        Serialize a numpy array for sending over the wire

        Args:
            array:

        Returns:

        """
        compressed = base64.b64encode(blosc.pack_array(array)).decode('ascii')
        return {'NUMPY_ARRAY': compressed}


    def _deserialize_numpy(self, obj_pairs):
        # print(len(obj_pairs), obj_pairs)
        if (len(obj_pairs) == 1) and obj_pairs[0][0] == "NUMPY_ARRAY":
            return blosc.unpack_array(base64.b64decode(obj_pairs[0][1]))
        else:
            return dict(obj_pairs)

    def expand(self):
        """
        Don't decompress numpy arrays by default for faster IO, explicitly expand them when needed

        :return:
        """
        pass






    def __delitem__(self, key):
        """
        Args:
            key:
        """
        self.changed=True
        del self.__dict__[key]

    def __contains__(self, key):
        """
        Args:
            key:
        """
        return key in self.__dict__

    def __len__(self):
        return len(self.__dict__)

    def get_timestamp(self):
        """
        Get a Python timestamp

        Returns:
            str: Isoformatted timestamp from ``datetime``
        """
        self.timestamp = datetime.datetime.now().isoformat()

    def validate(self):
        """
        Checks if `id`, `to`, `sender`, and `key` are all defined.

        Returns:
            bool (True): Does message have all required attributes set?
        """
        valid = True
        for prop in (self.id, self.to, self.sender, self.key):
            if prop is None:
                valid = False
        return valid




    def serialize(self):
        """
        Serializes all attributes in `__dict__` using json.

        Returns:
            str: JSON serialized message.
        """

        if not self.changed and self.serialized:
            return self.serialized

        valid = self.validate()
        if not valid:
            Exception("""Message invalid at the time of serialization!\n {}""".format(str(self)))
            return False

        # msg = {
        #     'id': self.id,
        #     'to': self.to,
        #     'sender': self.sender,
        #     'key': self.key,
        #     'value': self.value
        # }
        msg = self.__dict__
        # exclude 'serialized' so it's not in there twice
        try:
            del msg['serialized']
        except KeyError:
            pass

        try:
            msg_enc = json.dumps(msg, default=self._serialize_numpy).encode('utf-8')
            self.serialized = msg_enc
            self.changed=False
            return msg_enc
        except:
            return False

def serialize_array(array):
    """
    Pack an array with :func:`blosc.pack_array` and serialize with :func:`base64.b64encode`

    Args:
        array (:class:`numpy.ndarray`): Array to serialize

    Returns:
        dict: {'NUMPY_ARRAY': base-64 encoded, blosc-compressed array.}
    """
    compressed = base64.b64encode(blosc.pack_array(array)).decode('ascii')
    return {'NUMPY_ARRAY': compressed}













































