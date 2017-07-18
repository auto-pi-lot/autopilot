#!/usr/bin/env python

'''
Basic testing handler: if we enter one state, go to the other state and play a sound
'''

from taskontrol.core import pystatematrix as sm

def otherstate(pin):
    names = ['state1', 'state2']
    pins = ['a', 'k']
    newname = None
    newpin = None
    if pin == pins[0]:
        newname = names[1]
        newpin = pins[1]
    else:
        newname = names[0]
        newpin = pins[0]
    print('We are now in state {}'.format(newname))
    return(newname,newpin)


def make_test_mat():
    testmat = sm.StateMatrix()
    testmat.add_state('state1',otherstate,start_state=1)
    testmat.add_state('state2',otherstate)
    return testmat

def run_test_mat():
    testmat = make_test_mat()
    nextstate = None
    nextpin = None
    handler = testmat.handlers[testmat.startState]
    while True:
        uin = raw_input('\n a or k? >')
        nextstate, nextpin = handler(uin)
        handler = testmat.handlers[nextstate]

