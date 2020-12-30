import datetime
import itertools
import tables
import threading
from copy import copy
import typing
import time

import numpy as np

import autopilot.hardware.gpio
from autopilot.hardware import gpio
from autopilot.tasks import Task
from collections import OrderedDict as odict
from autopilot.core.networking import Net_Node
from autopilot.core.utils import find_recursive

from autopilot import prefs
import pdb
import pickle

TASK = 'Blink'


class Blink(Task):

	# Just blink an LED


	STAGE_NAMES = ["pulse"]


	PARAMS = odict()
	PARAMS['pulse_duration']         = {'tag':'LED Pulse Duration (ms)',
	                            'type':'int'}
	PARAMS['pulse_interval']         = {'tag':'LED Pulse Interval (ms)',
	                            'type':'int'}
	class TrialData(tables.IsDescription):
	        # This class allows the Subject object to make a data table with the correct data types. You must update it for any new data you'd like to store
	        trial_num = tables.Int32Col()

	HARDWARE = {
	 	'LEDS':{ #dLED has to be inside of a group for some reason
	       'dLED': gpio.Digital_Out
        }
	}


	def __init__(self, stage_block=None, pulse_duration=100, pulse_interval=500, **kwargs):
		super(Blink, self).__init__()
		# explicitly type everything to be safe.
		self.pulse_duration = int(pulse_duration)
		self.pulse_interval = int(pulse_interval)

	# This allows us to cycle through the task by just repeatedly calling self.stages.next()
		stage_list = [self.pulse]
		self.num_stages = len(stage_list)
		self.stages = itertools.cycle(stage_list)
		self.trial_counter = itertools.count()

		# Initialize hardware
		self.init_hardware()
		self.logger.debug('Hardware initialized')

		self.hardware['LEDS']['dLED'].set(1)
		self.logger.debug('test message')

		self.stage_block = stage_block



	##################################################################################
	# Stage Functions
	##################################################################################
	def pulse(self,*args,**kwargs):
		"""
		Stage 0: a single pulse and interval.
		Returns: just the trial number
		"""

		self.hardware['LEDS']['dLED'].set(1)
		self.logger.debug('light on')
		time.sleep(self.pulse_duration / 1000)

		self.hardware['LEDS']['dLED'].set(0)
		self.logger.debug('light off')
		time.sleep(self.pulse_interval / 1000)


		self.current_trial = next(self.trial_counter)
		self.current_stage = 0
		self.logger.debug('trial ', self.current_trial)

#		next(self.stages)
		self.stage_block.set()

		data = {'trial_num' : self.current_trial}
		return data






