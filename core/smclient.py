#!/usr/bin/env python

'''
Client for the state machine server running on an Arduino Due.

TO DO:
- Change welcome message to opcode,size,msg
- The welcome message includes a cut message a the beginning
  but when arduino is reset manually it sends only the right thing.
- Send time (for a schedule wave)
- Send actions

'''

__version__ = '0.2'
__author__ = 'Santiago Jaramillo <sjara@uoregon.edu>'


import serial
import glob
import os
import sys
import time
import struct

try:
    from taskontrol.settings import rigsettings
    SERIAL_PORT_PATH = rigsettings.STATE_MACHINE_PORT
except ImportError:
    SERIAL_PORT_PATH = '/dev/ttyACM0'

SERIAL_BAUD = 115200  # Should be the same in statemachine.ino
SERIAL_TIMEOUT = 0.1
NINPUTS = 8
NOUTPUTS = 16

# -- COMMANDS --
opcode = {
    'OK'                 : 0xaa,
    'RESET'              : 0x01,     #OBSOLETE
    'CONNECT'            : 0x02,
    'TEST_CONNECTION'    : 0x03,
    'SET_SIZES'          : 0x04,
    'GET_SERVER_VERSION' : 0x05,
    'GET_TIME'           : 0x06,
    'GET_INPUTS'         : 0x0e,
    'FORCE_OUTPUT'       : 0x0f,
    'SET_STATE_MATRIX'   : 0x10,
    'RUN'                : 0x11,
    'STOP'               : 0x12,
    'GET_EVENTS'         : 0x13,
    'REPORT_STATE_MATRIX': 0x14,
    'GET_CURRENT_STATE'  : 0x15,
    'FORCE_STATE'        : 0x16,
    'SET_STATE_TIMERS'   : 0x17,
    'REPORT_STATE_TIMERS': 0x18,
    'SET_STATE_OUTPUTS'  : 0x19,
    'SET_EXTRA_TIMERS'   : 0x1a,
    'SET_EXTRA_TRIGGERS' : 0x1b,
    'REPORT_EXTRA_TIMERS': 0x1c,
    'SET_SERIAL_OUTPUTS' : 0x1d,
    'REPORT_SERIAL_OUTPUTS': 0x1e,
    'ERROR'              : 0xff,
}
for k,v in opcode.iteritems():
    opcode[k]=chr(v)

class StateMachineClient(object):
    def __init__(self,connectnow=True):
        '''
        State machine client for the Arduino Due.
        '''
        '''
        # -- Check if there are multiple serial USB ports --
        allSerialPorts = glob.glob(SERIAL_PORT_PATH)
        if len(allSerialPorts)>1:
            raise
        self.port = allSerialPorts[0]
        '''
        # -- These values will be set by set_sizes() --
        self.nInputs = 0
        self.nOutputs = 0
        self.nExtraTimers = 0
        self.nActions = 1

        self.port = SERIAL_PORT_PATH
        self.ser = None  # To be created on self.connect()
        if connectnow:
            self.connect()
    def send_reset(self):
        '''Old function necessary for Maple. Obsolete for Arduino'''
        pass
    def connect(self):
        ###self.ser.flushInput()  # XXFIXME: Why would I need this?
        portReady = False
        fsmReady = False
        while not portReady:  #os.path.exists(self.port):
            try:
                self.ser = serial.Serial(self.port, SERIAL_BAUD,
                                         timeout=SERIAL_TIMEOUT)
                portReady = True
            except serial.SerialException:
                print 'Waiting for Arduino to be ready...'
                time.sleep(1)
        self.ser.setTimeout(1)
        #self.ser.flushOutput()  # XXFIXME: Discard anything in output buffer?
        #self.ser.flushInput()   # XXFIXME: Discard anything in input buffer?
        time.sleep(0.2)  # XXFIXME: why does it need extra time? 0.1 does not work!
        self.ser.write(opcode['CONNECT'])
        while not fsmReady:
            print 'Establishing connection...'
            sys.stdout.flush()
            fsmReady = (self.ser.read(1)==opcode['OK'])
        self.ser.setTimeout(SERIAL_TIMEOUT)
        print 'Connected!'
        #self.ser.flushOutput()
    def test_connection(self):
        self.ser.write(opcode['TEST_CONNECTION'])
        connectionStatus = self.ser.read()
        if connectionStatus==opcode['OK']:
            return 'OK'
        else:
            raise IOError('Connection to state machine was lost.')
            #print 'Connection lost'
    def get_version(self):
        '''Request version number from server.
        Returns: string
        '''
        self.ser.write(opcode['GET_SERVER_VERSION'])
        versionString = self.ser.readline()
        return versionString.strip()
    def set_sizes(self,nInputs,nOutputs,nExtraTimers):
        self.nInputs = nInputs
        self.nOutputs = nOutputs
        self.nExtraTimers = nExtraTimers
        # -- nActions: two per input, one state timer, and extra timers --
        self.nActions = 2*self.nInputs + 1 + self.nExtraTimers
        self.ser.write(opcode['SET_SIZES'])
        self.ser.write(chr(nInputs))
        self.ser.write(chr(nOutputs))
        self.ser.write(chr(nExtraTimers))
    def get_time(self):
        '''Request server time.
        Returns time in seconds.
        '''
        self.ser.write(opcode['GET_TIME'])
        serverTime = self.ser.readline()
        return 1e-3*float(serverTime.strip())
    def get_inputs(self):
        '''Request values of inputs.
        Returns: string
        '''
        self.ser.flushInput()  ## WHY
        self.ser.write(opcode['GET_INPUTS'])
        #inputValues = self.ser.readlines()
        # XXFIXME: verify that the number of inputs from server matches client
        nInputs = ord(self.ser.read(1))
        inputValuesChr = self.ser.read(nInputs)
        inputValues = [ord(x) for x in inputValuesChr]
        return inputValues
    def force_output(self,outputIndex,outputValue):
        self.ser.write(opcode['FORCE_OUTPUT']+chr(outputIndex)+chr(outputValue))
    def set_state_matrix(self,stateMatrix):
        '''
        stateMatrix: [nStates][nActions]  (where nActions is 2*nInputs+1+nExtraTimers)
        '''
        for onerow in stateMatrix:
            if len(onerow)!=self.nActions:
                raise ValueError('The states transition matrix does not have the '+\
                                 'correct number of columns.\n'+\
                                 'It should be {0} not {1}'.format(self.nActions,
                                                                   len(onerow)))
        self.ser.write(opcode['SET_STATE_MATRIX'])
        self.send_matrix(stateMatrix)
    def send_matrix(self,someMatrix):
        nRows = len(someMatrix)
        nCols = len(someMatrix[0])
        self.ser.write(chr(nRows))
        self.ser.write(chr(nCols))
        #print repr(chr(nRows)) ### DEBUG
        #print repr(chr(nCols)) ### DEBUG
        for oneRow in someMatrix:
            for oneItem in oneRow:
                #print repr(chr(oneItem)) ### DEBUG
                self.ser.write(chr(oneItem))
    def report_state_matrix(self):
        self.ser.write(opcode['REPORT_STATE_MATRIX'])
        sm = self.ser.readlines()
        for line in sm:
            print line,
    def run(self):
        self.ser.write(opcode['RUN'])
    def stop(self):
        self.ser.write(opcode['STOP'])
    def set_state_timers(self,timerValues):
        '''
        Values should be in seconds.
        '''
        self.ser.write(opcode['SET_STATE_TIMERS'])
        # XXFIXME: test if the value is too large
        for oneval in timerValues:
            if oneval<0:
                raise ValueError('Value of timers should be positive.')
        timerValuesInMillisec = [int(1e3*x) for x in timerValues]
        # Send unsigned long ints (4bytes) little endian
        for oneTimerValue in timerValuesInMillisec:
            packedValue = struct.pack('<L',oneTimerValue)
            self.ser.write(packedValue)
    def report_state_timers(self):
        self.ser.write(opcode['REPORT_STATE_TIMERS'])
        return self.ser.readlines()
    def set_extra_timers(self,extraTimersValues):
        '''
        Send the values for each extra timer. Values should be in seconds.
        '''
        self.ser.write(opcode['SET_EXTRA_TIMERS'])
        # XXFIXME: test if the value is too large
        for oneval in extraTimersValues:
            if oneval<0:
                raise ValueError('Value of timers should be positive.')
        timerValuesInMillisec = [int(1e3*x) for x in extraTimersValues]
        # Send unsigned long ints (4bytes) little endian
        for oneTimerValue in timerValuesInMillisec:
            packedValue = struct.pack('<L',oneTimerValue)
            self.ser.write(packedValue)
    def set_extra_triggers(self,stateTriggerEachExtraTimer):
        '''
        Send the state that will trigger each extra timer.
        '''
        self.ser.write(opcode['SET_EXTRA_TRIGGERS'])
        for onestate in stateTriggerEachExtraTimer:
            self.ser.write(chr(onestate))
    def report_extra_timers(self):
        self.ser.write(opcode['REPORT_EXTRA_TIMERS'])
        return self.ser.readlines()
    def set_state_outputs(self,stateOutputs):
        '''stateOutputs is a python array with integer values.
        The size should be [nStates][nOutputs] 
        Values should be either 0 (for low), 1 (for high), other (for no change)
        '''
        self.ser.write(opcode['SET_STATE_OUTPUTS'])
        self.send_matrix(stateOutputs)
    def set_serial_outputs(self,serialOutputs):
        '''serialOutputs is a python array of length [nStates]
        with integer values in the range 0-255.
        A value of 0 means no serial output for that state.
        '''
        self.ser.write(opcode['SET_SERIAL_OUTPUTS'])
        for oneOutput in serialOutputs:
            self.ser.write(chr(oneOutput))
    def report_serial_outputs(self):
        self.ser.write(opcode['REPORT_SERIAL_OUTPUTS'])
        return self.ser.readline()
    def get_events_raw_strings(self):
        '''Request list of events
        Returns: strings (NEEDS MORE DETAIL)
        '''
        self.ser.write(opcode['GET_EVENTS'])
        nEvents = ord(self.ser.read())
        eventsList = []
        for inde in range(nEvents):
            eventsList.append(self.ser.readline())
        return eventsList
    def get_events(self):
        # XXFIXME: translation of the events strings to a matrix may be slow
        #        it needs to be tested carefully.
        eventsList = self.get_events_raw_strings()
        eventsMat = []
        for oneEvent in eventsList:
            eventItems = [int(x) for x in oneEvent.split()]
            eventItems[0] = 1e-3*eventItems[0]
            eventsMat.append(eventItems)
        return eventsMat
    def get_current_state(self):
        self.ser.write(opcode['GET_CURRENT_STATE'])
        currentState = self.ser.read()
        return ord(currentState)
    def force_state(self,stateID):
        self.ser.write(opcode['FORCE_STATE'])
        self.ser.write(chr(stateID))        

    def write(self,value):
        self.ser.write(value)
    def OLD_set_state_outputs(self,stateOutputs):
        '''Each element of stateOutputs must be one byte.
        A future version may include a 'mask' so that the output
        is not changed when entering that state.'''
        self.ser.write(opcode['SET_STATE_OUTPUTS'])
        for outputsOneState in stateOutputs:
            self.ser.write(outputsOneState)
    def readlines(self):
        return self.ser.readlines()
    def read(self):
        oneline = self.ser.readlines()
        #print ''.join(oneline)
        print oneline
    def error_check(self):
        # XXFIXME: is this implemented correctly? It has not been tested
        status = self.ser.read()
        if status==opcode['ERROR']:
            therest = self.ser.readline()
            raise Exception('The state machine server sent an error opcode and %s'%therest)
        elif status!='':
            therest = self.ser.readline()
            raise Exception('The state machine server sent: %s%s'%(status,therest))
    def close(self):
        self.stop()
        #for ... force_output() # Force every output to zero
        self.ser.close()
'''
    def send_timers(self,oneTime):
        self.ser.write(chr(SEND_TIMERS))
        self.ser.write('%d\n'%oneTime) # in milliseconds
        
'''


if __name__ == "__main__":

    CASE = 4

    if CASE==0:
        c = StateMachineClient()
        #c.set_output(1,1)
        #import time; time.sleep(0.5)
        c.set_sizes(3,3,0) # inputs,outputs,extratimers
        stateMatrix = [[1,0, 0,0, 0,0, 1] , [0,1, 1,1, 1,1, 0]]
        c.set_state_matrix(stateMatrix)
        c.set_state_timers([1, 0.5])
        #stateOutputs = ['\x00','\xff']
        stateOutputs = [[1,8,8],[0,8,8]]
        c.set_state_outputs(stateOutputs)
        c.run()
        sys.exit()
    elif CASE==1:
        c = StateMachineClient()
        c.set_sizes(3,3,1) # inputs,outputs,extratimers
        stateMatrix = [[1,0, 0,0, 0,0, 1, 0] , [0,1, 1,1, 1,1, 0, 1]]
        c.set_state_matrix(stateMatrix)
        c.set_state_timers([1, 0.5])
        stateOutputs = [[1,7,7],[0,7,7]]
        c.set_state_outputs(stateOutputs)
        #c.run()
        c.set_extra_timers([1.2])
        c.set_extra_triggers([1])
        sys.exit()
    elif CASE==2:
        # -- Test with a large matrix --
        m=reshape(arange(400)%10,(20,20))
        c.set_state_matrix(m)
        c.report_state_matrix()
    elif CASE==3:
        stateMatrix=[]
        # INPUTS          i1 i2
        #stateMatrix.append([ 1 , 2 ])
        #stateMatrix.append([ 2 , 0 ])
        #stateMatrix.append([ 0 , 1 ])

        # XXFIXME: there is a limit on the size of the matrix
        #        one due to the number of rows or cols (has to be <128)
        #        another probably due to the serial buffer size
        # On what platform was this problem seen? maple or arduino due?

        #stateMatrix.append(range(0,4))
        #stateMatrix.append(range(100,104))
        stateMatrix = [[1,0, 0,0, 0,0, 1] , [0,1, 1,1, 1,1, 0]]
        stateTimers = [200000,1000000] # in microseconds
        #stateMatrix = [[1,0, 1] , [0,1, 0]]
        #stateTimers = [0,0] # in microseconds
        stateOutputs = ['\x00','\xff']

        import time
        time.sleep(0.5)
        c.set_state_matrix(stateMatrix)
        #time.sleep(0.1)
        #print c.readlines()
        c.set_state_timers(stateTimers)
        #time.sleep(0.1)
        #print c.readlines()
        c.set_state_outputs(stateOutputs)
        #time.sleep(0.1)
        unwantedData = c.readlines()
        if unwantedData:
            print unwantedData
        c.run()
        '''
        '''
        #c.send_timers(200)
    elif CASE==4:
        c = StateMachineClient()
        c.set_sizes(3,3,0) # inputs,outputs,extratimers
        stateMatrix = [[1,0, 0,0, 0,0, 1] , [0,1, 1,1, 1,1, 0]]
        c.set_state_matrix(stateMatrix)
        c.set_state_timers([100, 1])
        stateOutputs = [[1,7,7],[0,7,7]]
        c.set_state_outputs(stateOutputs)
        serialOutputs = [0,67]
        c.set_serial_outputs(serialOutputs)
        #c.run()
        sys.exit()


