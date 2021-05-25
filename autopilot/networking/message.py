import base64
import datetime
import json

import blosc


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