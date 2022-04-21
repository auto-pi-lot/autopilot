"""
Classes for network communication.

There are two general types of network objects -

* :class:`autopilot.networking.Station` and its children are independent processes that should only be instantiated once
    per piece of hardware. They are used to distribute messages between :class:`.Net_Node` s,
    forward messages up the networking tree, and responding to messages that don't need any input from
    the :class:`~.pilot.Pilot` or :class:`~.terminal.Terminal`.
* :class:`.Net_Node` is a pop-in networking class that can be given to any other object that
    wants to send or receive messages.

The :class:`~autopilot.networking.Message` object is used to serialize and pass
messages. When sent, messages are ``JSON`` serialized (with some special magic
to compress/encode numpy arrays) and sent as ``zmq`` multipart messages.

Each serialized message, when sent, can have ``n`` frames of the format::

    [hop_0, hop_1, ... hop_n, final_recipient, serialized_message]

Or, messages can have multiple "hops" (a typical message will have one 'hop' specified
by the ``to`` field), the second to last frame is always the final intended recipient,
and the final frame is the serialized message. Note that the ``to`` field of a
:class:`~autopilot.networking.Message` object will always be the final recipient
even if a list is passed for ``to`` when sending. This lets :class:`~.networking.Station`
objects efficiently forward messages without deserializing them at every hop.
"""


import base64

import blosc2 as blosc

from autopilot.networking.station import Station, Terminal_Station, Pilot_Station
from autopilot.networking.node import Net_Node
from autopilot.networking.message import Message


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