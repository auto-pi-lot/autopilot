from autopilot.networking import Net_Node, Station, Message
import numpy as np
import zmq
import time

import pytest

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


def test_node(node_params):
    """
    Just initialize and release a net node.
    Just testing that the default params havent changed basically
    """

    id = 'init'
    node = Net_Node(**node_params(id=id))
    node.release()

def test_node_to_node(node_params):
    """
    Test that one node can send a message to another when acting as a router,
    and back


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





