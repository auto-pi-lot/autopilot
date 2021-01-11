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
from autopilot.stim.sound import sounds
from autopilot.stim import init_manager


from autopilot import prefs
import pdb
import pickle

TASK = 'TuningCurve'
	#Note that when you write a new task, you have to add it to autopilot/autopilot/tasks/__init__.py

class TuningCurve(Task):

	# play an array of tones and/or whitenoise


	STAGE_NAMES = ["playtone"] 
	#there's only one stage, which consists of a single LED flash and play a tone


	PARAMS = odict()
	PARAMS['duration']         = {'tag':'Tone Duration (ms)', 'type':'int'}
	PARAMS['inter_stimulus_interval']         = {'tag':'Inter Stimulus Interval (ms)', 'type':'int'}
	PARAMS['frequency']         = {'tag':'Tone frequency (Hz)', 'type':'int'}
	PARAMS['amplitude']         = {'tag':'Tone amplitude (0-1)', 'type':'int'}
	PARAMS['stim']           = {'tag':'Sounds',
                            'type':'sounds'}


	class TrialData(tables.IsDescription):
	        """This class allows the Subject object to make a data table with the
			correct data types. You must update it for any new data you'd like to store
			For a blinking LED there isn't much in the way of data, but we (probably) need
			to return at least something  """
	        trial_num = tables.Int32Col()

	"""the only hardware here is a digital out to flash the LED.  """
	HARDWARE = {
		'LEDS':{ 
	       'dLED': gpio.Digital_Out 
        }
	}


	#def __init__(self, stage_block=None, tone_duration=100, inter_stimulus_interval=500, frequency=1000, amplitude=.25, stim=[{"type": "Tone"}], **kwargs):
	def __init__(self, stage_block=None, stim=[{"type": "Tone"}], **kwargs):
		super(TuningCurve, self).__init__()
		# explicitly type everything to be safe.
#		self.tone_duration = int(tone_duration)
#		self.inter_stimulus_interval = int(inter_stimulus_interval)
#		self.frequency = int(frequency)
#		self.amplitude = int(amplitude)

		# This allows us to cycle through the task by just repeatedly calling self.stages.next()
		stage_list = [self.playtone] #a list of only one stage, the pulse
		self.num_stages = len(stage_list)
		self.stages = itertools.cycle(stage_list)
		self.trial_counter = itertools.count()

		# Initialize hardware
		self.init_hardware()
		self.logger.debug('Hardware initialized')

		self.stage_block = stage_block
		#this is the threading.event object that is used to advance from one stage to the next 

		# Initialize stim manager
		if not stim:
			raise RuntimeError("Cant instantiate task without stimuli!")
		else:
			self.stim_manager = init_manager(stim)
		self.logger.debug('Stimulus manager initialized')


	##################################################################################
	# Stage Functions
	##################################################################################
	def playtone(self,*args,**kwargs):
		"""
		Stage 0: a single tone and interval.
		Returns: just the trial number
		"""

		self.hardware['LEDS']['dLED'].set(1)

		# get next stim
		self.target, self.distractor, self.stim = self.stim_manager.next_stim()
		self.logger.debug(f'target: {self.target}')

		#get values from stim
		#this doesn't work yet - I don't know how to read values 
		#tone_duration=self.stim.PARAMS.duration
		##inter_stimulus_interval=self.stim.PARAMS.inter_stimulus_interval
		#self.logger.debug(f'tone duration {tone_duration}')
		#self.logger.debug(f'ISI {inter_stimulus_interval}')

		# buffer it
		#self.stim.buffer()

		self.stim.play()

		time.sleep(.5)

		self.hardware['LEDS']['dLED'].set(0)
		#self.logger.debug('light off')
		time.sleep(.5)


		self.current_trial = next(self.trial_counter)
		self.current_stage = 0
		#self.logger.debug(f'trial {self.current_trial}')

		self.stage_block.set()
		#this clears the stage block so we advance to the next stage 

		# get stim info and add to data dict
		sound_info = {k:getattr(self.stim, k) for k in self.stim.PARAMS}
		self.logger.debug(f'playtone: {sound_info}')
		
		#data.update(sound_info)
		#data.update({'type':self.stim.type})


		#return the trial number as data
		data = {'trial_num' : self.current_trial}
		return data






