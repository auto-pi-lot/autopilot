import base64
import datetime
import json
import numpy as np

import blosc2 as blosc


class Message(object):
    """
    A formatted message that takes ``value``, sends it to ``id``, who should call
    the listen method indicated by the ``key``.

    Additional message behavior can be indicated by passing ``flags``

    Numpy arrays given in the value field are automatically serialized and deserialized
    when sending and receiving using bas64 encoding and blosc compression.

    `id`, `to`, `sender`, and `key` are required attributes,
    but any other key-value pair passed on init is added to the message's attributes
    and included in the message. All arguments not indicated in the signature are passed in
    as kwargs and stored as attributes.

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
        flags (dict): Flags determine additional message behavior. If a flag has no value associated with it,
            add it as a key with ``None`` as the value (eg. self.flags['MINPRINT'] = None), the value doesn't matter.

            * ``MINPRINT`` - don't print the value in logs (eg. when a large array is being sent)
            * ``NOREPEAT`` - sender will not seek, and recipients will not attempt to send message receipt confirmations
            * ``NOLOG`` - don't log this message! for streaming, or other instances where the constant printing of the logger is performance prohibitive
    """

    def __init__(self, msg=None, expand_arrays = False, blosc:bool=True,  **kwargs):
        """
        Args:
            msg (str): A serialized message made with :meth:`.serialize`. Optional -- can be passed rather than
                the message attributes themselves if, for example, we're receiving and reconstituting this message.
            expand_arrays (bool): If given a serialized message, if ``True``, expand and deserialize the arrays.
                Otherwise leave serialized. For speed of message forwarding -- don't deserialize if we're just forwarding
                this message.
            blosc (bool): If ``True`` (default), When serializing arrays, also compress with blosc. Stored as a flag
            *args:
            **kwargs:
        """
        self.id = None  # number of message, format {sender.id}_{number}
        self.to = None
        self.sender = None
        self.key = None
        # value is the only attribute that can be left None,
        # ie. with signal-type messages like "STOP"
        self.value = None
        self.timestamp = None
        self.changed = False
        self.serialized = None

        # optional attrs should be instance attributes so they are caught by _-dict__
        self.flags = {}
        self.timestamp = None
        self.blosc = blosc

        self.ttl = kwargs.get('ttl', 2)

        if msg:
            self.serialized = msg
            if expand_arrays:
                deserialized = json.loads(msg, object_pairs_hook=self._deserialize_numpy)
            else:
                deserialized = json.loads(msg)
            kwargs.update(deserialized)

        for k, v in kwargs.items():
            setattr(self, k, v)

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
        self.changed=True
        #value = self._check_enc(value)
        self.__dict__[key] = value


    def _serialize_numpy(self, array:np.ndarray):
        """
        Serialize a numpy array for sending over the wire

        Args:
            array:

        Returns:

        """
        if self.blosc:
            compressed = base64.b64encode(blosc.pack_array(array)).decode('ascii')
        else:
            compressed = base64.b64encode(array.tobytes()).decode('ascii')
        return {'NUMPY_ARRAY': compressed, 'DTYPE': str(array.dtype), 'SHAPE':array.shape}


    def _deserialize_numpy(self, obj_pairs):
        # print(len(obj_pairs), obj_pairs)
        if (len(obj_pairs) == 3) and obj_pairs[0][0] == "NUMPY_ARRAY":
            decode = base64.b64decode(obj_pairs[0][1])
            try:
                arr = blosc.unpack_array(decode)
            except RuntimeError:
                # cannot decompress, maybe because wasn't compressed
                arr = np.frombuffer(decode, dtype=obj_pairs[1][1]).reshape(obj_pairs[2][1])

            return arr
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