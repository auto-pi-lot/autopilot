"""
Networking Tests.

**Assumptions**

- In docstring examples, ``listens`` callbacks are often omitted for clarity

"""

import pytest

from autopilot.networking import Net_Node, Station, Message
import numpy as np
import zmq
import time
import multiprocessing as mp



PORTRANGE = (5000, 8000)

@pytest.fixture
def node_params():
    """
    to enforce api as well as functionality...
    """
    def _node_params(**kwargs) -> dict:
        paramdict = {
            'id': '',
            'upstream': '',
            'port': np.random.randint(*PORTRANGE),
            'listens': {},
            'instance': False,
            'upstream_ip': 'localhost',
            'router_port': None,
            'daemon': True,
            'expand_on_receive': True
        }
        paramdict.update(kwargs)
        return paramdict
    return _node_params

@pytest.fixture
def station_params():
    """
    Default params for station
    """
    def _station_params(**kwargs) -> dict:
        paramdict = {
            'id': '',
            'pusher': False,
            'push_ip': 'localhost',
            'push_port': 5001,
            'push_id': '',
            'listen_port': 5000,
            'listens': None
        }
        paramdict.update(kwargs)
        return paramdict
    return _station_params


def test_node(node_params):
    """
    :class:`.Net_Node` s can be initialized with their default parameters
    """

    id = 'init'
    node = Net_Node(**node_params(id=id))
    node.release()

def test_node_to_node(node_params):
    """
    :class:`.Net_Node` s can directly send messages to each other with ``ROUTER``/``DEALER`` pairs.

    .. code-block:: python

        >>> node_1 = Net_Node(id='a', router_port=5000)
        >>> node_2 = Net_Node(id='b', upstream='a', port=5000)
        >>> node_2.send('a', 'KEY', 'VALUE')
        >>> node_2.send('b', 'KEY', 'VALUE')
    """
    global node1_received
    global node2_received
    node1_received = False
    node2_received = False

    def l_gotit(value):
        global node1_received
        global node2_received
        if value == 'node1':
            globals()['node1_received'] = True
        elif value == 'node2':
            globals()['node2_received'] = True

    node_1_params = node_params(
        id="a",
        router_port=np.random.randint(*PORTRANGE),
        listens = {'GOTIT': l_gotit}
    )
    node_2_params = node_params(
        id='b',
        upstream='a',
        port=node_1_params['router_port'],
        listens={'GOTIT': l_gotit}
    )

    node_1 = Net_Node(**node_1_params)
    node_2 = Net_Node(**node_2_params)
    time.sleep(0.1)
    node_2.send(to='a', key='GOTIT', value='node1')
    time.sleep(0.1)
    node_1.send(to='b', key='GOTIT', value='node2')
    time.sleep(0.1)

    assert node1_received
    assert node2_received

    node_1.release()
    node_2.release()


def test_multihop(node_params, station_params):
    """
    :class:`.Message` s can be routed through multiple :class:`.Station` objects
    by using a list in the ``to`` field

    .. code-block:: python

        # send message:
        # node_1 -> station_1 -> station_2 -> station_3 -> node_3
        >>> station_1 = Station(id='station_1', listen_port=6000,
                pusher=True, push_port=6001, push_id='station_2')
        >>> station_2 = Station(id='station_2', listen_port=6001,
                pusher=True, push_port=6002, push_id='station_3',)
        >>> station_3 = Station(id='station_3', listen_port=6002)
        >>> node_1 = Net_Node(id='node_1',
                upstream='station_1', port=6000)
        >>> node_3 = Net_Node(id='node_3',
                upstream='station_3', port=6002)
        >>> node_1.send(key='KEY', value='VALUE',
                to=['station_1', 'station_2', 'station_3', 'node_3'])
    """
    # node_1 -> station_1 -> station_2 -> station_3 -> node_3

    update_lock = mp.Lock()
    n_calls = mp.Value('i', lock=True)
    n_calls.value = 0

    def gotit(self):
        print(self)
        with n_calls.get_lock():
            n_calls.value += 1

    def hello(args):
        print('hello', args)
        pass



    node_1_params = node_params(
        id='node_1',
        upstream='station_1',
        port=6000,
        listens = {'HELLO': hello, 'GOTIT': gotit}
    )
    station_1_params = station_params(
        id='station_1',
        pusher=True,
        push_port=6001,
        push_id='station_2',
        listen_port=6000,
        listens={'HELLO': hello, 'GOTIT': gotit}
    )
    station_2_params = station_params(
        id='station_2',
        pusher=True,
        push_port=6002,
        push_id='station_3',
        listen_port=6001,
        listens={'HELLO': hello, 'GOTIT': gotit}
    )
    station_3_params = station_params(
        id='station_3',
        pusher=False,
        listen_port=6002,
        listens={'HELLO': hello, 'GOTIT': gotit}
    )
    node_3_params = node_params(
        id='node_3',
        upstream='station_3',
        port=6002,
        listens={'HELLO': hello, 'GOTIT': gotit}
    )

    # init in reverse
    station_3 = Station(**station_3_params)
    station_3.start()
    time.sleep(0.1)
    node_3 = Net_Node(**node_3_params)
    time.sleep(0.1)
    station_2 = Station(**station_2_params)
    station_2.start()
    time.sleep(0.1)
    station_1 = Station(**station_1_params)
    station_1.start()
    time.sleep(0.1)
    node_1 = Net_Node(**node_1_params)
    time.sleep(0.1)

    # send messages from nodes to stations to open connection
    node_1.send('station_1', 'HELLO', '', repeat=True)
    node_3.send('station_3', 'HELLO', '', repeat=True)
    time.sleep(0.1)

    # try sending message from node_1 to node_3 through the stations
    node_1.send(to=['station_1', 'station_2', 'station_3', 'node_3'],
                key='GOTIT',
                repeat=True,
                value=0)

    time.sleep(0.2)

    try:
        assert n_calls.value == 1 # gotit was only called once (no other nodes acted on it)
        assert station_1.msgs_received.value == 2 # gotit + first ping
        assert station_2.msgs_received.value == 1 # gotit
        assert station_3.msgs_received.value == 3 # extra from the confirmation
        assert node_1.msgs_received == 1 # confirmation of first ping
        assert node_3.msgs_received == 2 # confirmation of first ping + gotit
    finally:
        station_1.release()
        station_2.release()
        station_3.release()
        node_1.release()
        node_3.release()

@pytest.mark.parametrize('do_blosc', [True, False])
@pytest.mark.parametrize('dtype', ['bool', 'uint8', 'uint16', 'uint32', 'uint64', 'int8', 'int16', 'int32', 'int64', 'float32', 'float64'])
def test_blosc(do_blosc, dtype):
    """
    Messages should be able to serialize numpy arrays both with and without blosc compression and recreate them respecting
    their dtype and shape
    """
    arr = np.zeros((100, 250), dtype=dtype)

    msg = Message(to='test', sender='test', key='test', id='test', arr=arr, blosc=do_blosc)

    serialized = msg.serialize()

    msg_deserialized = Message(msg=serialized, expand_arrays=True)

    assert np.array_equal(msg_deserialized.arr, arr)
    assert arr.dtype == msg_deserialized.arr.dtype
    assert arr.shape == msg_deserialized.arr.shape
    # check that we actually did blosc
    if do_blosc:
        assert len(serialized) < 2000
    else:
        assert len(serialized) > 2000








