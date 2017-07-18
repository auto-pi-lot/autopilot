'''
Create a paradigm for calibrating the amount of water delivered.
'''

import sys
from PySide import QtCore 
from PySide import QtGui 
from taskontrol.settings import rigsettings
from taskontrol.core import dispatcher
from taskontrol.core import statematrix
from taskontrol.core import savedata
from taskontrol.core import paramgui
from taskontrol.core import messenger
from taskontrol.core import arraycontainer
from taskontrol.plugins import manualcontrol


class WaterCalibration(QtGui.QMainWindow):
    def __init__(self, parent=None, paramfile=None, paramdictname=None, dummy=False):
        super(WaterCalibration, self).__init__(parent)

        self.name = '2afc'

        # -- Read settings --
        if dummy:
            smServerType = 'dummy'
        else:
            smServerType = rigsettings.STATE_MACHINE_TYPE

        # -- Module for saving data --
        self.saveData = savedata.SaveData(rigsettings.DATA_DIR)

        # -- Create an empty state matrix --
        self.sm = statematrix.StateMatrix(inputs=rigsettings.INPUTS,
                                          outputs=rigsettings.OUTPUTS,
                                          readystate='readyForNextTrial')

        # -- Add parameters --
        self.params = paramgui.Container()
        '''
        self.params['experimenter'] = paramgui.StringParam('Experimenter',
                                                           value='experimenter',
                                                           group='Session info')
        self.params['subject'] = paramgui.StringParam('Subject',value='subject',
                                                      group='Session info')
        self.sessionInfo = self.params.layout_group('Session info')
        '''

        self.params['timeWaterValveL'] = paramgui.NumericParam('Time valve left',value=0.04,
                                                               units='s',group='Valves times')
        #self.params['timeWaterValveC'] = paramgui.NumericParam('Time valve center',value=0.04,
        #                                                       units='s',group='Valves times')
        self.params['timeWaterValveR'] = paramgui.NumericParam('Time valve right',value=0.04,
                                                               units='s',group='Valves times')
        valvesTimes = self.params.layout_group('Valves times')

        self.params['waterVolumeL'] = paramgui.NumericParam('Water volume left',value=0,
                                                               units='ml',group='Water volume')
        #self.params['waterVolumeC'] = paramgui.NumericParam('Water volume center',value=0,
        #                                                       units='ml',group='Water volume')
        self.params['waterVolumeR'] = paramgui.NumericParam('Water volume right',value=0,
                                                               units='ml',group='Water volume')
        waterVolume = self.params.layout_group('Water volume')

        self.params['offTime'] = paramgui.NumericParam('Time between',value=0.5,
                                                       units='s',group='Schedule')
        self.params['nDeliveries'] = paramgui.NumericParam('N deliveries',value=2,
                                                       units='',group='Schedule')
        self.params['nDelivered'] = paramgui.NumericParam('N delivered',value=0,
                                                       units='',group='Schedule')
        self.params['nDelivered'].set_enabled(False)
        schedule = self.params.layout_group('Schedule')


        # -- Create dispatcher --
        self.dispatcherModel = dispatcher.Dispatcher(serverType=smServerType,interval=0.1)
        self.dispatcherView = dispatcher.DispatcherGUI(model=self.dispatcherModel)
 
        # -- Manual control of outputs --
        self.manualControl = manualcontrol.ManualControl(self.dispatcherModel.statemachine)

        # -- Add graphical widgets to main window --
        self.centralWidget = QtGui.QWidget()
        layoutMain = QtGui.QHBoxLayout()
        layoutCol1 = QtGui.QVBoxLayout()
        layoutCol2 = QtGui.QVBoxLayout()
        layoutCol3 = QtGui.QVBoxLayout()

        layoutCol1.addWidget(self.saveData)
        #layoutCol1.addWidget(self.sessionInfo)
        layoutCol1.addWidget(self.dispatcherView)

        layoutCol2.addWidget(valvesTimes)
        layoutCol2.addStretch()
        layoutCol2.addWidget(self.manualControl)

        layoutCol3.addWidget(waterVolume)
        layoutCol3.addStretch()
        layoutCol3.addWidget(schedule)

        layoutMain.addLayout(layoutCol1)
        layoutMain.addLayout(layoutCol2)
        layoutMain.addLayout(layoutCol3)

        self.centralWidget.setLayout(layoutMain)
        self.setCentralWidget(self.centralWidget)

        # -- Add variables storing results --
        self.results = arraycontainer.Container()

        # -- Connect signals from dispatcher --
        self.dispatcherModel.prepareNextTrial.connect(self.prepare_next_trial)
        self.dispatcherModel.timerTic.connect(self._timer_tic)

        # -- Connect messenger --
        self.messagebar = messenger.Messenger()
        self.messagebar.timedMessage.connect(self._show_message)
        self.messagebar.collect('Created window')

        # -- Connect signals to messenger
        self.saveData.logMessage.connect(self.messagebar.collect)
        self.dispatcherModel.logMessage.connect(self.messagebar.collect)

        # -- Connect other signals --
        self.saveData.buttonSaveData.clicked.connect(self.save_to_file)

        # -- Center in screen --
        paramgui.center_in_screen(self)

        # -- Prepare first trial --
        # - No need to prepare here. Dispatcher sends a signal when pressing Start -
        #self.prepare_next_trial(0)
        

    def _show_message(self,msg):
        self.statusBar().showMessage(str(msg))
        print msg

    def _timer_tic(self,etime,lastEvents):
        pass

    def save_to_file(self):
        pass

    def prepare_next_trial(self, nextTrial):
        print '============ Prearing trial {0} ==========='.format(self.dispatcherModel.currentTrial)
        self.sm.reset_transitions()
        valveTimeR = self.params['timeWaterValveR'].get_value()
        #valveTimeR = self.params['timeWaterValveR'].get_value()

        self.sm.add_state(name='startTrial', statetimer=0,
                          transitions={'Tup':'valveOnL'})
        self.sm.add_state(name='valveOnL',
                          statetimer=self.params['timeWaterValveL'].get_value(),
                          transitions={'Tup':'valveOffL'},
                          outputsOn={'leftLED','leftWater'})
        self.sm.add_state(name='valveOffL',
                          statetimer=self.params['offTime'].get_value(),
                          transitions={'Tup':'valveOnR'},
                          outputsOff={'leftLED','leftWater'})
        self.sm.add_state(name='valveOnR',
                          statetimer=self.params['timeWaterValveR'].get_value(),
                          transitions={'Tup':'valveOffR'},
                          outputsOn={'rightLED','rightWater'})
        self.sm.add_state(name='valveOffR',
                          statetimer=self.params['offTime'].get_value(),
                          transitions={'Tup':'readyForNextTrial'},
                          outputsOff={'rightLED','rightWater'})
        pass
        print self.sm ### DEBUG
        self.dispatcherModel.set_state_matrix(self.sm)

        #if self.dispatcherModel.currentTrial < 0:
        #print '---- {0} ---'.format(self.dispatcherModel.currentTrial)
        #pass
        if self.params['nDelivered'].get_value() < self.params['nDeliveries'].get_value():
            self.dispatcherModel.ready_to_start_trial()
            self.params['nDelivered'].set_value(int(self.params['nDelivered'].get_value())+1)
        else:
            self.dispatcherView.stop()
            self.params['nDelivered'].set_value(0)

    def closeEvent(self, event):
        '''
        Executed when closing the main window.
        This method is inherited from QtGui.QMainWindow, which explains
        its camelCase naming.
        '''
        self.dispatcherModel.die()
        event.accept()

if __name__ == "__main__":
    (app,paradigm) = paramgui.create_app(WaterCalibration)
