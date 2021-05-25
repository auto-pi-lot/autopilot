"""
Classes for network communication.

There are two general types of network objects -

* :class:`autopilot.networking.Station` and its children are independent processes that should only be instantiated once
    per piece of hardware. They are used to distribute messages between :class:`.Net_Node` s,
    forward messages up the networking tree, and responding to messages that don't need any input from
    the :class:`~.pilot.Pilot` or :class:`~.terminal.Terminal`.
* :class:`.Net_Node` is a pop-in networking class that can be given to any other object that
    wants to send or receive messages.
"""


import base64

import blosc

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