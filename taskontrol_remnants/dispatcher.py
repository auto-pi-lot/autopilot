#!/usr/bin/env python

'''
Dispatcher for behavioral paradigm.

It is meant to be the interface between a trial-structured paradigm
and the state machine. It will for example halt the state machine
until the next trial has been prepared and ready to start.

NOTES:
- Should I separate GUI from trial structure control?
- Should I implement it with QThread instead?
- If running on Windows I may need to change name to *.pyw
- Does the time keep going even if close the window?
- Crashing should be graceful (for example close connection to statemachine)
- Style sheets (used for changing color) may not be supported on MacOSX
- There is a delay when pressing Start button before it changes color.
  This happens even if I move the code to the beginning of the method,
  but only when I'm using the StateMachine (not in dummy mode).

TODO:
* When the form is destroyed, dispatcher.closeEvent is not called!
'''


__version__ = '0.2'
__author__ = 'Santiago Jaramillo <sjara@uoregon.edu>'


import sys
from PySide import QtCore 
from PySide import QtGui 
import numpy as np
from taskontrol.settings import rigsettings
#from taskontrol.core import messenger
#from taskontrol.core import smclient

#reload(smclient)

DEFAULT_PREPARE_NEXT = 0 # State to prepare next trial
N_INPUTS = len(rigsettings.INPUTS)
N_OUTPUTS = len(rigsettings.OUTPUTS)

class Dispatcher(QtCore.QObject):
    '''
    Dispatcher is the trial controller. It is an interface between a
    trial-structured paradigm and the state machine.

    It emits the following signals:
    - 'timerTic'        : at every tic of the dispatcher timer.
                          It sends: serverTime,currentState,eventCount,currentTrial
    - 'prepareNextTrial': whenever one of the prepare-next-trial-states is reached.
                          It sends: 'nextTrial'

    REMOVED:
    - 'startNewTrial'   : whenever READY TO START TRIAL is sent to state machine.
                          It sends: 'currentTrial'
    '''
    # -- Create signals (they need to be before constructor) --
    timerTic = QtCore.Signal(float,int,int,int)
    prepareNextTrial = QtCore.Signal(int)
    startNewTrial = QtCore.Signal(int) ### XXFIXME: is this really necessary?
    logMessage = QtCore.Signal(str)

    def __init__(self, parent=None,serverType='dummy', connectnow=True, interval=0.3,
                 nInputs=N_INPUTS,nOutputs=N_OUTPUTS):
        super(Dispatcher, self).__init__(parent)

        if serverType=='arduino_due':
            from taskontrol.core import smclient as smclient
        elif serverType=='dummy':
            from taskontrol.plugins import smdummy as smclient
        elif serverType=='emulator':
            from taskontrol.plugins import smemulator as smclient
        else:
            pass
        
        # -- Set trial structure variables --
        self.prepareNextTrialStates = [0]    # Default state to prepare next trial
        self.preparingNextTrial = False      # True while preparing next trial

        # -- Create a state machine client --
        #self.host = host
        #self.port = port
        self.nInputs = nInputs
        self.nOutputs = nOutputs
        self.isConnected = False
        self.statemachine = smclient.StateMachineClient(connectnow=False)

        if connectnow:
            self.connect_to_sm()  # Connect to state machine

        # -- Create state machine variables --
        self.serverTime = 0.0   # Time on the state machine
        self.currentState = 0   # State of the state machine
        self.eventCount = 0     # Number of events so far
        self.currentTrial = -1   # Current trial (first trial will be 0)
        #self.lastEvents = np.array([])   # Matrix with info about last events
        #self.eventsMat = np.empty((0,3)) # Matrix with info about all events
        self.lastEvents = []   # Matrix with info about last events
        self.eventsMat = []    # Matrix with info about all events
        #self._stateMatrixStatus = False # To indicate if a matrix has been set
        self.indexLastEventEachTrial = [] # index of last event for each trial

        # -- Create timer --
        self.interval = interval # Polling interval (sec)
        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self.timeout)

        # -- Start with just a zero-state --
        self.reset_state_matrix()

    def connect_to_sm(self):
        '''Connect to state machine server and initialize it.'''
        self.statemachine.connect()
        ###self.statemachine.initialize()
        self.statemachine.set_sizes(self.nInputs,self.nOutputs,0)
        self.isConnected = True

    def reset_state_matrix(self):
        nActions = 2*self.nInputs+1
        blankMatrix = [nActions*[0]]
        blankOutputs = [self.nOutputs*[0]]
        blankSerial = None
        blankTimers = [60] # in sec
        self._set_state_matrix(blankMatrix,blankOutputs,blankSerial,blankTimers)

    def set_state_matrix(self,stateMatrix):
        '''
        Send state transition matrix to server.
        Args:
            stateMatrix (statematrix.StateMatrix): object that contains all information
                        about the state matrix, outputs and timers.
        '''
        self._set_prepare_next_trial_states(stateMatrix.get_ready_states(),
                                            stateMatrix.get_states_dict())
        self._set_state_matrix(stateMatrix.get_matrix(),
                               stateMatrix.get_outputs(),
                               stateMatrix.get_serial_outputs(),
                               stateMatrix.get_state_timers())

    def _set_state_matrix(self,stateMatrix,stateOutputs,serialOutputs,stateTimers,extraTimers=None):
        '''
        Send state transition matrix, outputs and timers to server, given python lists.

        Data must be python lists (2D), not numpy arrays.
        stateMatrix: [nStates][nActions]  (where nActions is 2*nInputs+1+nExtraTimers)
        stateOutputs: [nStates][nOutputs] specifying it turn on, off, or no change.
                      0 (for low), 1 (for high), other (for no change)
        serialOutputs: [nStates] (where each value is one byte corresponding to 8 outputs)
        stateTimers: [nStates] (in sec)
        '''
        # -- Set prepare next trial states --
        #set_prepare_next_trial_states(self.sm.get_ready_states(),
        #                             self.sm.get_states_dict())
        if self.isConnected:
            #if not isinstance(statesmatrix,np.ndarray):
            #    statesmatrix = np.array(statesmatrix)
            if extraTimers:
                #self.statemachine.setScheduledWavesDIO(schedwavesmatrix)        
                raise 'Sending extra-timers is not implemented yet.'
            self.statemachine.set_state_matrix(stateMatrix)
            self.statemachine.set_state_outputs(stateOutputs)
            if serialOutputs:
                self.statemachine.set_serial_outputs(serialOutputs)
            self.statemachine.set_state_timers(stateTimers)
            #self._stateMatrixStatus = True
        else:
            print 'Call to setStateMatrix, but the client is not connected.\n'

    def _set_prepare_next_trial_states(self,prepareNextTrialStatesAsStrings,statesDict):
        '''Defines the list of states from which the state machine returns control
        to the client to prepare the next trial.'''
        if not isinstance(prepareNextTrialStatesAsStrings,list):
            raise TypeError('prepareNextTrialStatesAsStrings must be a list of strings')
        self.prepareNextTrialStates = []
        for oneState in prepareNextTrialStatesAsStrings:
            self.prepareNextTrialStates.append(statesDict[oneState])

    def ready_to_start_trial(self):
        '''
        Tell the state machine that it can jump to state 1 and start new trial.
        '''
        self.currentTrial += 1
        self.statemachine.force_state(1)
        self.preparingNextTrial = False
        ### self.startNewTrial.emit(self.currentTrial) # XXFIXME: is this really necessary?

    def timeout(self):
        ###print '************************ TIMEOUT *********************'
        self.query_state_machine()
        self.timerTic.emit(self.serverTime,self.currentState,self.eventCount,self.currentTrial)
        ###print '{0}  {1}'.format(self.currentState,self.serverTime) ### DEBUG
        ###print self.prepareNextTrialStates
        # -- Check if one of the PrepareNextTrialStates has been reached --
        #print len(self.lastEvents), self.currentState  # DEBUG
        #print self.prepareNextTrialStates # DEBUG
        # Is current state a prepare-next-trial state?
        if self.currentState in self.prepareNextTrialStates:
            self.preparingNextTrial = True
            self.update_trial_borders()
            self.prepareNextTrial.emit(self.currentTrial+1)
        # XXFIXME: Should I stop the clock/timeouts here? until everything is processed?
        # XXFIXME: fix what to do for other preparation states
        '''
        if self.currentState and not self.preparingNextTrial) or \
                (len(self.lastEvents)>0 and not self.preparingNextTrial:
            laststates = self.lastEvents[:,2] # XFIXME: is that 3 or 2?
            for state in self.prepareNextTrialStates:
                if state in laststates:
                    self.preparingNextTrial = True
                    #self.emit(QtCore.SIGNAL('PrepareNextTrial'), self.currentTrial+1)
                    self.prepareNextTrial.emit(self.currentTrial+1)
                    break
       '''

    #@QtCore.Slot()
    def resume(self):
        # --- Start timer ---
        self.timer.start(1e3*self.interval) # timer takes interval in ms
        # -- Start state machine --
        if self.isConnected:
            if 1: #self._stateMatrixStatus:
                # Prepare next trial when start is pressed
                #self.prepareNextTrial.emit(self.currentTrial+1)
                self.statemachine.run()
                self.logMessage.emit('Started')
                # Prepare next trial (and jump to state 1) when pressing START
                # this is also emitted when timeout() encounters end of trial
                #self.prepareNextTrial.emit(self.currentTrial+1)
                self.timeout()
            else:
                raise Exception('A state matrix has not been set')
        else:
            print 'The dispatcher is not connected to the state machine server.'

    #@QtCore.Slot()
    def pause(self):
        # --- Stop timer ---
        self.timer.stop()
        # -- Start state machine --
        if self.isConnected:
            self.statemachine.stop()
            self.statemachine.force_state(0)
            for indout in range(self.nOutputs):
                self.statemachine.force_output(indout,0)
            self.logMessage.emit('Stopped')
        else:
            print 'The dispatcher is not connected to the state machine server.'

    def query_state_machine(self):
        '''Request events information to the state machine'''
        if self.isConnected:
            #resultsDict = self.statemachine.getTimeEventsAndState(self.eventCount+1)
            self.serverTime = self.statemachine.get_time()
            self.lastEvents = self.statemachine.get_events()
            #self.eventsMat = np.vstack((self.eventsMat,self.lastEvents))
            if len(self.lastEvents)>0:
                self.eventsMat.extend(self.lastEvents)
                self.currentState = self.eventsMat[-1][2]
                self.eventCount = len(self.eventsMat)
                # XXFIXME: this may fail if eventsMat is empty on the first call
                ### print self.eventsMat ### DEBUG

    def update_trial_borders(self):
        '''Find last index of last trial.
        It looks for state zero, which corresponds to the last state no each trial.
        The first event of all is also state zero, but this one is ignored.'''
        # XXFIXME: slow way to find end of trial
        if self.currentTrial>=0: # & self.eventCount>0:
            for inde in xrange(self.eventCount-1,-1,-1): # This will count from n to 0
                #if self.eventsMat[inde][2] in self.prepareNextTrialStates:
                if self.eventsMat[inde][2]==DEFAULT_PREPARE_NEXT:
                    self.indexLastEventEachTrial.append(inde)
                    break
        # WARNING: make sure this method is not called before the events
        #          at the end of the trials are sent to the client/dispatcher
        # XXFIXME: this function has not been tested with more than one state
        #        in prepareNextTrialStates.

    def events_one_trial(self,trialID):
        '''Return events for one trial as a numpy array'''
        #if trialID<0: eventsThisTrial = np.empty((0,3)) # NOTE: hardcoded size
        indLast = self.indexLastEventEachTrial[-1]
        if trialID==0:
            indPrev = 0
        else:
            indPrev = self.indexLastEventEachTrial[-2]
        # -- Include the state 0 at the beginning of the trial --
        #eventsThisTrial = self.eventsMat[indPrev:indLast+1] # eventsMat is a list
        # -- Do not include the state 0 at the beginning of the trial --
        eventsThisTrial = self.eventsMat[indPrev+1:indLast+1] # eventsMat is a list
        return np.array(eventsThisTrial)
        ####### XXFIXME: this seems inefficient because eventsMat is an array and we
        #######        need only a set of trials. Do we need to convert the whole thing?


    def append_to_file(self,h5file,currentTrial=None):
        '''Add events information to an open HDF5 file.
        At this point, it ignores the value of 'currentTrial'.
        '''
        if not (self.indexLastEventEachTrial): # not len(self.eventsMat):
            raise UserWarning('WARNING: No trials have been completed. No events were saved.')
        eventsGroup = h5file.create_group('/events') # Events that ocurred during the session
        eventsMatrixAsArray = np.array(self.eventsMat)
        eventsGroup.create_dataset('eventTime', dtype=float, data=eventsMatrixAsArray[:,0])
        eventsGroup.create_dataset('eventCode', dtype=int, data=eventsMatrixAsArray[:,1])
        eventsGroup.create_dataset('nextState', dtype=int, data=eventsMatrixAsArray[:,2])
        eventsGroup.create_dataset('indexLastEventEachTrial', dtype=int,
                                   data=np.array(self.indexLastEventEachTrial))

        ###### XXFIXME: what happens (on trial 1) when indexLastEventEachTrial is empty? #####


        #rawEventsColumnsLabels = ['eventTime','eventCode','nextState']
        #eventsGroup.create_dataset('rawEvents', dtype=float, data=dispatcherModel.eventsMatrix)
        #dtstr = h5py.special_dtype(vlen=str)
        #eventsGroup.create_dataset('rawEventsColumnsLabels', dtype=dtstr,
        #                           data=rawEventsColumnsLabels)
        #return True
        
        
    def die(self):
        '''Make sure timer stops when user closes the dispatcher.'''
        self.pause()
        if self.isConnected:
            # XXFIXME: set all outputs to zero
            #self.statemachine.bypassDout(0)
            self.statemachine.force_state(0)
            self.statemachine.close()



BUTTON_COLORS = {'start':'limegreen','stop':'red'}

class DispatcherGUI(QtGui.QGroupBox):
    resumeSM = QtCore.Signal()
    pauseSM = QtCore.Signal()
    def __init__(self, parent=None, minwidth=220, dummy=False, model=None):
        super(DispatcherGUI, self).__init__(parent)

        self.runningState = False

        # -- Set string formats --
        self._timeFormat = 'Time: {0:0.1f} s'
        self._stateFormat = 'State: {0}'
        self._eventCountFormat = 'Events: {0}'
        self._currentTrialFormat = 'Trial: {0}'

        # -- Create graphical objects --
        self.stateLabel = QtGui.QLabel()
        self.timeLabel = QtGui.QLabel()
        self.eventCountLabel = QtGui.QLabel()
        self.currentTrialLabel = QtGui.QLabel()
        self.buttonStartStop = QtGui.QPushButton('')
        self.buttonStartStop.setCheckable(False)
        self.buttonStartStop.setMinimumHeight(100)
        #self.buttonStartStop.setMinimumWidth(160)
        buttonFont = QtGui.QFont(self.buttonStartStop.font())
        buttonFont.setPointSize(buttonFont.pointSize()+10)
        self.buttonStartStop.setFont(buttonFont)
        self.setMinimumWidth(minwidth)

        self.update(0.0, 0, 0, '')

        '''
        # -- To have a reference for StyleSheets ? --
        self.stateLabel.setObjectName('DispatcherLabel')
        self.timeLabel.setObjectName('DispatcherLabel')
        self.eventCountLabel.setObjectName('DispatcherLabel')
        self.currentTrialLabel.setObjectName('DispatcherLabel')
        '''

        # -- Create layouts --
        layout = QtGui.QGridLayout()
        layout.addWidget(self.stateLabel,0,0)
        layout.addWidget(self.eventCountLabel,0,1)
        layout.addWidget(self.timeLabel,1,0)
        layout.addWidget(self.currentTrialLabel,1,1)
        layout.addWidget(self.buttonStartStop, 2,0, 1,2) # Span 1 row, 2 cols
        self.setLayout(layout)
        self.setTitle('Dispatcher')

        # -- Connect signals --
        self.buttonStartStop.clicked.connect(self.startOrStop)
        if model is not None:
            self.resumeSM.connect(model.resume)
            self.pauseSM.connect(model.pause)
            model.timerTic.connect(self.update)
        self.stop()

    #@QtCore.Slot(float,int,int,int)  # XXFIXME: is this really needed?
    def update(self,serverTime,currentState,eventCount,currentTrial):
        '''Update display of time and events.'''
        self.timeLabel.setText(self._timeFormat.format(serverTime))
        self.stateLabel.setText(self._stateFormat.format(currentState))
        self.eventCountLabel.setText(self._eventCountFormat.format(eventCount))
        if currentTrial>=0:
            self.currentTrialLabel.setText(self._currentTrialFormat.format(currentTrial))
        #trialToPrint = currentTrial if currentTrial>-1 else ''

    def startOrStop(self):
        '''Toggle (start or stop) state machine and dispatcher timer.'''
        if(self.runningState):
            self.stop()
        else:
            self.start()

    def start(self):
        '''Resume state machine.'''
        # -- Change button appearance --
        stylestr = 'QWidget { background-color: %s }'%BUTTON_COLORS['stop']
        self.buttonStartStop.setStyleSheet(stylestr)
        self.buttonStartStop.setText('Stop')

        self.resumeSM.emit()
        self.runningState = True

    def stop(self):
        '''Pause state machine.'''
        # -- Change button appearance --
        stylestr = 'QWidget { background-color: %s }'%BUTTON_COLORS['start']
        self.buttonStartStop.setStyleSheet(stylestr)
        self.buttonStartStop.setText('Start')
        self.pauseSM.emit()
        self.runningState = False


    #------------------- End of DispatcherGUI class ------------------


def center(guiObj):
    '''Place in the center of the screen (NOT TESTED YET)'''
    screen = QtGui.QDesktopWidget().screenGeometry()
    size =  guiObj.geometry()
    guiObj.move((screen.width()-size.width())/2, (screen.height()-size.height())/2)


if __name__ == "__main__":

    TESTCASE = 2
    if TESTCASE==1:
        import signal
        # -- Needed for Ctrl-C (otherwise you need to kill with Ctrl-\ 
        signal.signal(signal.SIGINT, signal.SIG_DFL)
        app = QtCore.QCoreApplication(sys.argv)
        d = Dispatcher(parent=None,serverType='dummy', connectnow=False, interval=1)
        d.start()
        sys.exit(app.exec_())
    elif TESTCASE==2:
        import signal
        signal.signal(signal.SIGINT, signal.SIG_DFL) # Enable Ctrl-C
        app=QtGui.QApplication.instance() # checks if QApplication already exists 
        if not app: # create QApplication if it doesnt exist 
            app = QtGui.QApplication(sys.argv)
        form = QtGui.QDialog()
        form.setSizePolicy(QtGui.QSizePolicy.Expanding, QtGui.QSizePolicy.Expanding)
        #form.setSizePolicy(QtGui.QSizePolicy.Minimum, QtGui.QSizePolicy.Minimum)
        dispatcherModel = Dispatcher(parent=form,serverType='dummy',connectnow=True, interval=0.5)
        dispatcherView = DispatcherGUI(parent=form)
        dispatcherModel.timerTic.connect(dispatcherView.update)
        dispatcherView.resumeSM.connect(dispatcherModel.resume)
        dispatcherView.pauseSM.connect(dispatcherModel.pause)
        #dispatcherModel.resume()
        form.show()
        app.exec_()

'''
    TESTCASE = 1

    app = QtGui.QApplication(sys.argv)
    form = QtGui.QDialog()
    form.setFixedSize(180,200)
    #form.setSizePolicy(QtGui.QSizePolicy.Expanding,QtGui.QSizePolicy.Expanding)

    if TESTCASE==100:
        dispatcherwidget = Dispatcher(parent=form,connectnow=False)
    elif TESTCASE==101:
        dispatcherwidget = Dispatcher(parent=form,host='soul')
        #        Ci  Co  Li  Lo  Ri  Ro  Tout  t  CONTo TRIGo
        mat = [ [ 0,  0,  0,  0,  0,  0,  2,  1.2,  0,   0   ] ,\
                [ 1,  1,  1,  1,  1,  1,  1,   0,   0,   0   ] ,\
                [ 3,  3,  0,  0,  0,  0,  3,   4,   1,   0   ] ,\
                [ 2,  2,  0,  0,  0,  0,  2,   4,   2,   0   ] ]
        mat = np.array(mat)
        dispatcherwidget.setStateMatrix(mat)

    form.show()
    app.exec_()
    
    # XFIXME: maybe this way is better
    #sys.exit(app.exec_())
'''

