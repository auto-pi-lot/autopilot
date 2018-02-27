#!/usr/bin/env python

'''
Run a simple state matrix that alternates between two states.
A state change happens either from a 2 sec timer or from the first
two inputs (center port in, left port in).
'''

__author__ = 'Santiago Jaramillo'
__created__ = '2013-03-17'

from taskontrol.core import smclient
import time

nInputs = 3  # Inputs: C,L,R
nOutputs = 3 # Outputs
nExtraTimers = 0  # No extra timers, just the one timer for each state

#                Ci  Co  Li  Lo  Ri  Ro  Tup
stateMatrix = [ [ 0,  0,  0,  0,  0,  0,  1 ] ,
                [ 2,  1,  1,  1,  1,  1,  2 ] ,
                [ 2,  2,  1,  2,  2,  2,  1 ] ]

#stateOutputs = ['\x00','\xff','\x00']
stateOutputs = [[0,0,0],[1,1,1],[0,0,0]]
stateTimers  = [  0.1,    0.8 ,    1.2  ]


sm = smclient.StateMachineClient()

version = sm.get_version()
print 'Server version {0}'.format(version)

sm.set_sizes(nInputs,nOutputs,nExtraTimers)
sm.set_state_matrix(stateMatrix)
sm.set_state_outputs(stateOutputs)
sm.set_state_timers(stateTimers)
sm.run()

print('To stop state transitions, type: sm.stop()')
print('To close the client, type: sm.close()')
