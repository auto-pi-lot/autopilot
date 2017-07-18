#!/usr/bin/env python

'''
State machine client emulator.

TO DO:
- Separate GUI from Model by using signals and slots.


'''


__version__ = '0.1'
__author__ = 'Santiago Jaramillo <sjara@uoregon.edu>'
__created__ = '2013-09-23'

import time
import numpy as np
import datetime
from PySide import QtCore 
from PySide import QtGui 

MAXNEVENTS = 512
MAXNSTATES = 256
MAXNEXTRATIMERS = 16
MAXNINPUTS = 8
MAXNOUTPUTS = 16
MAXNACTIONS = 2*MAXNINPUTS + 1 + MAXNEXTRATIMERS


class EmulatorGUI(QtGui.QWidget):
    def __init__(self, parent=None):
        super(EmulatorGUI, self).__init__(parent)
        '''
        self.window = QtGui.QMainWindow()
        #self.window = QtGui.QWidget()
        self.window.setAttribute(QtCore.Qt.WA_DeleteOnClose)

        self.window.setGeometry(100, 600, 500, 300)
        self.window.setWindowTitle('State Machine Emulator')
        self.window.show()
        self.window.activateWindow()
        '''
        self.setAttribute(QtCore.Qt.WA_DeleteOnClose)
        self.setGeometry(600, 600, 300, 200)
        self.setWindowTitle('State Machine Emulator')

        nButtons = 3
        self.button = nButtons*[0]
        self.light = nButtons*[0]
        self.water = nButtons*[0]
        buttonsStrings = ['C','L','R']
        buttonsPos = [1,0,2]
        layoutMain = QtGui.QGridLayout()
        for indbut in range(nButtons):
            self.button[indbut] = QtGui.QPushButton(buttonsStrings[indbut])
            self.button[indbut].setMinimumSize(100,100)
            layoutMain.addWidget(self.button[indbut],2,buttonsPos[indbut])
            self.light[indbut] = QtGui.QPushButton()
            self.light[indbut].setMinimumSize(100,25)
            self.light[indbut].setEnabled(False)
            self.changeLight(indbut,0)
            layoutMain.addWidget(self.light[indbut],1,buttonsPos[indbut])
            self.water[indbut] = QtGui.QPushButton()
            self.water[indbut].setMinimumSize(100,25)
            self.water[indbut].setEnabled(False)
            layoutMain.addWidget(self.water[indbut],0,buttonsPos[indbut])
        self.setLayout(layoutMain)

        self.inputStatus = np.zeros(nButtons,dtype=int)

        for indbut in range(nButtons):
            self.button[indbut].pressed.connect(lambda ind=indbut: self.inputOn(ind))
            self.button[indbut].released.connect(lambda ind=indbut: self.inputOff(ind))

        self.show()
        self.activateWindow()
    def inputOn(self,inputID):
        #print 'ON: {0}'.format(inputID)
        self.inputStatus[inputID] = 1
    def inputOff(self,inputID):
        #print 'OFF: {0}'.format(inputID)
        self.inputStatus[inputID] = False
    def changeLight(self,lightID,value):
        if value:
            stylestrLight = 'QWidget { background-color: yellow }'
        else:
            stylestrLight = ''
        self.light[lightID].setStyleSheet(stylestrLight)
    def changeWater(self,waterID,value):
        if value:
            stylestrWater = 'QWidget { background-color: blue }'
        else:
            stylestrWater = ''
        self.water[waterID].setStyleSheet(stylestrWater)
    def set_one_output(self,outputID,value):
        # XFIXME: this should be written more clearly (with less hardcoded assumptions)
        if outputID=='':
            pass
        elif outputID==1:
            self.changeLight(0,value)
        elif outputID==3:
            self.changeLight(1,value)
        elif outputID==5:
            self.changeLight(2,value)
        elif outputID==0:
            self.changeWater(0,value)
        elif outputID==2:
            self.changeWater(1,value)
        elif outputID==4:
            self.changeWater(2,value)
    def set_outputs(self,outputValues):
        for ind,val in enumerate(outputValues):
            if val in [0,1]:
                self.set_one_output(ind,val)

class StateMachineClient(QtCore.QObject):

    def __init__(self, connectnow=True, verbose=False, parent=None):
        super(StateMachineClient, self).__init__(parent)
        # -- Variables for SM client --
        # -- These values will be set by set_sizes() --
        self.nInputs = 0
        self.nOutputs = 0
        self.nExtraTimers = 0
        self.nActions = 1

        # DO I NEED THESE?
        ###self.lastTimeOfEvents = 0
        ###self.serverTime = 0
        ###self.state = 0
        ###self.lastEvents = []

        # -- Variables for SM server --
        self.timeOfCreation = time.time()
        ###self.timeOfLastEvents = self.timeOfCreation
        self.runningState = False
        self.eventsTime = np.zeros(MAXNEVENTS)
        self.eventsCode = np.zeros(MAXNEVENTS)
        self.nEvents = 0
        self.eventsToProcess = 0
        self.currentState = 0
        self.previousState = 0 # NEEDED?
        self.nextState = np.zeros(MAXNEVENTS)

        self.sizesSetFlag = False;
        # -- The following sizes will be overwritten by this class' methods --
        self.previousInputValues = np.zeros(MAXNINPUTS)
        self.inputValues = np.zeros(MAXNINPUTS)
        self.serialOutputs = np.zeros(MAXNSTATES)
        self.stateMatrix = np.zeros((MAXNSTATES,MAXNACTIONS))
        self.stateTimers = np.zeros(MAXNSTATES)
        self.stateOutputs = np.zeros((MAXNSTATES,MAXNOUTPUTS))
        self.extraTimers = np.zeros(MAXNEXTRATIMERS)
        self.triggerStateEachExtraTimer = np.zeros(MAXNEXTRATIMERS)
        
        self.stateTimerValue = 0;
        self.extraTimersValues = np.zeros(MAXNEXTRATIMERS)
        self.currentState = 0;

        # -- Variables for Virual Hardware --
        self.outputs = np.zeros(MAXNOUTPUTS)
        self.inputs = np.zeros(MAXNINPUTS)
        self.serialout = 0

        # -- Create timer --
        self.interval = 0.01 # Polling interval (sec)
        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self.execute_cycle)

        self.emuGUI = EmulatorGUI()
        
    def send_reset(self):
        pass
    def connect(self):
        print 'EMULATOR: Connect.'
        pass
    def test_connection(self):
        pass
    def get_version(self):
        pass
    def set_sizes(self,nInputs,nOutputs,nExtraTimers):
        self.nInputs = nInputs
        self.nOutputs = nOutputs
        self.nExtraTimers = nExtraTimers
        self.nActions = 2*nInputs + 1 + nExtraTimers
        self.sizesSetFlag = True
    def get_time(self):
        serverTime = time.time()-self.timeOfCreation
        #datetime.datetime.now().second  ######## DEBUG ##########
        return round(serverTime,3)
    def get_inputs(self):
        pass
    def force_output(self,output,value):
        self.outputs[output] = value
        # XFIXME: do the following with signals and slots
        if value in [0,1]:
            self.emuGUI.set_one_output(output,value)
        print 'EMULATOR: Force output {0} to {1}'.format(output,value)
        pass
    def set_state_matrix(self,stateMatrix):
        '''
        stateMatrix: [nStates][nActions]  (where nActions is 2*nInputs+1+nExtraTimers)
        See smclient.py
        '''
        # WARNING: We are not checking the validity of this matrix
        self.stateMatrix = np.array(stateMatrix)
        print 'EMULATOR: Set state matrix.'
    def send_matrix(self,someMatrix):
        pass
    def report_state_matrix(self):
        pass
    def run(self):
        self.runningState = True
        self.timer.start(1e3*self.interval) # timer takes interval in ms
        print 'EMULATOR: Run.'
    def stop(self):
        self.timer.stop()
        self.runningState = False
        print 'EMULATOR: Stop.'
    def set_state_timers(self,timerValues):
        self.stateTimers = np.array(timerValues)
        pass
    def report_state_timers(self):
        pass
    def set_extra_timers(self,extraTimersValues):
        self.extraTimers = np.array(extraTimersValues)
        pass
    def set_extra_triggers(self,stateTriggerEachExtraTimer):
        self.triggerStateEachExtraTimer = np.array(stateTriggerEachExtraTimer)
        pass
    def report_extra_timers(self):
        pass
    def set_state_outputs(self,stateOutputs):
        self.stateOutputs = np.array(stateOutputs)
        print 'EMULATOR: Set state outputs.'
        #print self.stateOutputs
        pass
    def set_serial_outputs(self,serialOutputs):
        self.serialOutputs = np.array(serialOutputs)
        pass
    def report_serial_outputs(self):
        pass
    def get_events(self):
        lastEventsTime = self.eventsTime[:self.nEvents]
        lastEventsCode = self.eventsCode[:self.nEvents]
        lastNextState = self.nextState[:self.nEvents]
        lastEvents = np.column_stack((lastEventsTime,lastEventsCode,lastNextState))
        self.nEvents = 0
        return lastEvents.tolist()
    def get_current_state(self):
        return self.currentState
        pass
    def force_state(self,stateID):
        ## XFIXME: In this function, the way nextState is updated is weird (in arduino)
        #  maybe it should be closer to add_event
        self.eventsTime[self.nEvents] = self.get_time()
        self.currentState = stateID
        self.eventsCode[self.nEvents] = -1
        self.nextState[self.nEvents] = self.currentState
        self.nEvents += 1
        self.enter_state(self.currentState)
        print 'EMULATOR: Force state {0}.'.format(stateID)
    def write(self,value):
        pass
    def readlines(self):
        pass
    def read(self):
        pass
    def close(self):
        print 'EMULATOR: Close.'
        self.emuGUI.close()

    def add_event(self,thisEventCode):
        self.eventsTime[self.nEvents] = self.get_time()
        self.eventsCode[self.nEvents] = thisEventCode
        self.nEvents += 1
        self.eventsToProcess += 1
        print 'Added event {0}'.format(thisEventCode)

    def execute_cycle(self):
        '''
        Add events to the queue if any inputs changed or timers finished.
        This implementation is not intended to be the most efficient,
        instead we're trying to be as close to the Arduino code as possible.
        '''
        # -- Check if any input has changed, if so, add event --
        for indi in range(self.nInputs):
            previousValue = self.inputValues[indi]
            self.inputValues[indi] = self.emuGUI.inputStatus[indi]
            if self.inputValues[indi]!=previousValue:
                self.add_event(2*indi + previousValue)
        currentTime = self.get_time()
        if (currentTime-self.stateTimerValue) >= self.stateTimers[self.currentState]:
            self.add_event(2*self.nInputs)
            self.stateTimerValue = currentTime # Restart timer
            pass

        # XTODO: extratimers
        ###
            
        # -- Update state machine given last events --
        # XFIXME: this is ugly (in the arduino code).
        #        update_state_machine sneakily changes a value (currentState)
        previousState = self.currentState
        self.update_state_machine()
        # -- The following code created problems (see docs), IT IS BEING TESTED --
        if self.currentState != previousState:
            self.enter_state(self.currentState)
            pass

    def enter_state(self,currentState):
        self.stateTimerValue = self.get_time()
        # XTODO: Finish extra timers
        #for indt in range(self.nExtraTimers)
        self.outputs = self.stateOutputs[currentState,:]
        self.emuGUI.set_outputs(self.outputs)
        self.serialout = self.serialOutputs[currentState]
        self.emulate_serial_output()

    def emulate_serial_output(self):
        f=open('/tmp/serialoutput.txt','w')
        f.write(str(self.serialout))
        f.close()

    def update_state_machine(self):
        while(self.eventsToProcess>0):
            currentEventIndex = self.nEvents-self.eventsToProcess
            currentEvent = self.eventsCode[currentEventIndex];
            self.nextState[currentEventIndex] = self.stateMatrix[self.currentState,currentEvent]
            self.currentState = self.nextState[currentEventIndex]
            self.eventsToProcess -= 1


