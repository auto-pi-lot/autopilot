#!/usr/bin/env python

'''
This example implements a simple two-alternative force choice paradigm.

TODO:
- Add subject/experimenter section
- Make container for results

SEE COMPLEX EXPERTPORT PARADIGM:
/home/sjara/zadorlab/human_psychophysics/reversal/@saja_reversal/saja_reversal.m

'''

__author__ = 'Santiago Jaramillo <jara@cshl.edu>'
__created__ = '2013-07-17'

import sys
from PySide import QtCore 
from PySide import QtGui 
from taskontrol.settings import rigsettings
from taskontrol.core import dispatcher
from taskontrol.core import statematrix
from taskontrol.core import paramgui
from taskontrol.core import arraycontainer
from taskontrol.core import savedata
from taskontrol.core import messenger
from taskontrol.core import utils
from taskontrol.plugins import sidesplot
from taskontrol.plugins import manualcontrol
#from taskontrol.plugins import stylesheets
import signal
import numpy as np

reload(statematrix)
reload(savedata)
reload(paramgui)
reload(messenger)
reload(utils)


class Paradigm(QtGui.QMainWindow):
    def __init__(self, parent=None, paramfile=None, paramdictname=None):
        super(Paradigm, self).__init__(parent)

        #self.setStyleSheet(stylesheets.styleCompact)

        # -- Read settings --
        smServerType = rigsettings.STATE_MACHINE_TYPE
        #smServerType = 'dummy'

        # -- Module for saving data --
        self.saveData = savedata.SaveData(rigsettings.DATA_DIR)

        # -- Sides plot --
        sidesplot.set_pg_colors(self)
        self.mySidesPlot = sidesplot.SidesPlot(nTrials=80)

        # -- Create an empty state matrix --
        self.sm = statematrix.StateMatrix(inputs=rigsettings.INPUTS,
                                          outputs=rigsettings.OUTPUTS,
                                          readystate='ready_next_trial')

        # -- Add parameters --
        self.params = paramgui.Container()
        self.params['experimenter'] = paramgui.StringParam('Experimenter',value='santiago',
                                                           group='Session info')
        self.params['subject'] = paramgui.StringParam('Subject',value='saja000',
                                                      group='Session info')
        sessionInfo = self.params.layout_group('Session info')

        self.params['stimulusDuration'] = paramgui.NumericParam('Stim duration',value=0.2,
                                                        group='Timing parameters')
        self.params['rewardDuration'] = paramgui.NumericParam('Reward duration',value=0.05,
                                                        group='Timing parameters')
        timingParams = self.params.layout_group('Timing parameters')

        # -- Load parameters from a file --
        #self.params.from_file('params_008.py','saja002') ### DEBUG
        self.params.from_file(paramfile,paramdictname)

        # -- Create dispatcher --
        self.dispatcherModel = dispatcher.Dispatcher(serverType=smServerType,interval=0.3)
        self.dispatcherView = dispatcher.DispatcherGUI(model=self.dispatcherModel)
 
        # -- Manual control of outputs --
        self.manualControl = manualcontrol.ManualControl(self.dispatcherModel.statemachine)

        # -- Add graphical widgets to main window --
        centralWidget = QtGui.QWidget()
        layoutMain = QtGui.QVBoxLayout()
        layoutTop = QtGui.QVBoxLayout()
        layoutBottom = QtGui.QHBoxLayout()
        layoutCol1 = QtGui.QVBoxLayout()
        layoutCol2 = QtGui.QVBoxLayout()

        
        layoutMain.addLayout(layoutTop)
        #layoutMain.addStretch()
        layoutMain.addSpacing(0)
        layoutMain.addLayout(layoutBottom)

        layoutTop.addWidget(self.mySidesPlot)

        layoutBottom.addLayout(layoutCol1)
        layoutBottom.addLayout(layoutCol2)

        layoutCol1.addWidget(self.saveData)
        layoutCol1.addWidget(sessionInfo)
        layoutCol1.addWidget(self.dispatcherView)
        
        layoutCol2.addWidget(timingParams)
        layoutCol2.addWidget(self.manualControl)

        centralWidget.setLayout(layoutMain)
        self.setCentralWidget(centralWidget)

        # -- Center in screen --
        self.center_in_screen()


        # -- Add variables for storing results --
        maxNtrials = 4000
        self.results = arraycontainer.Container()
        self.results.labels['rewardSide'] = {'left':0,'right':1}
        self.results['rewardSide'] = np.random.randint(2,size=maxNtrials)
        self.results.labels['choice'] = {'left':0,'right':1,'none':2}
        self.results['choice'] = np.empty(maxNtrials,dtype=int)
        self.results.labels['outcome'] = {'correct':1,'error':0,'invalid':2}
        self.results['outcome'] = np.empty(maxNtrials,dtype=int)
        self.results['timeTrialStart'] = np.empty(maxNtrials,dtype=float)
        self.results['timeCenterIn'] = np.empty(maxNtrials,dtype=float)
        self.results['timeCenterOut'] = np.empty(maxNtrials,dtype=float)
        self.results['timeSideIn'] = np.empty(maxNtrials,dtype=float)

        # --- Create state matrix ---
        #self.set_state_matrix() ################# ?????????????

        # -- Connect signals from dispatcher --
        self.dispatcherModel.prepareNextTrial.connect(self.prepare_next_trial)
        ###self.dispatcherModel.startNewTrial.connect(self.start_new_trial)
        self.dispatcherModel.timerTic.connect(self.timer_tic)

        # -- Connect messenger --
        self.messagebar = messenger.Messenger()
        self.messagebar.timedMessage.connect(self.show_message)
        #self.messagebar.timedMessage.emit('Created window')
        self.messagebar.collect('Created window')

        # -- Connect signals to messenger
        self.saveData.logMessage.connect(self.messagebar.collect)
        self.dispatcherModel.logMessage.connect(self.messagebar.collect)

        # -- Connect other signals --
        self.saveData.buttonSaveData.clicked.connect(self.save_to_file)

        # -- Prepare first trial --
        self.prepare_next_trial(0)

    def save_to_file(self):
        '''Triggered by button-clicked signal'''
        # Next line is needed to truncate data before saving
        ###self.results.currentTrial = self.dispatcherModel.currentTrial
        self.saveData.to_file([self.params, self.dispatcherModel,
                               self.sm, self.results],
                              self.dispatcherModel.currentTrial,
                              experimenter=self.params['experimenter'].get_value(),
                              subject=self.params['subject'].get_value(),
                              paradigm='example')

    def show_message(self,msg):
        self.statusBar().showMessage(str(msg))
        print msg

    def center_in_screen(self):
        qr = self.frameGeometry()
        cp = QtGui.QDesktopWidget().availableGeometry().center()
        qr.moveCenter(cp)
        self.move(qr.topLeft())

    def set_state_matrix(self,nextCorrectChoice):
        self.sm.reset_transitions()

        stimulusDuration = self.params['stimulusDuration'].get_value()
        rewardDuration = self.params['rewardDuration'].get_value()

        if nextCorrectChoice==self.results.labels['rewardSide']['left']:
            stimOutput = 'LeftLED'
            fromChoiceL = 'reward'
            fromChoiceR = 'punish'
            rewardOutput = 'LeftWater'
        elif nextCorrectChoice==self.results.labels['rewardSide']['right']:
            stimOutput = 'RightLED'
            fromChoiceL = 'punish'
            fromChoiceR = 'reward'
            rewardOutput = 'RightWater'
        else:
            raise ValueError('Value of nextCorrectChoice is not appropriate')

        #print stimOutput, fromChoiceL, rewardOutput ### DEBUG


        # -- Set state matrix --
        self.sm.add_state(name='start_trial', statetimer=0,
                              transitions={'Tup':'wait_for_cpoke'})
        self.sm.add_state(name='wait_for_cpoke', statetimer=4,
                    transitions={'Cin':'play_stimulus'}) #, 'Tup':'ready_next_trial'
        self.sm.add_state(name='play_stimulus', statetimer=stimulusDuration,
                    transitions={'Tup':'wait_for_sidepoke'},
                    outputsOn=[stimOutput])
        self.sm.add_state(name='wait_for_sidepoke', statetimer=4,
                    transitions={'Lin':'choiceL', 'Rin':'choiceR',
                                 'Tup':'ready_next_trial'},
                    outputsOff=[stimOutput])
        self.sm.add_state(name='choiceL', statetimer=0,
                    transitions={'Tup':fromChoiceL})
        self.sm.add_state(name='choiceR', statetimer=0,
                    transitions={'Tup':fromChoiceR})
        self.sm.add_state(name='reward', statetimer=rewardDuration,
                    transitions={'Tup':'stopReward'},
                    outputsOn=[rewardOutput])
        self.sm.add_state(name='punish', statetimer=0,
                    transitions={'Tup':'ready_next_trial'})
        self.sm.add_state(name='stopReward', statetimer=0,
                    transitions={'Tup':'ready_next_trial'},
                    outputsOff=[rewardOutput])

        print self.sm ### DEBUG
        self.dispatcherModel.set_state_matrix(self.sm)
        
        '''
         # XFIXME: Will this change from trial to trial? maybe not.
        prepareNextTrialStates = self.sm.get_ready_states()
        self.dispatcherModel.set_prepare_next_trial_states(prepareNextTrialStates,
                                                  self.sm.get_states_dict())

        print self.sm ### DEBUG
        self.dispatcherModel.set_state_matrix(self.sm.get_matrix(),
                                              self.sm.get_outputs(),
                                              self.sm.get_serial_outputs(),
                                              self.sm.get_state_timers())
        '''

    def prepare_next_trial(self, nextTrial):
        self.params.update_history()
        print '\nPreparing trial %d'%nextTrial
        '''
        lastTenEvents = self.dispatcherModel.eventsMat[-10:-1]
        print 'Last 10 events:'
        for oneEvent in lastTenEvents:
            print '%0.3f\t %d\t %d'%(oneEvent[0],oneEvent[1],oneEvent[2])
        '''
        # -- Prepare next trial --
        nextCorrectChoice = self.results['rewardSide'][nextTrial]
        #print '\nNext choice = {0}'.format(nextCorrectChoice) ### DEBUG
        self.set_state_matrix(nextCorrectChoice)
        #print self.sm ### DEBUG
        self.dispatcherModel.ready_to_start_trial()

        # -- Calculate results from last trial (update outcome, choice, etc) --
        if nextTrial>0:
            self.calculate_results(nextTrial-1)

        # -- Update sides plot --
        self.mySidesPlot.update(self.results['rewardSide'],self.results['outcome'],nextTrial)

    def calculate_results(self,trialIndex):
        #choice = self.results['choice']
        #choiceLabels = self.results.labels['choice']
        eventsThisTrial = self.dispatcherModel.events_one_trial(trialIndex)

        # -- Find beginning of trial --
        startTrialStateID = self.sm.statesNameToIndex['start_trial']
        startTrialInd = np.flatnonzero(eventsThisTrial[:,2]==startTrialStateID)[0]
        self.results['timeTrialStart'][trialIndex] = eventsThisTrial[startTrialInd,0]

        # -- Find valid center-port-in time --
        # XFIXME: be wiser when calculating the times (first may not be the right one)
        waitForCpokeStateID = self.sm.statesNameToIndex['wait_for_cpoke']
        playStimulusStateID = self.sm.statesNameToIndex['play_stimulus']
        centerInInds = utils.find_transition(eventsThisTrial[:,2],
                                                   waitForCpokeStateID,playStimulusStateID)
        if len(centerInInds)>0:
            self.results['timeCenterIn'][trialIndex] = eventsThisTrial[centerInInds[0],0]
        else:
            self.results['timeCenterIn'][trialIndex] = np.nan
        #print self.results['timeCenterIn'][:trialIndex+1] ### DEBUG

        # -- Find center-port-out time --
        waitForSidePokeStateID = self.sm.statesNameToIndex['wait_for_sidepoke']
        CoutID = self.sm.eventsDict['Cout']
        centerOutOnStimInds =  utils.find_event(eventsThisTrial[:,1],eventsThisTrial[:,2],
                                               CoutID,playStimulusStateID)
        centerOutOnWaitInds =  utils.find_event(eventsThisTrial[:,1],eventsThisTrial[:,2],
                                               CoutID,waitForSidePokeStateID)
        centerOutInds = np.concatenate((centerOutOnStimInds,centerOutOnWaitInds))
        if len(centerOutInds)>0:
            self.results['timeCenterOut'][trialIndex] = eventsThisTrial[min(centerOutInds),0]
        else:
            self.results['timeCenterOut'][trialIndex] = np.nan

        #print centerOutInds ### DEBUG
        # print eventsThisTrial ### DEBUG

        # -- Find side-port-in time --
        LinID = self.sm.eventsDict['Lin']
        RinID = self.sm.eventsDict['Rin']
        LinInInds =  utils.find_event(eventsThisTrial[:,1],eventsThisTrial[:,2],
                                            LinID,waitForSidePokeStateID)
        RinInInds =  utils.find_event(eventsThisTrial[:,1],eventsThisTrial[:,2],
                                            RinID,waitForSidePokeStateID)
        SideInInds = np.concatenate((LinInInds,RinInInds))
        if len(SideInInds)>0:
            self.results['timeSideIn'][trialIndex] = eventsThisTrial[min(SideInInds),0]
        else:
            self.results['timeSideIn'][trialIndex] = np.nan
        
        # -- Store choice and outcome --
        if self.sm.statesNameToIndex['choiceL'] in eventsThisTrial[:,2]:
            self.results['choice'][trialIndex] = self.results.labels['choice']['left']
        elif self.sm.statesNameToIndex['choiceR'] in eventsThisTrial[:,2]:
            self.results['choice'][trialIndex] = self.results.labels['choice']['right']
        else:
            self.results['choice'][trialIndex] = self.results.labels['choice']['none']

        if self.sm.statesNameToIndex['reward'] in eventsThisTrial[:,2]:
            self.results['outcome'][trialIndex] = self.results.labels['outcome']['correct']
        else:
            self.results['outcome'][trialIndex] = self.results.labels['outcome']['error']
         

    def start_new_trial(self, currentTrial):
        '''OBSOLETE'''
        print '\n======== Started trial %d ======== '%currentTrial


    def timer_tic(self,etime,lastEvents):
        print '.',
        sys.stdout.flush() # Force printing on the screen at this point


    def closeEvent(self, event):
        '''
        Executed when closing the main window.
        This method is inherited from QtGui.QMainWindow, which explains
        its camelCase naming.
        '''
        ###print 'ENTERED closeEvent()' # DEBUG
        self.dispatcherModel.die()
        event.accept()


if __name__ == "__main__":
    '''
    To load parameters from file at startup:
    python example008_simple2afc.py params_008.py sj002
    
    '''
    #QtCore.pyqtRemoveInputHook() # To stop looping if error occurs (for PyQt not PySide)
    signal.signal(signal.SIGINT, signal.SIG_DFL) # Enable Ctrl-C

    # -- A workaround to enable re-running the app in ipython after closing --
    #app = QtGui.QApplication(sys.argv)
    app=QtGui.QApplication.instance() # checks if QApplication already exists 
    if not app: # create QApplication if it doesnt exist 
        app = QtGui.QApplication(sys.argv)

    if len(sys.argv)>1:
        paramfile = sys.argv[1]
        paramdictname = sys.argv[2]
    else:
        paramfile = None
        paramdictname = None
    #paradigm = Paradigm() ### DEBUG
    paradigm = Paradigm(paramfile=paramfile,paramdictname=paramdictname)
    paradigm.show()
    app.exec_()
