import threading
import time
import typing
from copy import copy
from itertools import count
from typing import Union, Optional
from collections import deque
import socket

import zmq
from tornado.ioloop import IOLoop
from zmq.eventloop.zmqstream import ZMQStream

from autopilot import prefs
from autopilot.utils.loggers import init_logger
from autopilot.networking.message import Message


class Net_Node(object):
    """
    Drop in networking object to be given to any sub-object
    behind some external-facing :class:`.Station` object.

    To minimize the complexity of the network topology, the typical way to use
     ``Net_Node``s is through a :class:`.Station` ROUTER, rather than
    addressing each other directly. Practically, this means that
    all messages are sent first to the parent :class:`.networking.Station` object,
    which then handles them, forwards them, etc.
    This proved to be horribly misguided and
    will be changed in v0.5.0 to support simplified
    messaging to a ``agent_id.netnode_id`` address. Until then the networking modules
    will be in a bit of flux.

    To receive messages directly at this Net_Node, pass the ``router_port``
    which will bind a ``zmq.ROUTER`` socket, and messages will be handled as regular 'listens'
    Note that Net_Nodes assume that they are the final recipients of messages,
    and so don't handle forwarding messages (unless a ``listen`` method explicitly
    does so), and will automatically deserialize them on receipt.

    .. note::

        Listen methods currently receive only the ``value`` of a message, this will change in v0.5.0,
        where they will receive the full message like :class:`.networking.Station` objects.

    Args:
        id (str): What are we known as? What do we set our :attr:`~zmq.Socket.identity` as?
        upstream (str): The identity of the ROUTER socket used by our upstream :class:`.Station` object.
        port (int): The port that our upstream ROUTER socket is bound to
        listens (dict): Dictionary of functions to call for different types of messages.
            keys match the :attr:`.Message.key`.
        instance (bool): Should the node try and use the existing zmq context and tornado loop?
        upstream_ip (str): If this Net_Node is being used on its own (ie. not behind a :class:`.Station`), it can directly connect to another node at this IP. Otherwise use 'localhost' to connect to a station.
        router_port (int): Typically, Net_Nodes only have a single Dealer socket and receive messages from their encapsulating :class:`.Station`, but
            if you want to take this node offroad and use it independently, an int here binds a Router to the port.
        daemon (bool): Run the IOLoop thread as a ``daemon`` (default: ``True``)

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
        msg_counter (:class:`itertools.count`): counter to index our sent messages
        loop_thread (:class:`threading.Thread`): Thread that holds our loop. initialized with `daemon=True`
    """
    repeat_interval = 5 # how many seconds to wait before trying to repeat a message

    def __init__(self, id: str, upstream: str, port: int,
                 listens: typing.Dict[str, typing.Callable],
                 instance:bool=True, upstream_ip:str='localhost',
                 router_port:Optional[int] = None,
                 daemon:bool=True, expand_on_receive:bool=True):

        if instance:
            self.context = zmq.Context.instance() # type: zmq.Context
            self.loop    = IOLoop.current() # type: IOLoop
        else:
            self.context = zmq.Context()  # type: zmq.Context
            self.loop    = IOLoop() # type: IOLoop

        self.closing = threading.Event() # type: threading.Event
        self.closing.clear()

        # we have a few builtin listens
        self.listens = {
            'CONFIRM': self.l_confirm,
            #'STREAM' : self.l_stream
        } # type: typing.Dict[str, typing.Callable]
        # then add the rest
        self.listens.update(listens)

        self.id = id # type: str
        self.upstream = upstream  # type: str
        self.port = int(port)  # type: int
        self.router_port = router_port
        self.router = None # type: Optional[zmq.Socket]
        self.loop_thread = None  # type: Optional[threading.Thread]
        self.senders = {} # type: typing.Dict[bytes, str]
        self._ip = None

        # self.connected = False
        self.msg_counter = count()
        self.msgs_received = 0
        self.logger = init_logger(self)

        # If we were given an explicit IP to connect to, stash it
        self.upstream_ip = upstream_ip

        self.daemon = daemon
        self.streams = {}
        self.outbox = {}
        self.timers = {}
        self.expand = expand_on_receive

        if prefs.get( 'SUBJECT'):
            self.subject = prefs.get('SUBJECT').encode('utf-8')
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
        self.sock.setsockopt_string(zmq.IDENTITY, self.id)
        #self.sock.probe_router = 1

        # connect our dealer socket to "push" messages upstream
        self.sock.connect('tcp://{}:{}'.format(self.upstream_ip, self.port))
        self.sock = ZMQStream(self.sock, self.loop)
        self.sock.on_recv(self.handle_listen)

        # if want to directly receive messages, bind a router port
        if self.router_port is not None:
            self.router = self.context.socket(zmq.ROUTER)
            self.router.setsockopt_string(zmq.IDENTITY, self.id)
            self.router.bind('tcp://*:{}'.format(self.router_port))
            self.router = ZMQStream(self.router, self.loop)
            self.router.on_recv(self.handle_listen)

        # the loop thread keeps the ioloop alive until the program exits
        self.loop_thread = threading.Thread(target=self.threaded_loop)
        if self.daemon:
            self.loop_thread.daemon = True
        self.loop_thread.start()

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

    def handle_listen(self, msg: typing.List[bytes]):
        """
        Upon receiving a message, call the appropriate listen method
        in a new thread and send confirmation it was received.

        Note:
            Unlike :meth:`.Station.handle_listen` , only the :attr:`.Message.value`
            is given to listen methods. This was initially intended to simplify these
            methods, but this might change in the future to unify the messaging system.

        Args:
            msg (list): JSON :meth:`.Message.serialize` d message.
        """
        self.msgs_received += 1

        # if we have a router, check if this is a router msg and store
        # the sender if so
        if self.router is not None and len(msg)>=2:
            if msg[0] not in self.senders.keys():
                self.senders[msg[0]] = ''

        # Nodes expand arrays by default as they're expected to
        msg = Message(msg[-1], expand_arrays=self.expand)

        # Check if our listen was sent properly
        if not msg.validate():
            if self.logger:
                self.logger.error('Message failed to validate:\n{}'.format(str(msg)))
            return

        # unnest any list if it was a multihop message
        if isinstance(msg.to, list) and len(msg.to) == 1:
            msg.to = msg.to[0]

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

            self.logger.exception('MSG ID {} - No listen function found for key: {}'.format(msg.id, msg.key))

        if (msg.key != "CONFIRM") and ('NOREPEAT' not in msg.flags.keys()) :
            # send confirmation
            self.send(msg.sender, 'CONFIRM', msg.id)

        log_this = True
        if 'NOLOG' in msg.flags.keys():
            log_this = False

        if self.logger and log_this:
            self.logger.debug('RECEIVED: {}'.format(str(msg)))


    def send(self, to: Optional[Union[str, list]] = None,
             key:str=None,
             value:typing.Any=None,
             msg:Optional['Message']=None,
             repeat:bool=False, 
             flags = None, 
             force_to:bool = False,
             blosc:bool = False):
        """
        Send a message via our :attr:`~.Net_Node.sock` , DEALER socket.

        `to` is not required.

        * If the node doesn't have a router, (or the recipient is not
          in the :attr:`Net_Node.senders` dict ) every message
          is always sent to :attr:`~.Net_Node.upstream` . `to` can be included
          to send a message further up the network tree to a networking object
          we're not directly connected to.
        * If the node has a router, since messages can only be sent on router
          sockets after the recipient has first sent us a message, if the
          ``to`` is in the :attr:`~.Net_Node.senders` dict, it will be
          directly sent via :attr:`.Net_Node.router`
        * If the ``force_to`` arg is ``True``, send to the ``to`` recipient directly
          via the dealer :attr:`.Net_Node.sock`
        * If ``to`` is a list, or is intended to be sent as a multihop message with
          an explicit path, then networking objects will attempt to forward it
          along that path (disregarding implicit topology).

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
            blosc (bool): Tell the message to compress its serialized contents with blosc
        """
        if (key is None) and (msg is None):
            if self.logger:
                self.logger.error('Push sent without Key')
            return

        # send message via the dealer
        # even though we only have one connection over our dealer,
        # we still include 'to' in case we are sending further upstream
        # but can push without 'to', just fill in with upstream id
        if to is None:
            to = self.upstream

        # differentiate between a single 'to' and a list (ie. a multihop message)
        # in this case, 'recipient' is encoded in the message as the final node to
        # send to, and the rest of 'to' is encoded as parts in a multipart message.
        if isinstance(to, list):
            recipient = to[-1]
        else:
            recipient = to

        if not msg:
            msg = self.prepare_message(recipient, key, value, repeat, flags, blosc)

        log_this = True
        if 'NOLOG' in msg.flags.keys():
            log_this = False

        # encode message
        msg_enc = msg.serialize()
        if not msg_enc:
            self.logger.error('Message could not be encoded:\n{}'.format(str(msg)))
            return

        if isinstance(to, list):
            multipart = [bytes(hop, encoding='utf-8') for hop in to]
            multipart.append(recipient.encode('utf-8'))
            multipart.append(msg_enc)

        else:
            # the first frame will be added below if needed...
            multipart = [recipient.encode('utf-8'), msg_enc]
            if force_to or to.encode('utf-8') in self.senders.keys():
                multipart.insert(0, to.encode('utf-8'))
            else:
                multipart.insert(0, self.upstream.encode('utf-8'))

        if self.router is not None and multipart[0] in self.senders.keys():
            self.router.send_multipart(multipart)
        else:
            self.sock.send_multipart(multipart)

        if self.logger and log_this:
            self.logger.debug("MESSAGE SENT - {}".format(str(msg)))

        if repeat and not msg.key == "CONFIRM":
            # add to outbox and spawn timer to resend
            self.outbox[msg.id] = (time.time(), msg)

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


    def prepare_message(self, to, key, value, repeat, flags=None, blosc:bool=False):
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
            blosc (bool): Whether or not the message should be compressed with blosc
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
        msg.blosc = blosc

        msg_num = next(self.msg_counter)
        msg.id = "{}_{}".format(self.id, msg_num)

        if not repeat:
            msg.flags['NOREPEAT'] = True


        if flags:
            for k, v in flags.items():
                msg.flags[k] = v


        return msg

    def get_stream(self, id, key, min_size=5, upstream=None, port = None, ip=None, subject=None, q_size:Optional[int]=None):
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
            elif prefs.get( 'SUBJECT'):
                subject = prefs.get('SUBJECT')

        # make a queue
        q = deque(maxlen=q_size)

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
            if prefs.get( 'SUBJECT'):
                subject = prefs.get('SUBJECT')
            else:
                subject = ""
        if isinstance(subject, bytes):
            subject = subject.decode('utf-8')

        if prefs.get('LINEAGE') == "CHILD":
            # pilot = bytes(prefs.get('PARENTID'), encoding="utf-8")
            pilot = prefs.get('PARENTID')
        else:
            # pilot = bytes(prefs.get('NAME'), encoding="utf-8")
            pilot = prefs.get('NAME')

        msg_counter = count()

        pending_data = []

        if min_size > 1:

            while True:
                try:
                    data = q.popleft()
                except IndexError:
                    # normal, we might iterate faster than the source
                    continue
                if isinstance(data, str) and data == 'END':
                    break
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
            # just send like normal messags
            while True:
                try:
                    data = q.popleft()
                except IndexError:
                    continue

                if isinstance(data, str) and data == "END":
                    break

                if isinstance(data, tuple):
                    # tuples are immutable, so can't serialize numpy arrays they contain
                    data = list(data)

                msg = Message(to=upstream.decode('utf-8'), key=msg_key,
                              subject=subject,
                              pilot=pilot,
                              continuous=True,
                              value=data,
                              flags={'NOREPEAT': True, 'MINPRINT': True},
                              id="{}_{}".format(id, next(msg_counter)),
                              sender=socket_id).serialize()
                socket.send_multipart((upstream, upstream, msg),
                                       track=False, copy=False)

                self.logger.debug("STREAM {}: Sent 1 item".format(self.id + '_' + id))


    @property
    def ip(self) -> str:
        """
        Find our IP address

        .. todo::

            this is a copy of the :meth:`.Station.get_ip` method -- unify this in v0.5.0

        returns (str): our IPv4 address.
        """

        # shamelessly stolen from https://www.w3resource.com/python-exercises/python-basic-exercise-55.php
        # variables are badly named because this is just a rough unwrapping of what was a monstrous one-liner
        # (and i don't really understand how it works)

        if self._ip is None:

            # get ips that aren't the loopback
            unwrap00 = [ip for ip in socket.gethostbyname_ex(socket.gethostname())[2] if not ip.startswith("127.")][:1]
            # ??? truly dk
            unwrap01 = [[(s.connect(('8.8.8.8', 53)), s.getsockname()[0], s.close()) for s in
                         [socket.socket(socket.AF_INET, socket.SOCK_DGRAM)]][0][1]]

            self._ip = [l for l in (unwrap00, unwrap01) if l][0][0]

        return self._ip

    def release(self):
        self.closing.set()
        self.sock.close()
        if self.router:
            self.router.close()
        self.loop.add_callback(lambda:IOLoop.current().stop())