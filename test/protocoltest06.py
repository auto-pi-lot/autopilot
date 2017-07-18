#!/usr/bin/env python

'''
Example protocol.
Using savedata widge.

'''

__version__ = '0.0.1'
__author__ = 'Santiago Jaramillo <jara@cshl.edu>'
__created__ = '2009-11-15'


import sys
sys.path.append('../')
from PyQt4 import QtCore 
from PyQt4 import QtGui 
import numpy as np
import paramgui
import dispatcher
import statematrix
import rigsettings
import savedata

reload(paramgui)
reload(dispatcher)
reload(statematrix)
reload(rigsettings)
reload(savedata)

import eventsplot
reload(eventsplot)


class Protocol(QtGui.QDialog):
    def __init__(self, parent=None):
        super(Protocol, self).__init__(parent)

        # -- Read settings --
        smhost = rigsettings.STATE_MACHINE_SERVER

        # -- Add widgets --
        self.dispatcher = dispatcher.Dispatcher(host=smhost,connectnow=False)
        self.savedata = savedata.SaveData()
        self.params = []
        for ind in range(6):
            self.params.append(paramgui.NumericParam('Param%d'%ind,value=1.1*ind))
        self.param3 = paramgui.MenuParam('MenuParam',('One','Two','Three'))
        self.evplot = eventsplot.EventsPlot()

        layoutMain = QtGui.QVBoxLayout()
        layoutTop = QtGui.QVBoxLayout()
        layoutBottom = QtGui.QHBoxLayout()
        layoutCol0 = QtGui.QVBoxLayout()
        layoutCol1 = QtGui.QVBoxLayout()
        layoutCol2 = QtGui.QVBoxLayout()
        groupBox1 = QtGui.QGroupBox('Group 1')
        layoutBox1 = QtGui.QVBoxLayout()

        layoutMain.addLayout(layoutTop)
        layoutMain.addStretch()
        layoutMain.addLayout(layoutBottom)

        layoutTop.addWidget(self.evplot)
        layoutBottom.addLayout(layoutCol0)
        layoutBottom.addLayout(layoutCol1)
        layoutBottom.addLayout(layoutCol2)
        #layoutBottom.setStretch(0,1)
        #layoutBottom.setStretch(1,0)

        layoutCol0.addWidget(self.savedata)
        layoutCol0.addWidget(self.dispatcher)
        #layoutCol2.addStretch()
        layoutCol2.addWidget(groupBox1)
        groupBox1.setLayout(layoutBox1)
        for param in self.params:
            layoutBox1.addWidget(param)
        layoutBox1.addWidget(self.param3)
        self.setLayout(layoutMain)
        
        # -- Set state matrix --
        tmin = 0.001            # Very small time
        Sdur = 0.2              # Duration of sound
        RewAvail = 4            # Length of time reward is available
        Rdur = 0.1              # Duration of reward
        Lw = rigsettings.LEFT_WATER  # Left water valve
        Rw = rigsettings.RIGHT_WATER # Right water valve
        #Corr =  
        #Err  =
        
        '''
        mat = []
        #           Ci  Co  Li  Lo  Ri  Ro  Tout  t  CONTo TRIGo
        mat.append([ 0,  0,  0,  0,  0,  0,  2, tmin,  0,   0   ]) # 0: State 0
        mat.append([ 1,  1,  1,  1,  1,  1,  1,   0,   0,   0   ]) # 1: PrepareNextTrial
        mat.append([ 3,  2,  2,  2,  2,  2,  2,   0,   0,   0   ]) # 2: WaitForCpoke
        mat.append([ 3,  3,  3,  3,  3,  3,  4, Sdur,  1,   1   ]) # 3: PlayTarget
        mat.append([ 4,  4,  5,  4,  1,  4,  1, Tout,  0,   0   ]) # 4: WaitForApoke
        mat.append([ 5,  5,  5,  5,  5,  5,  1, Rdur, Lw,   0   ]) # 5: Reward
        '''

        sm = statematrix.StateMatrix(readystate=('ready_next_trial',1))
        sm.addState(name='wait_for_cpoke', selftimer=4,
                    transitions={'Cin':'play_target'})
        sm.addState(name='play_target', selftimer=Sdur,
                    transitions={'Cout':'wait_for_apoke','Tout':'wait_for_apoke'},
                    actions={'DOut':7})
        sm.addState(name='wait_for_apoke', selftimer=RewAvail,
                    transitions={'Lin':'reward','Rin':'punish','Tout':'ready_next_trial'})
        sm.addState(name='reward', selftimer=Rdur,
                    transitions={'Tout':'ready_next_trial'},
                    actions={'DOut':2})
        sm.addState(name='punish', selftimer=Rdur,
                    transitions={'Tout':'ready_next_trial'},
                    actions={'DOut':4})

        #prepareNextTrialStates = ('ready_next_trial','reward','punish')
        prepareNextTrialStates = ('ready_next_trial')
        self.dispatcher.setPrepareNextTrialStates(prepareNextTrialStates,
                                                  sm.getStatesDict())
        self.dispatcher.setStateMatrix(sm.getMatrix())

        # QUESTION: what happens if signal 'READY TO START TRIAL'
        #           is sent while on JumpState?
        #           does it jump to new trial or waits for timeout?


        print sm

        # -- Setup events plot --
        #self.evplot.setStatesColor(np.random.rand(6))
        '''
        statesColor = [ [255,0,0],[0,255,0],[0,0,255],\
                        [255,255,0],[255,0,255],[0,255,255] ]  
        self.evplot.setStatesColor(statesColor)
        '''
        statesColorDict = {'wait_for_cpoke': [127,127,255],
                           'play_target':    [255,255,0],
                           'wait_for_apoke': [191,191,255],
                           'reward':         [0,255,0],
                           'punish':         [255,0,0],
                           'ready_next_trial':   [0,0,0]}
        self.evplot.setStatesColor(statesColorDict,sm.getStatesDict())


        # -- Connect signals from dispatcher --
        self.connect(self.dispatcher,QtCore.SIGNAL('PrepareNextTrial'),self.prepareNextTrial)
        self.connect(self.dispatcher,QtCore.SIGNAL('StartNewTrial'),self.startNewTrial)
        self.connect(self.dispatcher,QtCore.SIGNAL('TimerTic'),self.timerTic)


    def prepareNextTrial(self, nextTrial):
        print 'Prepare trial %d'%nextTrial
        self.dispatcher.readyToStartTrial()


    def startNewTrial(self, currentTrial):
        print 'Started trial %d'%currentTrial


    def timerTic(self,etime,lastEvents):
        #timesAndStates = lastEvents[:,[2,3]]
        #timesAndStates[:,0] -= etime
        # XFIXME: I should not access attribute of dispatcher directly
        timesAndStates = self.dispatcher.eventsMat[:,[2,3]]
        # XFIXME: next line maybe the first place where a copy is made:
        # It's either inefficient to copy all states, or I'm modifying
        # the original eventsMat which is BAD!
        #timesAndStates[:,0] -= etime
        #print etime
        #print timesAndStates
        self.evplot.updatePlot(timesAndStates, etime)


    def closeEvent(self, event):
        '''Make sure dispatcher stops and closes when closing window.'''
        # XFIXME: this feel recursive, I thought the event would come back
        #        to the parent of dispatcher
        self.dispatcher.die()
        event.accept()


if __name__ == "__main__":

    app = QtGui.QApplication(sys.argv)
    protocol = Protocol()
    protocol.show()
    app.exec_()

    #protocol.dispatcher.stop()
    #raise

