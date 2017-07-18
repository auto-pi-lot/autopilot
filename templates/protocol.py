#!/usr/bin/python2.7
"""
Allows multiple state matrices to be stacked together as steps in one protocol.
Protocols allow automatic shaping - mice automatically advance to harder stimuli, etc.
Provides methods for terminal to compute graduation criteria between steps, combining state matrices,
and saving them as a durable file (or as part of a mouse object)
"""

# This shit should be super lightweight, just storing params and testing whether it can instantiate the state matrices.
