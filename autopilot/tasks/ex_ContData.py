"""This module defines the ex_ContData Task.

This is an example showing how to return both trial-based and continuous data.   
"""

import threading
import itertools
import random
import datetime
import functools
from collections import OrderedDict as odict
import time
import queue
import tables
import numpy as np
import pandas
import autopilot.hardware.gpio
from autopilot.stim.sound import sounds
from autopilot.tasks.task import Task
from autopilot.networking import Net_Node
from autopilot import prefs
from autopilot.hardware import BCM_TO_BOARD
from autopilot.core.loggers import init_logger
from autopilot.stim.sound import jackclient

# The name of the task
# This declaration allows Subject to identify which class in this file 
# contains the task class. 
TASK = 'ex_ContData'


## Define the Task
class ex_ContData(Task):
    """The probabalistic auditory foraging task (PAFT).

    This passes through three stages: 
        choose_stimulus, wait_for_response, end_of_trial
    
    The first two stages both return TrialData. The second stage also
    returns ContinuousData.
    
    To understand the stage progression logic, see:
    * autopilot.core.pilot.Pilot.run_task - the main loop
    * autopilot.tasks.task.Task.handle_trigger - set stage trigger
    
    To understand the data saving logic, see:
    * autopilot.core.terminal.Terminal.l_data - what happens when data is sent
    * autopilot.core.subject.Subject.data_thread - how data is saved
    """
    
    ## Define the class attributes
    # This defines params we receive from terminal on session init
    # It also determines the params that are available to specify in the
    # Protocol creation GUI.
    # The params themselves are defined the protocol json.
    # Presently these can only be of type int, bool, enum (aka list), or sound
    # Defaults cannot be specified here or in the GUI, only in the corresponding
    # kwarg in __init__
    PARAMS = odict()
    PARAMS['reward'] = {
        'tag':'Reward Duration (ms)',
        'type':'int',
        }

    # Per https://docs.auto-pi-lot.com/en/latest/guide/task.html:
    # The `TrialData` object is used by the `Subject` class when a task
    # is assigned to create the data storage table
    # 'trial_num' and 'session_num' get added by the `Subject` class
    # 'session_num' is properly set by `Subject`, but 'trial_num' needs
    # to be set properly here.
    # If they are left unspecified on any given trial, they receive 
    # a default value, such as 0 for Int32Col.
    class TrialData(tables.IsDescription):
        # The trial within this session
        # Unambigously label this
        trial_in_session = tables.Int32Col()
        
        # If this isn't specified here, it will be added anyway
        trial_num = tables.Int32Col()
        
        # The chosens stimulus and response
        # Must specify the max length of the string, we use 64 to be safe
        chosen_stimulus = tables.StringCol(64)
        chosen_response = tables.StringCol(64)
        
        # The timestamps
        timestamp_trial_start = tables.StringCol(64)
        timestamp_response = tables.StringCol(64)

    # Definie continuous data
    # https://docs.auto-pi-lot.com/en/latest/guide/task.html
    # autopilot.core.subject.Subject.data_thread would like one of the
    # keys to be "timestamp"
    # Actually, no I think that is extracted automatically from the 
    # networked message, and should not be defined here
    class ContinuousData(tables.IsDescription):
        string_data = tables.StringCol(64)
        int_data = tables.Int32Col()

    # Per https://docs.auto-pi-lot.com/en/latest/guide/task.html:
    # The HARDWARE dictionary maps a hardware type (eg. POKES) and 
    # identifier (eg. 'L') to a Hardware object. The task uses the hardware 
    # parameterization in the prefs file (also see setup_pilot) to 
    # instantiate each of the hardware objects, so their naming system 
    # must match (ie. there must be a prefs.PINS['POKES']['L'] entry in 
    # prefs for a task that has a task.HARDWARE['POKES']['L'] object).
    HARDWARE = {}
    
    # This is used by the terminal to plot the results of each trial
    PLOT = {
        'data': {
            'target': 'point'
        }
    }
    
    
    ## Define the class methods
    def __init__(self, stage_block, current_trial, step_name, task_type, 
        subject, step, session, pilot, graduation, reward):
        """Initialize a new ex_ContData Task. 
        
        
        All arguments are provided by the Terminal.
        
        Note that this __init__ does not call the superclass __init__, 
        because that superclass Task inclues functions for punish_block
        and so on that we don't want to use.
        
        Some params, such as `step_name` and `task_type`, are always required 
        to be specified in the json defining this protocol
        
        Other params, such as `reward`, are custom to this particular task.
        They should be described in the class attribute `PARAMS` above, and
        their values should be specified in the protocol json.
        
        Arguments
        ---------
        stage_block (:class:`threading.Event`): 
            used to signal to the carrying Pilot that the current trial 
            stage is over
        current_trial (int): 
            If not zero, initial number of `trial_counter`
            This is set to be 1 greater than the last value of "trial_num"
            in the HDF5 file by autopilot.core.subject.Subject.prepare_run
        step_name : string
            This is passed from the "protocol" json
            Currently it is always "ex_ContData"
        task_type : string
            This is passed from the "protocol" json
            Currently it is always "ex_ContData"
        subject : string
            The name of the subject
        step : 0
            Index into the "protocol" json?
        session : int
            number of times it's been started
        pilot : string
            The name of this pilot
        graduation : dict
            Probably a dict of graduation criteria
        reward (int): 
            ms to open solenoids
            This is passed from the "protocol" json
        """    
        
        ## These are things that would normally be done in superclass __init__
        # Set up a logger first, so we can debug if anything goes wrong
        self.logger = init_logger(self)

        # This threading.Event is checked by Pilot.run_task before
        # advancing through stages. Clear it to wait for triggers; set
        # it to advance to the next stage.
        self.stage_block = stage_block
        
        # This is needed for sending Node messages
        self.subject = subject
        
        # This is used to count the trials for the "trial_num" HDF5 column
        self.counter_trials_across_sessions = itertools.count(int(current_trial))        

        # This is used to count the trials for the "trial_in_session" HDF5 column
        self.counter_trials_in_session = itertools.count(0)

        # A dict of hardware triggers
        self.triggers = {}

    
        ## Define the stages
        # Stage list to iterate
        # Iterate through these three stages forever
        stage_list = [
            self.choose_stimulus, self.wait_for_response, self.end_of_trial]
        self.num_stages = len(stage_list)
        self.stages = itertools.cycle(stage_list)        
        
        
        ## Init hardware -- this sets self.hardware, self.pin_id, and
        ## assigns self.handle_trigger to gpio callbacks
        self.init_hardware()
        
        
        ## For reporting continuous data to the Terminal
        # With instance=True, I get a threading error about current event loop
        self.node = Net_Node(
            id="T_{}".format(prefs.get('NAME')),
            upstream=prefs.get('NAME'),
            port=prefs.get('MSGPORT'),
            listens={},
            instance=False,
            )        
    
    def choose_stimulus(self):
        """A stage that chooses the stimulus"""
        # Get timestamp
        timestamp_trial_start = datetime.datetime.now()
        
        # Wait a little before doing anything
        self.logger.debug(
            'choose_stimulus: entering stage at {}'.format(
            timestamp_trial_start.isoformat()))
        time.sleep(3)
        
        # Choose stimulus randomly
        chosen_stimulus = random.choice(['stim0', 'stim1', 'stim2'])
        self.logger.debug('choose_stimulus: chose {}'.format(chosen_stimulus))
        
        # Continue to the next stage
        # CLEAR means "wait for triggers"
        # SET means "advance anyway"
        self.stage_block.set()

        # Return data about chosen_stim so it will be added to HDF5
        # I think it's best to increment trial_num now, since this is the
        # first return from this trial. Even if we don't increment trial_num,
        # it will still make another row in the HDF5, but it might warn.
        # (This hapepns in autopilot.core.subject.Subject.data_thread)
        return {
            'chosen_stimulus': chosen_stimulus,
            'timestamp_trial_start': timestamp_trial_start.isoformat(),
            'trial_num': next(self.counter_trials_across_sessions),
            'trial_in_session': next(self.counter_trials_in_session),
            }

    def wait_for_response(self):
        """A stage that waits for a response"""
        # Wait a little before doing anything
        self.logger.debug('wait_for_response: entering stage')
        time.sleep(3)
        
        # Choose response randomly
        chosen_response = random.choice(['choice0', 'choice1'])
    
        # Get timestamp of response
        timestamp_response = datetime.datetime.now()
        self.logger.debug('wait_for_response: chose {} at {}'.format(
            chosen_response, timestamp_response.isoformat()))

        # Directly report continuous data to terminal (aka _T)
        # Otherwise it can be encoded in the returned data, but that is only
        # once per stage
        # subject is needed by core.terminal.Terminal.l_data
        # pilot is needed by networking.station.Terminal_Station.l_data
        # timestamp and continuous are needed by subject.Subject.data_thread
        self.node.send(
            to='_T',
            key='DATA',
            value={
                'subject': self.subject,
                'pilot': prefs.get('NAME'),
                'continuous': True,
                'string_data': 'a long string',
                'int_data': 3,
                'timestamp': datetime.datetime.now().isoformat(),
                },
            )

        # Continue to the next stage
        self.stage_block.set()        
        
        # Return data about chosen_stim so it will be added to HDF5
        # Could also return continuous data here
        return {
            'chosen_response': chosen_response,
            'timestamp_response': timestamp_response.isoformat(),
            }        
    
    def end_of_trial(self):
        """A stage that ends the trial"""
        # Wait a little before doing anything
        self.logger.debug('end_of_trial: entering stage')
        time.sleep(3)
        
        # Cleanup logic could go here

        # Continue to the next stage
        self.stage_block.set()        
        
        # Return TRIAL_END so the Terminal knows the trial is over
        return {
            'TRIAL_END': True,
            }