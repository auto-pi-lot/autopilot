#!/usr/bin/env python

'''
Classes for assembling a state transition matrix, timers and outputs.

NOTES:

* The state matrix is represented by a python list (of lists), in which
  each element (row) corresponds to the transitions from one state.
* The state timers are represented as a list of floats.
  One element per state.
* The outputs are represented as a list (of lists). Each element contains
  the outputs for each state as a list of 0 (off), 1 (on) or another integer
  which indicates the output should not be changed from its previous value.

'''

'''
Input format:
sma.add_state(name='STATENAME', statetimer=3,
             transitions={'EVENT':NEXTSTATE},
             outputsOn=[], outputsOff=[])


  OUTPUT WILL CHANGE TO SEPARATE TRANSITION MATRIX AND TIMERS
Output:
#       Ci  Co  Li  Lo  Ri  Ro  Tup
mat = [  0,  0,  0,  0,  0,  0,  2  ]


WRITE DOCUMENTATION ABOUT:
sm.statesNameToIndex
self.eventsDict
...

'''


#from taskontrol.settings import rigsettings
#reload(rigsettings)
from taskontrol.core import utils

__version__ = '0.3'
__author__ = 'Santiago Jaramillo <sjara@uoregon.edu>'

# XFIXME: what should be the Statetimer period?
VERYLONGTIME  = 100    # Time period to stay in a state if nothing happens
#VERYSHORTTIME = 0.0001 # Time period before jumping to next state "immediately" OBSOLETE, use 0.
SAMEOUTPUT = 7

class StateMatrix(object):
    '''
    State transition matrix.

    The default state transition matrix without extra timers has the
    following columns:

    [ Cin  Cout  Lin  Lout  Rin  Rout  Tup]

    Where the first six are for center, left and right ports, and the
    next column for the state timer.
    
    XFIXME: only one 'readystate' can be specified. It should accept many.
    '''
    def __init__(self,inputs={},outputs={},readystate='readyForNextTrial'):
        '''
        Args:
            inputs (dict): Labels for inputs. Elements should be of type str:int.
            outputs (dict): Labels for outputs. Elements should be of type str:int.
            readystate (str): name of ready-for-next-trial state.
        
        A common use is:
        self.sm = statematrix.StateMatrix(inputs=rigsettings.INPUTS,
                                          outputs=rigsettings.OUTPUTS,
                                          readystate='readyForNextTrial')
        '''
        self.inputsDict = inputs
        self.outputsDict = outputs

        self.stateMatrix = []
        self.stateTimers = []
        self.stateOutputs = []
        self.serialOutputs = []

        self.statesIndexToName = {}
        self.statesNameToIndex = {}

        self._nextStateInd = 0

        self.extraTimersIndexToName = {}
        self.extraTimersNameToIndex = {}
        self._nextExtraTimerInd = 0
        self.extraTimersDuration = []
        self.extraTimersTriggers = []

        # This dictionary is modified if ExtraTimers are used.
        self.eventsDict = {}
        for key,val in self.inputsDict.iteritems():
            self.eventsDict[key+'in'] = 2*val
            self.eventsDict[key+'out'] = 2*val+1
        self.eventsDict['Tup'] = len(self.eventsDict)

        self.nInputEvents = len(self.eventsDict)
        self.eventsDict['Forced'] = -1
        self.nOutputs = len(self.outputsDict)

        #self.readyForNextTrialStateName = readystate[0]
        #self.readyForNextTrialStateInd = readystate[1]
        self.readyForNextTrialStateName = readystate
        self._init_mat()

    def append_to_file(self,h5file,currentTrial):
        '''Append states definitions to open HDF5 file
        It ignores currentTrial'''
        statematGroup = h5file.create_group('/stateMatrix')
        utils.append_dict_to_HDF5(statematGroup,'eventsNames',self.eventsDict)
        utils.append_dict_to_HDF5(statematGroup,'outputsNames',self.outputsDict)
        utils.append_dict_to_HDF5(statematGroup,'statesNames',self.statesNameToIndex)
        utils.append_dict_to_HDF5(statematGroup,'extraTimersNames',self.extraTimersNameToIndex)

    def _make_default_row(self,stateInd):
        '''Create a transition row for a state.'''
        nExtraTimers = len(self.extraTimersNameToIndex)
        newrow = (self.nInputEvents+nExtraTimers)*[stateInd]    # Input events
        return newrow


    def _init_mat(self):
        '''
        Initialize state transition matrix with a row for the readystate.
        '''
        if len(self.stateMatrix)>1:
            raise Exception('You need to create all extra timers before creating any state.')
        self.add_state(name=self.readyForNextTrialStateName,statetimer=VERYLONGTIME)
        # -- Setting outputs off here is not a good idea. Instead we do it in dispatcher --
        #self.add_state(name=self.readyForNextTrialStateName,statetimer=VERYLONGTIME,
        #               outputsOff=self.outputsDict.keys())


    def _force_transition(self,originStateID,destinationStateID):
        '''Set Tup transition from one state to another give state numbers
        instead of state names'''
        self.stateMatrix[originStateID][self.eventsDict['Tup']] = destinationStateID
        
        
    def _update_state_dict(self,stateName,stateInd):
        '''Add name and index of a state to the dicts keeping the states list.'''
        self.statesNameToIndex[stateName] = stateInd
        self.statesIndexToName[stateInd] = stateName


    #def _updateExtraTimerDict(self,stateName,stateInd):
    #    '''Add name and index of a schedule wave to the dicts keeping the waves list.'''
    #    self.extraTimersNameToIndex[schedWaveName] = self._nextExtraTimerInd
    #    self.extraTimersIndexToName[self._nextExtraTimerInd] = schedWaveName


    def _append_state_to_list(self,stateName):
        '''Add state to the list of available states.'''        
        #if self._nextStateInd==self.readyForNextTrialStateInd:
        #    self._nextStateInd += 1  # Skip readyForNextTrialState
        self._update_state_dict(stateName,self._nextStateInd)
        self._nextStateInd += 1
        

    def _append_extratimer_to_list(self,extraTimerName):
        '''Add schedule wave to the list of available schedule waves.'''
        self.extraTimersNameToIndex[extraTimerName] = self._nextExtraTimerInd
        self.extraTimersIndexToName[self._nextExtraTimerInd] = extraTimerName
        self._nextExtraTimerInd += 1
        

    def add_state(self, name='', statetimer=VERYLONGTIME, transitions={},
                  outputsOn=[], outputsOff=[], trigger=[], serialOut=0):
        '''Add state to transition matrix.
        outputsOn:
        outputsOff
        trigger: extra-timers trigger when entering this state
        serialOut: integer (1-255) to send through serial port on entering
                      state. A value of zero means no serial output.
        '''
        
        nExtraTimers = len(self.extraTimersNameToIndex)

        # -- Find index for this state (create if necessary) --
        if name not in self.statesNameToIndex:
            self._append_state_to_list(name)
        thisStateInd = self.statesNameToIndex[name]

        # -- Add target states from specified events --
        newRow = self._make_default_row(thisStateInd)
        colTimer = self.nInputEvents+2*nExtraTimers+1
        #NewRow[colTimer] = statetimer
        for (eventName,targetStateName) in transitions.iteritems():
            if targetStateName not in self.statesNameToIndex:
                self._append_state_to_list(targetStateName)
            targetStateInd = self.statesNameToIndex[targetStateName]
            newRow[self.eventsDict[eventName]] = targetStateInd

        # -- Add row to state transition matrix --
        # XFIXME: this way to do it seems very inefficient
        while len(self.stateMatrix)<(thisStateInd+1):
            self.stateMatrix.append([])
            self.stateTimers.append([])
            self.stateOutputs.append(self.nOutputs*[SAMEOUTPUT])
            self.serialOutputs.append(0)
        self.stateMatrix[thisStateInd] = newRow
        self.stateTimers[thisStateInd] = statetimer
        for oneOutput in outputsOn:
            outputInd = self.outputsDict[oneOutput]
            self.stateOutputs[thisStateInd][outputInd] = 1
        for oneOutput in outputsOff:
            outputInd = self.outputsDict[oneOutput]
            self.stateOutputs[thisStateInd][outputInd] = 0
        self.serialOutputs[thisStateInd] = serialOut

        # -- Add this state to the list of triggers for extra timers --
        for oneExtraTimer in trigger:
            extraTimerInd = self.extraTimersNameToIndex[oneExtraTimer]
            self.extraTimersTriggers[extraTimerInd] = thisStateInd
        pass

    def add_probstate(self, name='', statetimer=VERYLONGTIME, transitions={},
                  outputsOn=[], outputsOff=[], trigger=[], serialOut=0):
        """
        Add a state with probabilistic transitions, for example to choose different target conditions in a 2AFC task
        These states are instant transitions (as they are not meant to be available to the animal) so they do not require a transition trigger
        Instead, the format of the transition dict is {nextstate:probability} - or reversed from the usual states.
        This is so that states with equal probabilities are still defined uniquely (no multiple vals in the dict)
        """



    
    def add_extratimer(self, name='', duration=0):
        '''
        Add an extra timer that will be trigger when entering a defined state,
        but can continue after state transitions.
        '''
        if name not in self.extraTimersNameToIndex:
            self._append_extratimer_to_list(name)
        else:
            raise Exception('Extra timer ({0}) has already been defined.'.format(name))
        extraTimerEventCol = self.nInputEvents + len(self.extraTimersNameToIndex)-1
        self.eventsDict['%s_Up'%name] = extraTimerEventCol
        self._init_mat() # Initialize again with different number of columns
        self.extraTimersDuration.append(duration)
        self.extraTimersTriggers.append(None) # Will be filled by add_state

    def OLD_add_schedule_wave(self, name='',preamble=0, sustain=0, refraction=0, DIOline=-1, soundTrig=0):
        '''Add a Scheduled Wave to this state machine.

        Example:
          add_schedule_wave(self, name='mySW',preamble=1.2)
          self.sm.add_state(name='first_state', statetimer=100,
                           transitions={'Cin':'second_state'},
                           actions={'Dout':LeftLED, 'ExtraTimerTrig':'mySW'})
          self.sm.add_state(name='second_state', statetimer=100,
                           transitions={'mySW_In':'first_state'})

        Note that as currently configured, you can have up to 32
        different scheduled waves defined per state machine, no more.

        From ExperPort/Modules/@StateMachineAssembler/add_scheduled_wave.m

        '''
        print 'NOT IMPLEMENTED YET'
        return


    def OLD_update_events_dict(self,name):

        ######### TEST THIS ########

        '''Add entries to the events dictionary according to the names of
        extra timers.
        OBSOLETE: see instead code in add_extratimer
        '''
        # XFIXME: the length of extraTimersNameToIndex may differ from swID+1 ???
        extraTimerEventCol = self.nInputEvents + len(self.extraTimersNameToIndex)
        self.eventsDict['%s_Up'%name] = extraTimerEventCol
        
        ###outEventCol = inEventCol + 1
        #self.eventsDict['%s_In'%name] = inEventCol
        #self.eventsDict['%s_Out'%name] = outEventCol
        #self.eventsDict['Tup'] = outEventCol+1
        #if 'ExtraTimerTrig' not in self.outputNamesDict:
        #    self.outputNamesDict['ExtraTimerTrig']=2
        #return (inEventCol,outEventCol)


    def get_matrix(self):
        # -- Check if there are orphan states or calls to nowhere --
        maxStateIDdefined = len(self.stateMatrix)-1
        for (stateName,stateID) in self.statesNameToIndex.iteritems():
            if (stateID>maxStateIDdefined) or not len(self.stateMatrix[stateID]):
                raise ValueError('State "{0}" was not defined.'.format(stateName))
        return self.stateMatrix

    def reset_transitions(self):
        defaultTransitions = self.nInputEvents*[0] # Default row of the matrix
        for stateind in self.statesIndexToName.keys():
            self.stateMatrix[stateind] = defaultTransitions
            self.stateTimers[stateind] = VERYLONGTIME
            self.stateOutputs[stateind] = self.nOutputs*[SAMEOUTPUT]

    def get_outputs(self):
        return self.stateOutputs

    def get_serial_outputs(self):
        return self.serialOutputs

    def get_ready_states(self):
        '''Return names of state that indicate the machine is
        ready to start a new trial '''
        return [self.readyForNextTrialStateName]

    def get_state_timers(self):
        return self.stateTimers

    def get_sched_waves(self):
        # XFIXME: check if there are orphan SW
        return self.extraTimersMat


    def get_states_dict(self,order='NameToIndex'):
        '''
        Return mapping between states names and indices.

        'order' can be 'NameToIndex' or 'IndexToName'.
        '''
        if order=='NameToIndex':
            return self.statesNameToIndex
        elif order=='NameToIndex':
            return self.statesIndexToName
        else:
            raise ValueError('Order not valid.')


    def __str__(self):
        '''String representation of transition matrix.'''
        matstr = ''
        revEventsDict = {}
        for key in self.eventsDict:
            if key!='Forced':
                revEventsDict[self.eventsDict[key]] = key
        matstr += '\t\t\t'
        matstr += '\t'.join([revEventsDict[k][0:4] for k in sorted(revEventsDict.keys())])
        matstr += '\t\tTimers\tOutputs\tSerialOut'
        matstr += '\n'
        for (index,onerow) in enumerate(self.stateMatrix):
            if len(onerow):
                matstr += '%s [%d] \t'%(self.statesIndexToName[index].ljust(16),index)
                matstr += '\t'.join(str(e) for e in onerow)
                matstr += '\t|\t%0.2f'%self.stateTimers[index]
                matstr += '\t%s'%self._output_as_str(self.stateOutputs[index])
                matstr += '\t%d'%self.serialOutputs[index]
            else:
                matstr += 'EMPTY ROW'
            matstr += '\n'
        return matstr
    def _output_as_str(self,outputVec):
        #outputStr = '-'*len(outputVec)
        outputStr = ''
        for indo,outputValue in enumerate(outputVec):
            if outputValue==1:
                outputStr += '1'
            elif outputValue==0:
                outputStr += '0'
            else:
                outputStr += '-'
        return outputStr

if __name__ == "__main__":
    CASE = 1
    if CASE==1:
        sm = StateMatrix(inputs={'C':0, 'L':1, 'R':2},
                         outputs={'centerWater':0, 'centerLED':1})
        #elif CASE==100:
        sm.add_state(name='wait_for_cpoke', statetimer=12,
                    transitions={'Cin':'play_target'},
                    outputsOff=['centerLED'])
        sm.add_state(name='play_target', statetimer=0.5,
                    transitions={'Cout':'wait_for_apoke','Tup':'wait_for_cpoke'},
                    outputsOn=['centerLED'])
        print sm
    elif CASE==2:
        sm = StateMatrix()
        sm.add_schedule_wave(name='mySW',preamble=1.2)
        sm.add_schedule_wave(name='my2SW',sustain=3.3)
        sm.add_state(name='wait_for_cpoke', statetimer=10,
                    transitions={'Cin':'play_target'})
        sm.add_state(name='play_target', statetimer=0.5,
                    transitions={'Cout':'wait_for_apoke','Tup':'wait_for_apoke'},
                    outputs={'Dout':5})
        print sm
    elif CASE==3:
        sm = StateMatrix()
        sm.add_extratimer('mytimer', duration=0.6)
        sm.add_extratimer('secondtimer', duration=0.3)
        sm.add_state(name='wait_for_cpoke', statetimer=12,
                    transitions={'Cin':'play_target', 'mytimer_Up':'third_state'},
                    outputsOff=['CenterLED'],  trigger=['mytimer'])
        print sm
    elif CASE==4:
        sm = StateMatrix()
        sm.add_state(name='wait_for_cpoke', statetimer=12,
                    transitions={'Cin':'play_target','Tup':'play_target'},
                    outputsOff=['CenterLED'])
        sm.add_state(name='play_target', statetimer=0.5,
                    transitions={'Cout':'wait_for_apoke','Tup':'wait_for_cpoke'},
                    outputsOn=['CenterLED'])
        sm.add_state(name='wait_for_apoke', statetimer=0.5,
                    transitions={'Tup':'wait_for_cpoke'},
                    outputsOff=['CenterLED'])
        print sm
        sm.get_matrix()
        sm.reset_transitions()
        sm.add_state(name='wait_for_cpoke', statetimer=12,
                    transitions={'Cin':'play_target','Tup':'play_target'},
                    outputsOff=['CenterLED'])
        print sm
        sm.get_matrix()
    if CASE==5:
        sm = StateMatrix()
        sm.add_state(name='wait_for_cpoke', statetimer=12,
                    transitions={'Cin':'play_target'},
                    outputsOff=['CenterLED'])
        sm.add_state(name='play_target', statetimer=0.5,
                    transitions={'Cout':'wait_for_apoke','Tup':'wait_for_cpoke'},
                    outputsOn=['CenterLED'], serialOut=1)
        print sm
       
    '''
    sm.add_state(name='wait_for_apoke', statetimer=0.5,
                transitions={'Lout':'wait_for_cpoke','Rout':'wait_for_cpoke'})

    sm.add_state(name='wait_for_cpoke', statetimer=10,
                    transitions={'Cin':'play_target'})
    print sm.stateMatrix
    sm.add_state(name='play_target', statetimer=1,
                    transitions={'Cout':'wait_for_apoke','Tup':'wait_for_apoke'},
                    outputs={'Dout':1})
    sm.add_state(name='wait_for_apoke', statetimer=1,
                    transitions={'Lin':'reward','Rin':'punish','Tup':'end_of_trial'})
    sm.add_state(name='reward', statetimer=1,
                    transitions={'Tup':'end_of_trial'},
                    outputs={'Dout':2})
    sm.add_state(name='punish', statetimer=1,
                    transitions={'Tup':'end_of_trial'},
                    outputs={'Dout':4})
    sm.add_state(name='end_of_trial')


    print(sm)
    '''

    ############# FIX THIS ##########

    # TO DO: make sure there are (empty) states until JumpState

'''

I have to add states to the list first, and then look for their
indices to fill up the matrix.


'''
