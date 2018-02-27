#!/usr/bin/env python

'''
This example shows how to add parameters to a paradigm.
The example also shows how to use methods from paramgui to run the application.
'''

__author__ = 'Santiago Jaramillo <sjara@uoregon.edu>'
__created__ = '2013-03-18'

import sys
from PySide import QtCore 
from PySide import QtGui 
from taskontrol.settings import rigsettings
from taskontrol.core import dispatcher
from taskontrol.core import statematrix
from taskontrol.core import paramgui
import signal


class Paradigm(QtGui.QMainWindow):
    def __init__(self, parent=None, paramfile=None, paramdictname=None):
        super(Paradigm, self).__init__(parent)

        # -- Read settings --
        smServerType = rigsettings.STATE_MACHINE_TYPE

        # -- Create dispatcher --
        self.dispatcherModel = dispatcher.Dispatcher(serverType=smServerType,interval=0.1)
        self.dispatcherView = dispatcher.DispatcherGUI(model=self.dispatcherModel)

        # -- Add parameters --
        self.params = paramgui.Container()
        self.params['periodOn'] = paramgui.NumericParam('Period On',value=0.5,
                                                        group='Timing Parameters')
        self.params['periodOff'] = paramgui.NumericParam('Period Off',value=1,
                                                         group='Timing Parameters')
        timingParams = self.params.layout_group('Timing Parameters')
        self.params['irrelevant1'] = paramgui.MenuParam('Irrelevant 1',
                                                        ['one_item','another_item'],
                                                        value=0,group='Irrelevant')
        self.params['irrelevant2'] = paramgui.StringParam('Irrelevant 2',value='nothing',
                                                         group='Irrelevant')
        irrelevantParams = self.params.layout_group('Irrelevant')

        # -- Add graphical widgets to main window --
        centralWidget = QtGui.QWidget()
        layoutMain = QtGui.QHBoxLayout()
        layoutMain.addWidget(self.dispatcherView)
        layoutOneColumn = QtGui.QVBoxLayout()
        layoutOneColumn.addWidget(timingParams)
        layoutOneColumn.addWidget(irrelevantParams)
        layoutMain.addLayout(layoutOneColumn)
        centralWidget.setLayout(layoutMain)
        self.setCentralWidget(centralWidget)

        # -- Center in screen --
        paramgui.center_in_screen(self)

        # -- Connect signals from dispatcher --
        self.dispatcherModel.prepareNextTrial.connect(self.prepare_next_trial)
        self.dispatcherModel.timerTic.connect(self.timer_tic)


    def set_state_matrix(self):
        self.sm = statematrix.StateMatrix(inputs=rigsettings.INPUTS,
                                          outputs=rigsettings.OUTPUTS,
                                          readystate='ready_next_trial')

        timeOn = self.params['periodOn'].get_value()
        timeOff = self.params['periodOff'].get_value()
        
        # -- Set state matrix --
        self.sm.add_state(name='first_state', statetimer=timeOn,
                          transitions={'Cin':'second_state','Tup':'second_state'},
                          outputsOn=['centerLED'])
        self.sm.add_state(name='second_state', statetimer=timeOff,
                          transitions={'Lin':'first_state','Tup':'ready_next_trial'},
                          outputsOff=['centerLED'])
        print self.sm

        self.dispatcherModel.set_state_matrix(self.sm)


    def prepare_next_trial(self, nextTrial):
        print '\nPrepare trial %d'%nextTrial
        self.set_state_matrix()
        # -- Show results from previous trial --
        lastTenEvents = self.dispatcherModel.eventsMat[-10:-1]
        print 'Last 10 events:'
        for oneEvent in lastTenEvents:
            print '%0.3f\t %d\t %d'%(oneEvent[0],oneEvent[1],oneEvent[2])
        self.dispatcherModel.ready_to_start_trial()


    def start_new_trial(self, currentTrial):
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
        self.dispatcherModel.die()
        event.accept()


if __name__ == '__main__':
    (app,paradigm) = paramgui.create_app(Paradigm)

