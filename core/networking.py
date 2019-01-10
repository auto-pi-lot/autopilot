# Classes for network communication.
# Following http://zguide.zeromq.org/py:all#toc46

import json
import logging
import threading
import zmq
import time
import sys
import datetime
import os
import multiprocessing
import base64
import socket
from zmq.eventloop.ioloop import IOLoop, PeriodicCallback
from zmq.eventloop.zmqstream import ZMQStream
from warnings import warn
from collections import deque
from itertools import count

from .. import prefs

# Message structure:
# Messages flow from the Terminal class to the raspberry pi
# {key: {target, value}}
# key - what type of message is this (byte string)
# target - where should it go (json encoded on receipt, converted to byte string)
#          For the Pilot, target refers to the mouse so the Terminal can plot/store data
# value - what is the message (json encoded)
# This structure allows us to sensibly 'unwrap' messages:
# the handler function for each socket passes the target and value to the appropriate function for a given key
# the key function will do whatever it needs to do with value and send it on to target

# Listens

# TODO: Periodically ping pis to check that they are still responsive

class Networking(multiprocessing.Process):
    ctx          = None    # Context
    loop         = None    # IOLoop
    push_ip      = None    # IP to push to
    push_port    = None    # Publisher Port
    push_id      = ""    # Identity of the Router we push to
    listen_port  = None    # Listener Port
    message_port = None    # Messenger Port
    pusher       = None    # pusher socket - a dealer socket that connects to other routers
    listener     = None    # Listener socket - a router socket to send/recv messages
    logger       = None    # Logger....
    log_handler  = None
    log_formatter = None
    id           = None    # What are we known as?
    ip           = None    # whatismy
    listens      = None    # Dictionary of functions to call for different types of messages
    senders      = [] # who has sent us stuff (ie. directly connected)

    def __init__(self, prefs=None):
        super(Networking, self).__init__()
        # Prefs should be passed by the terminal, if not, try to load from default locatio
        # QtCore.QThread.__init__(self)
        if not prefs:
            try:
                with open('/usr/rpilot/prefs.json') as op:
                    self.prefs = json.load(op)
            except:
                Exception('No Prefs for networking class')
        else:
            self.prefs = prefs

        # # Store some prefs values
        # self.pub_port = self.prefs['PUBPORT']
        # self.listen_port = self.prefs['LISTENPORT']
        # self.message_port = self.prefs['MSGPORT']

        self.ip = self.get_ip()

        # Setup logging
        self.init_logging()

        self.file_block = threading.Event() # to wait for file transfer

        # number messages as we send them
        self.msg_counter = count()



    def run(self):
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
        # TODO: This would mess up multi-hop senders. we should make sure to send the whole message thru
        msg = Message()
        msg.sender = self.id
        msg.to = to
        msg.key = key
        msg.value = value

        msg_num = self.msg_counter.next()
        msg.id = "{}_{}".format(self.id, msg_num)

        return msg


    def send(self, to, key, value=None):
        # send message via the router
        # don't need to thread this because router sends are nonblocking

        msg = self.prepare_message(to, key, value)

        # Make sure our message has everything
        if not msg.validate():
            self.logger.error('Message Invalid:\n{}'.format(str(msg)))

        # encode message
        msg_enc = msg.serialize()

        if not msg_enc:
            self.logger.error('Message could not be encoded:\n{}'.format(str(msg)))
            return

        self.listener.send_multipart([to, msg_enc])

    def push(self,  to=None, key = None, value = None):
        # send message via the dealer
        # even though we only have one connection over our dealer,
        # we still include 'to' in case we are sending further upstream
        # but can push without 'to', just fill in with upstream id
        # TODO: Implement forwarding when 'to' field doesn't match ID of upstream router
        if to is None:
            to = self.push_id

        if key is None:
            self.logger.error('Push sent without Key')
            return

        msg = self.prepare_message(to, key, value)

        # Make sure our message has everything
        if not msg.validate():
            self.logger.error('Message Invalid:\n{}'.format(str(msg)))

        # encode message
        msg_enc = msg.serialize()

        if not msg_enc:
            self.logger.error('Message could not be encoded:\n{}'.format(str(msg)))
            return

        self.pusher.send_multipart([self.push_id, msg_enc])

    def handle_listen(self, msg):
        # TODO: This check is v. fragile, pyzmq has a way of sending the stream along with the message
        if len(msg)==1:
            # from our dealer
            msg = json.loads(msg[0])
            msg = Message(**msg)
        elif len(msg)==2:
            # from the router
            sender = msg[0]

            # if this is a new sender, add them to the list
            if sender not in self.senders:
                self.senders.append(sender)

            # connection pings are blank frames,
            # respond to let them know we're alive
            if msg[1] == b'':
                self.listener.send_multipart(msg)
                return

            msg = json.loads(msg[1])
            msg = Message(**msg)
        else:
            self.logger.error('Dont know what this message is:{}'.format(msg))
            return

        # Check if our listen was sent properly
        if not msg.validate():
            self.logger.error('Message failed to validate:\n{}'.format(str(msg)))
            return

        self.logger.info('RECEIVED:\n{}'.format(str(msg)))

        # if this message is to us, handle it.
        if msg.to in [self.id, "_{}".format(self.id)]:
            # Log and spawn thread to respond to listen
            listen_funk = self.listens[msg.key]
            listen_thread = threading.Thread(target=listen_funk, args=(msg,))
            listen_thread.start()
        # otherwise, if it's to someone we know about, send it there
        elif msg.to in self.senders:
            self.send(to=msg.to, key=msg.key, value=msg.value)
        # otherwise, if we have a pusher, send it there
        # it's either for them or some other upstream node we don't know about
        elif self.pusher:
            self.push(to=msg.to, key=msg.key, value=msg.value)
        else:
            self.logger.warning('Dont know how to handle message: {}'.format(str(msg)))


    def init_logging(self):

        # Setup logging
        timestr = datetime.datetime.now().strftime('%y%m%d_%H%M%S')
        log_file = os.path.join(self.prefs['LOGDIR'], 'Networking_Log_{}.log'.format(timestr))

        self.logger = logging.getLogger('networking')
        self.log_handler = logging.FileHandler(log_file)
        self.log_formatter = logging.Formatter("%(asctime)s %(levelname)s : %(message)s")
        self.log_handler.setFormatter(self.log_formatter)
        self.logger.addHandler(self.log_handler)
        self.logger.setLevel(logging.INFO)
        self.logger.info('Networking Logging Initiated')

    def get_ip(self):
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
    def __init__(self, prefs=None):
        if not prefs:
            try:
                with open('/usr/rpilot/prefs.json') as op:
                    self.prefs = json.load(op)
            except:
                Exception('No Prefs for networking class')
        else:
            self.prefs = prefs

        super(Terminal_Networking, self).__init__(self.prefs)

        # by default terminal doesn't have a pusher, everything connects to it
        self.pusher = False

        # Store some prefs values
        self.listen_port = self.prefs['LISTENPORT']
        self.id = b'T'

        # Message dictionary - What method to call for each type of message received by the terminal class
        self.listens = {
            'PING':      self.m_ping,  # We are asked to confirm that the raspberry pis are alive
            'INIT':      self.m_init,  # We should ask all the pilots to confirm that they are alive
            'START':     self.m_start_task,  # Upload task to a pilot
            'CHANGE':    self.m_change,  # Change a parameter on the Pi
            'STOP':      self.m_stop,
            'STOPALL':   self.m_stopall,
            'LISTENING': self.m_listening,  # Terminal wants to know if we're alive yet
            'KILL':      self.m_kill,  # Terminal wants us to die :(
            'DATA':      self.l_data,  # Stash incoming data from an rpilot
            'ALIVE':     self.l_alive,  # A Pi is responding to our periodic query of whether it remains alive
            # It replies with its subscription filter
            'STATE':     self.l_state,  # The Pi is confirming/notifying us that it has changed state
            'FILE':      self.l_file,  # The pi needs some file from us
        }


    ##########################
    # Message Handling Methods

    def m_ping(self, msg):
        # Ping a specific subscriber and ask if they are alive
        self.send(msg.target, 'PING')

    def m_init(self, msg):
        # Ping all pis that we are expecting given our pilot db until we get a response
        # Pass back who responds as they do to update the GUI.
        # We don't expect a response, so we don't send through normal publishing method

        # TODO: Redo this
        pass

        # # Override target if any is fed to us
        # target = b'X' # TODO: Allow all pub/sub key to be defined in setup functions
        #
        # # Publish a general ping five times, m_alive will update our list of subscribers as they respond
        # for i in range(3):
        #     msg_id = str(self.msg_counter.next())
        #     self.publisher.send_multipart([bytes(target), json.dumps({'key':'PING', 'value':'', 'id':msg_id})])
        #     self.logger.info('PUBLISH {} - Target: {}, Key: {}'.format(msg_id, target, 'PING'))
        #     time.sleep(1)
        #
        # # If we still haven't heard from pis that we expected to, we'll ping them a few more times
        # pis = set(value)
        # if not len(pis - self.subscribers) == 0:
        #     for i in range(3):
        #         awol_pis = pis - self.subscribers
        #         for p in awol_pis:
        #             msg_id = str(self.msg_counter.next())
        #             self.publisher.send_multipart([bytes(p), json.dumps({'key': 'PING', 'value': '', 'id':msg_id})])
        #             self.logger.info('PUBLISH {} - Target: {}, Key: {}'.format(msg_id, p, 'PING'))
        #         time.sleep(1)
        #
        #     # If we still haven't heard from them, tell the terminal that
        #     awol_pis = pis - self.subscribers
        #     for p in awol_pis:
        #         self.logger.warning('Requested Pilot {} was not heard from'.format(p))
        #         self.publish(b'T',{'key':'DEAD','value':p})



    def m_start_task(self, msg):
        # Just publish it
        self.send(msg.target, 'START', msg.value)

        # Then let the plot widget know so that it makes and starts a plot
        self.send(bytes('P_{}'.format(msg.target)), 'START', msg.value)

    def m_change(self, msg):
        # TODO: Should also handle param changes to GUI objects like ntrials, etc.
        pass


    def m_stop(self, msg):
        self.send(msg.target, 'STOP', msg.value)
        # and the plot widget
        self.send('P_{}'.format(msg.target), 'STOP', msg.value)

        #TODO: also pop mouse value from data function dict

    def m_stopall(self, msg):
        pass

    def m_listening(self, msg):
        self.send('_T', 'LISTENING')

    def m_kill(self, msg):
        self.logger.info('Received kill request')

        # Stopping the loop should kill the process, as it's what's holding us in run()
        self.loop.stop()


    def l_data(self, msg):
        # Send through to terminal
        self.send('_T', 'DATA', msg.value)

        # Send to plot widget, which should be listening to "P_{pilot_name}"
        self.send('P_{}'.format(msg.value['pilot']), 'DATA', msg.value)

    def l_alive(self, msg):
        # A pi has told us that it is alive and what its filter is
        self.subscribers[msg.value['pilot']] = msg.value['ip']
        self.logger.info('Received ALIVE from {}, ip: {}'.format(msg.value['pilot'], msg.value['ip']))
        # Tell the terminal
        self.send('_T', 'ALIVE', msg.value)

    def l_event(self, msg):
        pass

    def l_state(self, msg):
        pass

    def l_file(self, msg):
        # The <target> pi has requested some file <value> from us, let's send it back
        # This assumes the file is small, if this starts crashing we'll have to split the message...

        full_path = os.path.join(self.prefs['SOUNDDIR'], msg.value)
        with open(full_path, 'rb') as open_file:
            # encode in base64 so json doesn't complain
            file_contents = base64.b64encode(open_file.read())

        file_message = {'path':msg.value, 'file':file_contents}

        self.send(msg.target, 'FILE', file_message)

class Pilot_Networking(Networking):
    def __init__(self, prefs=None):
        if not prefs:
            try:
                with open('/usr/rpilot/prefs.json') as op:
                    self.prefs = json.load(op)
            except:
                Exception('No Prefs for networking class')
        else:
            self.prefs = prefs

        # Pilot has a pusher - connects back to terminal
        self.pusher = True
        self.push_id = 'T'

        # Store some prefs values
        self.listen_port = self.prefs['LISTENPORT']
        self.push_port = self.prefs['PUSHPORT']
        self.push_ip = self.prefs['TERMINALIP']
        self.id = self.prefs['NAME'].encode('utf-8')
        self.pi_id = "_{}".format(self.id)
        self.mouse = None # Store current mouse ID

        self.listens = {
            'STATE': self.m_state,  # Confirm or notify terminal of state change
            'DATA': self.m_data,  # Sending data back
            'COHERE': self.m_cohere, # Sending our temporary data table at the end of a run to compare w/ terminal's copy
            'ALIVE': self.m_alive,  # send some initial information to the terminal
            'PING': self.l_ping,  # The Terminal wants to know if we're listening
            'START': self.l_start,  # We are being sent a task to start
            'STOP': self.l_stop,  # We are being told to stop the current task
            'PARAM': self.l_change,  # The Terminal is changing some task parameter
            'FILE': self.l_file,  # We are receiving a file
        }

        super(Pilot_Networking, self).__init__(self.prefs)


    ###########################3
    # Message/Listen handling methods
    def m_state(self, msg):
        # Save locally so we can respond to queries on our own, then push 'er on through
        # Value will just have the state, we want to add our name
        self.state = msg.value
        self.push(key='STATE', value=msg.value)

    def m_data(self, msg):
        # Just sending it along after appending the mouse name
        msg.value['mouse'] = self.mouse
        msg.value['pilot'] = self.id
        self.push(key='DATA', value=msg.value)

    def m_cohere(self, msg):
        # Send our local version of the data table so the terminal can double check
        pass

    def m_alive(self, msg):
        # TODO: This is probably redundant with l_ping
        # just say hello
        self.push(key='ALIVE', value={'pilot':self.name, 'ip':self.ip, 'state':self.state})

    def l_ping(self, msg):
        # The terminal wants to know if we are alive, respond with our name and IP
        self.push(key='ALIVE', value={'pilot':self.name, 'ip':self.ip, 'state':self.state})

    def l_start(self, msg):
        self.mouse = msg.value['mouse']

        # TODO: Refactor into a general preflight check.
        # First make sure we have any sound files that we need
        if 'sounds' in msg.value.keys():
            # nested list comprehension to get value['sounds']['L/R'][0-n]
            f_sounds = [sound for sounds in msg.value['sounds'].values() for sound in sounds
                        if sound['type'] in ['File', 'Speech']]
            if len(f_sounds)>0:
                # check to see if we have these files, if not, request them
                for sound in f_sounds:
                    full_path = os.path.join(self.prefs['SOUNDDIR'], sound['path'])
                    if not os.path.exists(full_path):
                        # We ask the terminal to send us the file and then wait.
                        self.logger.info('REQUESTING SOUND {}'.format(sound['path']))
                        self.push(key='FILE', value=sound['path'])
                        # wait here to get the sound,
                        # the receiving thread will set() when we get it.
                        self.file_block.clear()
                        self.file_block.wait()

        # once we make sure we have everything, tell the Pilot to start.
        self.send(self.pi_id, 'START', msg.value)

    def l_stop(self, msg):
        self.send(self.pi_id, 'STOP')

    def l_change(self, value):
        # TODO: Changing some task parameter from the Terminal
        pass

    def l_file(self, msg):
        # The file should be of the structure {'path':path, 'file':contents}

        full_path = os.path.join(self.prefs['SOUNDDIR'], msg.value['path'])
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

#####################################

class Net_Node(object):
    context = None
    loop = None
    id = None
    upstream = None # ID of router we connect to
    port = None
    listens = None
    connected = False
    logger = None
    "pop in networking object, has to set behind some external-facing networking object"
    def __init__(self, id, upstream, port, listens, instance=True):
        if instance:
            self.context = zmq.Context.instance()
            self.loop    = IOLoop.instance()
        else:
            self.context = zmq.Context()
            self.loop    = IOLoop()

        self.id = id.encode('utf-8')
        self.upstream = upstream.encode('utf-8')
        self.port = int(port)
        self.listens = listens

        self.connected = False
        self.msg_counter = count()

        # try to get a logger
        try:
            self.logger = logging.getLogger('main')
        except:
            Warning("Net Node {} Couldn't get logger :(".format(self.id))

        self.init_networking()

    def init_networking(self):
        self.sock = self.context.socket(zmq.DEALER)
        self.sock.identity = self.id
        self.sock.probe_router = 1

        # net nodes are local only
        self.sock.connect('tcp://localhost:{}'.format(self.port))

        # wrap in zmqstreams and start loop thread
        self.sock = ZMQStream(self.sock, self.loop)
        self.sock.on_recv(self.handle_listen)

        self.loop_thread = threading.Thread(target=self.threaded_loop)
        self.loop_thread.daemon = True
        self.loop_thread.start()

        self.connected = True

    def threaded_loop(self):
        while True:
            self.loop.start()

    def handle_listen(self, msg):
        # messages from dealers are single frames because we only have one connected partner
        msg = json.loads(msg[0])
        msg = Message(**msg)

        # Check if our listen was sent properly
        if not msg.validate():
            if self.logger:
                self.logger.error('Message failed to validate:\n{}'.format(str(msg)))
            return

        if self.logger:
            self.logger.info('RECEIVED:\n{}'.format(str(msg)))

        # Log and spawn thread to respond to listen
        listen_funk = self.listens[msg.key]
        listen_thread = threading.Thread(target=listen_funk, args=(msg.value,))
        listen_thread.start()

    def send(self, to=None, key=None, value=None):
        # send message via the dealer
        # even though we only have one connection over our dealer,
        # we still include 'to' in case we are sending further upstream
        # but can push without 'to', just fill in with upstream id
        # TODO: Implement forwarding when 'to' field doesn't match ID of upstream router
        if to is None:
            to = self.upstream

        if key is None:
            if self.logger:
                self.logger.error('Push sent without Key')
            return

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

        self.sock.send_multipart([self.upstream, msg_enc])
        if self.logger:
            self.logger.info("MESSAGE SENT - \n{}".format(str(msg)))

    def prepare_message(self, to, key, value):
        # TODO: This would mess up multi-hop senders. we should make sure to send the whole message thru
        msg = Message()
        msg.sender = self.id
        msg.to = to
        msg.key = key
        msg.value = value

        msg_num = self.msg_counter.next()
        msg.id = "{}_{}".format(self.id, msg_num)

        return msg


class Message(object):
    # TODO: just make serialization handle all attributes except Files which need to be b64 encoded first.
    id = None # number of message, format {sender.id}_{number}
    to = None
    sender = None
    key = None
    # value is the only attribute that can be left None,
    # ie. with signal-type messages like "STOP"
    value = None

    def __init__(self, *args, **kwargs):
        # Messages don't need to have all attributes on creation,
        # but do need them to serialize
        if len(args)>0:
            Exception("Messages cannot be constructed with positional arguments")

        for k, v in kwargs.items():
            setattr(self, k, v)

    def __str__(self):
        if self.key == 'FILE':
            me_string = """
            id     : {}
            to     : {}
            sender : {}
            key    : {}
            """.format(self.id, self.to, self.sender, self.key)
        else:
            me_string = """
            id     : {}
            to     : {}
            sender : {}
            key    : {}
            value  : {}
            """.format(self.id, self.to, self.sender, self.key, self.value)
        return me_string

    # enable dictionary-like behavior
    def __getitem__(self, key):
        return self.__dict__[key]

    def __setitem__(self, key, value):
        self.__dict__[key] = value

    def __delitem__(self, key):
        del self.__dict__[key]

    def __contains__(self, key):
        return key in self.__dict__

    def __len__(self):
        return len(self.__dict__)

    def validate(self):
        if all([self.id, self.to, self.sender, self.key]):
            return True
        else:
            return False

    def serialize(self):
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















































