#!/usr/bin/env python

'''
Classes for assembling a state transition matrix, timers and outputs.
This class is primarily for building state machines from scratch, for a specific task structure, you should instead write a template
Keeps the state matrix as a python class rather than converting to the flat matrix needed by the arduinio statemachine
To be used with a raspberry pi, or any other state machine that supports running python.

The state matrix is agnostic to its physical implementation - ie. knows nothing about what it's controlling.
All inputs and outputs are aliases that are resolved by the RPilot or other statemachine manager.


A state is defined by a:
    -name
    -handler: a function that computes the output states from inputs, if any.
        These should be defined as paradigm templates - 2AFC has a certain set of handlers, etc.
        What the user ultimately will call is a blank state machine and a set of template handlers; and then input their parameters

The state matrix also accepts a list of strings as persistent variables (persists), or the variables that are used by the different states across trials.
    For example, if in your handler definitions you use the variable 'biaspct' to adjust the proportion of a particular type of target, declare it with persistentvars=['biaspct']

Inspired by: http://www.python-course.eu/finite_state_machine.php
'''

__version__ = '0.1'
__author__ = 'Jonny Saunders <jsaunder@uoregon.edu>'

class StateMatrix(object):
    def __init__(self, persists = None):
        self.handlers = {}
        self.startState = None
        self.endStates = []
        self.type = None
        self.persists = persists

    def add_state(self, name, handler, start_state=0, end_state=0):
        name = name.lower()

        if start_state: #Set the start state if we haven't already
            if self.startState:
                print('Start State is already defined')
                return
            else:
                self.startState = name

        if end_state: #Same as start, but can have more than 1
            self.endStates.append(name)

        self.handlers[name] = handler






