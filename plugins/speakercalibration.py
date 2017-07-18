'''
Generate sounds at different frequencies to calibrate speakers.

What I want:
- Play sound until press stop
  . To enable enough time to measure amplitude in oscilloscope
- GUI: 
  . array of frequencies
  . one button each freq to start/stop
  . a box to enter amplitude
  . a button to plot results
  . a button to save results

[0.03,0.014,0.013,0.004,0.005,0.006,0.01,0.01,0.03,0.017,0.03,0.028,0.03,0.03,0.03,0.03]
'''

import sys
from PySide import QtCore 
from PySide import QtGui 
from taskontrol.core import messenger
from taskontrol.settings import rigsettings
import pyo
import signal
import time
import os
import numpy as np
import h5py

SOUND_FREQUENCIES = np.logspace(np.log10(1000), np.log10(40000), 16)
SOUND_FREQUENCIES = np.sort(np.concatenate((SOUND_FREQUENCIES,[3000,5000,7000,11000,16000,24000])))
DEFAULT_AMPLITUDE = 0.01
AMPLITUDE_STEP = 0.0005
MAX_AMPLITUDE = 0.5

DEFAULT_INTENSITY = 50 # dB-SPL

DATADIR = '/var/tmp/'

BUTTON_COLORS = {'on':'red','off':'black'}


# -- Set computer's sound level --
if hasattr(rigsettings,'SOUND_VOLUME_LEVEL'):
    baseVol = rigsettings.SOUND_VOLUME_LEVEL
    if baseVol is not None:
        os.system('amixer set Master {0}% > /dev/null'.format(baseVol))
        print 'Set sound volume to {0}%'.format(baseVol)
        

def create_sound(soundParams):
    amplitude = soundParams['amplitude']
    if soundParams['type']=='sine':
        soundObjList = [pyo.Sine(freq=soundParams['frequency'],mul=amplitude)]
    if soundParams['type']=='chord':
        nTones = soundParams['ntones']  # Number of components in chord
        factor = soundParams['factor']  # Components will be in range [f/factor, f*factor]
        centerFreq = soundParams['frequency']
        freqEachComp = np.logspace(np.log10(centerFreq/factor),np.log10(centerFreq*factor),nTones)
        soundObjList = []
        for indcomp in range(nTones):
            soundObjList.append(pyo.Sine(freq=freqEachComp[indcomp],mul=amplitude))
    return soundObjList

class OutputButton(QtGui.QPushButton):
    '''Single button for manual output'''
    def __init__(self, soundServer, soundFreq, channel=1, parent=None):
        super(OutputButton, self).__init__(str(int(np.round(soundFreq))), parent)

        self.soundServer = soundServer
        self.soundFreq = soundFreq
        self.soundAmplitude = DEFAULT_AMPLITUDE
        self.channel = channel
        self.soundType = 'sine'
        self.setCheckable(True)
        self.clicked.connect(self.toggleOutput)
        self.create_sound(soundType='sine')
        '''
        self.soundObj = pyo.Sine(freq=self.soundFreq,mul=DEFAULT_AMPLITUDE)
        if soundFreq<40000:
            self.soundObj = pyo.Sine(freq=self.soundFreq,mul=DEFAULT_AMPLITUDE)
        else:
            self.soundObj = pyo.Noise(mul=DEFAULT_AMPLITUDE)
        '''
    def create_sound(self,soundType):
        if soundType=='sine':
            soundParams = {'type':'sine', 'frequency':self.soundFreq,
                           'amplitude':self.soundAmplitude}
        elif soundType=='chord':
            soundParams = {'type':'chord', 'frequency':self.soundFreq, 'ntones':12, 'factor':1.2,
                           'amplitude':self.soundAmplitude}
        self.soundObjList = create_sound(soundParams)

    def toggleOutput(self):
        if self.isChecked():
            self.start()
        else:
            self.stop()

    def start(self):
        '''Start action.'''
        self.setChecked(True)
        stylestr = 'QPushButton {{color: {0}; font: bold}}'.format(BUTTON_COLORS['on'])
        self.setStyleSheet(stylestr)
        self.create_sound(soundType=self.soundType)
        self.play_sound()

    def stop(self):
        '''Stop action.'''
        self.setChecked(False)
        stylestr = ''
        self.setStyleSheet(stylestr)
        self.stop_sound()
        
    def play_sound(self):
        #self.soundObj = pyo.Sine(freq=soundfreq,mul=0.02).mix(2).out()
        #self.soundObj.setMul(0.01) 
        for soundObj in self.soundObjList:
            soundObj.out(chnl=self.channel)

    def change_amplitude(self,amplitude):
        self.soundAmplitude = amplitude
        for soundObj in self.soundObjList:
            soundObj.setMul(amplitude)

    def stop_sound(self):
        for soundObj in self.soundObjList:
            soundObj.stop()

class AmplitudeControl(QtGui.QDoubleSpinBox):
    def __init__(self,soundButton,parent=None):
        super(AmplitudeControl,self).__init__(parent)
        self.setRange(0,MAX_AMPLITUDE)
        self.setSingleStep(AMPLITUDE_STEP)
        self.setDecimals(4)
        self.setValue(DEFAULT_AMPLITUDE)
        self.soundButton = soundButton
        self.valueChanged.connect(self.change_amplitude)
    def change_amplitude(self,value):
        self.soundButton.change_amplitude(value)

class SoundControl(QtGui.QGroupBox):
    def __init__(self, soundServer, channel=0, channelName='left', parent=None):
        super(SoundControl, self).__init__(parent)
        self.soundServer = soundServer
        self.soundFreqs = SOUND_FREQUENCIES
        # -- Create graphical objects --
        layout = QtGui.QGridLayout()
        nFreq = len(self.soundFreqs)
        self.outputButtons = nFreq*[None]
        self.amplitudeControl = nFreq*[None]
        self.channel = channel
        
        stopAllButton = QtGui.QPushButton('STOP ALL')
        layout.addWidget(stopAllButton, 0, 1)
        stopAllButton.clicked.connect(self.stop_all)
        playAllButton = QtGui.QPushButton('PLAY ALL')
        layout.addWidget(playAllButton, 0, 0)
        playAllButton.clicked.connect(self.play_all)

        for indf,onefreq in enumerate(self.soundFreqs):
            self.outputButtons[indf] = OutputButton(self.soundServer,onefreq,
                                                    channel=self.channel)
            self.amplitudeControl[indf] = AmplitudeControl(self.outputButtons[indf])
            layout.addWidget(self.outputButtons[indf], indf+1, 0)
            layout.addWidget(self.amplitudeControl[indf], indf+1, 1)
            
        self.setLayout(layout)
        self.setTitle('Speaker '+channelName)
    
    def play_all(self):
        for oneButton in self.outputButtons:
            oneButton.start()

    def stop_all(self):
        for oneButton in self.outputButtons:
            oneButton.stop()

    def amplitude_array(self):
        amplitudeEach = np.empty(len(self.amplitudeControl))
        for indf,oneAmplitude in enumerate(self.amplitudeControl):
            amplitudeEach[indf] = oneAmplitude.value()
        return amplitudeEach

class LoadButton(QtGui.QPushButton):
    '''
    Note: this class does not change target intensity value.
          It load data for the saved target intensity.
    '''
    logMessage = QtCore.Signal(str)
    def __init__(self, soundControlArray, parent=None):
        super(LoadButton, self).__init__('Load data', parent)
        self.soundControlArray = soundControlArray       
        self.calData = None # Object to contain loaded data
        self.clicked.connect(self.load_data)
    def load_data(self):
        fname,ffilter = QtGui.QFileDialog.getOpenFileName(self,'Open calibration file',DATADIR,'*.h5')
        self.calData = Calibration(fname)
        self.update_values()
    def update_values(self):
        nChannels = 2 # XFIXME: hardcoded
        for indch in range(nChannels):
            for indf in range(len(self.soundControlArray[indch].outputButtons)):
                oneOutputButton = self.soundControlArray[indch].outputButtons[indf]
                oneAmplitudeControl = self.soundControlArray[indch].amplitudeControl[indf]
                thisAmp = self.calData.find_amplitude(oneOutputButton.soundFreq,
                                                      self.calData.intensity)
                # NOTE: We are calculating values twice.
                #       find_amplitude() finds value for both channels
                oneAmplitudeControl.setValue(thisAmp[indch])
                oneOutputButton.change_amplitude(thisAmp[indch])

class PlotButton(QtGui.QPushButton):
    '''
    '''
    def __init__(self, soundControlArray, parent=None):
        super(PlotButton, self).__init__('Plot results', parent)
        self.soundControlArray = soundControlArray       
        self.clicked.connect(self.plot_data)
    def plot_data(self):
        frequencies = self.soundControlArray[0].soundFreqs
        amplitudeData = []
        for soundControl in self.soundControlArray:
            amplitudeData.append(soundControl.amplitude_array())
        amplitudeData = np.array(amplitudeData)
        import matplotlib.pyplot as plt
        plt.plot(frequencies,np.array(amplitudeData).T,'o-')
        plt.gca().set_xscale('log')
        plt.draw()
        plt.show()

class SaveButton(QtGui.QPushButton):
    '''
    '''
    logMessage = QtCore.Signal(str)
    def __init__(self, soundControlArray, parent=None):
        super(SaveButton, self).__init__('Save calibration', parent)
        self.soundControlArray = soundControlArray       
        self.clicked.connect(self.save_data)
        self.filename = None
        self.datadir = DATADIR
        self.interactive = False
    def save_data(self, date=None, filename=None):
        if filename is not None:
            defaultFileName = filename
        else:
            if date is None:
                date = time.strftime('%Y%m%d%H%M%S',time.localtime())
            dataRootDir = self.datadir
            fileExt = 'h5'
            dataDir = dataRootDir #os.path.join(dataRootDir)
            if not os.path.exists(dataDir):
                os.makedirs(dataDir)
            fileNameOnly = 'speaker_calibration_{0}.{1}'.format(date,fileExt)
            defaultFileName = os.path.join(dataDir,fileNameOnly)

        self.logMessage.emit('Saving data...')

        if self.interactive:
            fname,ffilter = QtGui.QFileDialog.getSaveFileName(self,'CHOOSE',DATADIR,'*.*')
            if not fname:
                self.logMessage.emit('Saving cancelled.')
                return
        else:
            fname = defaultFileName
        
        # Create array with amplitudes from all channels
        amplitudeData = []
        for soundControl in self.soundControlArray:
            amplitudeData.append(soundControl.amplitude_array())
        amplitudeData = np.array(amplitudeData)

        ###print amplitudeData ###DEBUG

        # -- Create data file --
        # XFIXME: check that the file opened correctly
        if os.path.exists(fname):
            self.logMessage.emit('File exists. I will rewrite {0}'.format(fname))
        h5file = h5py.File(fname,'w')

        try:
            dsetAmp = h5file.create_dataset('amplitude',data=amplitudeData)
            dsetAmp.attrs['Channels'] = 'left,right' # XFIXME: hardcoded
            dsetAmp.attrs['Units'] = '(none)' # XFIXME: hardcoded
            dsetFreq = h5file.create_dataset('frequency',data=SOUND_FREQUENCIES)
            dsetFreq.attrs['Units'] = 'Hz' # XFIXME: hardcoded
            dsetRef = h5file.create_dataset('intensity',data=DEFAULT_INTENSITY)
            dsetRef.attrs['Units'] = 'dB-SPL' # XFIXME: hardcoded
            dsetRef = h5file.create_dataset('computerSoundLevel',
                                            data=rigsettings.SOUND_VOLUME_LEVEL)
            dsetRef.attrs['Units'] = '%' # XFIXME: hardcoded
        except UserWarning as uwarn:
            self.logMessage.emit(uwarn.message)
            print uwarn.message
        except:
            h5file.close()
            raise
        h5file.close()
 
        self.filename = fname
        self.logMessage.emit('Saved data to {0}'.format(fname))
    
class VerticalLine(QtGui.QFrame):
    def __init__(self,parent=None):
        super(VerticalLine, self).__init__(parent)
        self.setFrameStyle(QtGui.QFrame.VLine)
        self.setFrameShadow(QtGui.QFrame.Sunken)
        self.setSizePolicy(QtGui.QSizePolicy.Minimum,
                           QtGui.QSizePolicy.Expanding)
     
    
class SpeakerCalibration(QtGui.QMainWindow):
    def __init__(self, parent=None, paramfile=None, paramdictname=None):
        super(SpeakerCalibration, self).__init__(parent)

        self.name = 'speakercalibration'
        self.soundServer = self.initialize_sound()

        # -- Add graphical widgets to main window --
        self.centralWidget = QtGui.QWidget()
        layoutMain = QtGui.QHBoxLayout()
        layoutRight = QtGui.QVBoxLayout()
               
        self.soundControlL = SoundControl(self.soundServer, channel=0, channelName='left')
        self.soundControlR = SoundControl(self.soundServer, channel=1, channelName='right')

        self.saveButton = SaveButton([self.soundControlL,self.soundControlR])
        soundTypeLabel = QtGui.QLabel('Sound type')
        self.soundTypeMenu = QtGui.QComboBox()
        self.soundTypeList = ['sine','chord']
        self.soundTypeMenu.addItems(self.soundTypeList)
        self.soundTypeMenu.activated.connect(self.change_sound_type)
        soundTargetIntensityLabel = QtGui.QLabel('Target intensity [dB-SPL]')
        self.soundTargetIntensity = QtGui.QLineEdit()
        self.soundTargetIntensity.setText(str(DEFAULT_INTENSITY))
        self.soundTargetIntensity.setEnabled(False)
        computerSoundLevelLabel = QtGui.QLabel('Computer sound level [%]')
        self.computerSoundLevel = QtGui.QLineEdit()
        self.computerSoundLevel.setText(str(rigsettings.SOUND_VOLUME_LEVEL))
        self.computerSoundLevel.setEnabled(False)
        self.loadButton = LoadButton([self.soundControlL,self.soundControlR])
        self.plotButton = PlotButton([self.soundControlL,self.soundControlR])
        

        layoutRight.addWidget(self.saveButton)
        layoutRight.addWidget(soundTypeLabel)
        layoutRight.addWidget(self.soundTypeMenu)
        layoutRight.addWidget(soundTargetIntensityLabel)
        layoutRight.addWidget(self.soundTargetIntensity)
        layoutRight.addWidget(computerSoundLevelLabel)
        layoutRight.addWidget(self.computerSoundLevel)
        layoutRight.addWidget(self.loadButton)
        layoutRight.addWidget(self.plotButton)
        layoutRight.addStretch()

        layoutMain.addWidget(self.soundControlL)
        layoutMain.addWidget(VerticalLine())
        layoutMain.addWidget(self.soundControlR)
        layoutMain.addWidget(VerticalLine())
        layoutMain.addLayout(layoutRight)
        

        self.centralWidget.setLayout(layoutMain)
        self.setCentralWidget(self.centralWidget)

        # -- Center in screen --
        self._center_in_screen()

        # -- Add variables storing results --
        #self.results = arraycontainer.Container()

        # -- Connect messenger --
        self.messagebar = messenger.Messenger()
        self.messagebar.timedMessage.connect(self._show_message)
        self.messagebar.collect('Created window')

        # -- Connect signals to messenger
        self.saveButton.logMessage.connect(self.messagebar.collect)
        
        # -- Connect other signals --
        #self.saveData.buttonSaveData.clicked.connect(self.save_to_file)

    def change_sound_type(self,soundTypeInd):
        for oneOutputButton in self.soundControlL.outputButtons:
            #oneOutputButton.create_sound(self.soundTypeList[soundTypeInd])
            oneOutputButton.soundType = self.soundTypeList[soundTypeInd]
        for oneOutputButton in self.soundControlR.outputButtons:
            #oneOutputButton.create_sound(self.soundTypeList[soundTypeInd])
            oneOutputButton.soundType = self.soundTypeList[soundTypeInd]

    def initialize_sound(self):
        s = pyo.Server(audio='jack').boot()
        s.start()
        return s

    def _show_message(self,msg):
        self.statusBar().showMessage(str(msg))
        print msg

    def _center_in_screen(self):
        qr = self.frameGeometry()
        cp = QtGui.QDesktopWidget().availableGeometry().center()
        qr.moveCenter(cp)
        self.move(qr.topLeft())

    def closeEvent(self, event):
        '''
        Executed when closing the main window.
        This method is inherited from QtGui.QMainWindow, which explains
        its camelCase naming.
        '''
        #print 'ENTERED closeEvent()' # DEBUG
        #print 'Closing all connections.' # DEBUG
        self.soundServer.shutdown()
        #self.pyoServer.shutdown()
        event.accept()

class Calibration(object):
    '''
    Reads data from file and finds appropriate amplitude for a desired
    sound intensity at a particular frequency.
    This class assumes two channels (left,right)
    '''
    def __init__(self,filename=None):
        if filename is not None:
            h5file = h5py.File(filename,'r')
            self.amplitude = h5file['amplitude'][...]
            self.frequency = h5file['frequency'][...]
            self.intensity = h5file['intensity'][...]
            h5file.close()
        else:
            self.amplitude = 0.01*np.ones((2,2))
            self.frequency = np.array([1000,4000])
            self.intensity = 60
        self.nChannels = self.amplitude.shape[0]
            
    def find_amplitude(self,frequency,intensity):
        '''
        Linear interpolation (in log-freq) to find appropriate amplitude
        Returns an array with the amplitude for each channel.
        '''
        ampAtRef = []
        for chn in range(self.nChannels):     
            thisAmp = np.interp(np.log10(frequency),np.log10(self.frequency),
                                self.amplitude[chn,:])
            ampAtRef.append(thisAmp)
        # Find factor from ref intensity
        dBdiff = intensity-self.intensity
        ampFactor = 10**(dBdiff/20.0)
        return np.array(ampAtRef)*ampFactor


if __name__ == "__main__":
    signal.signal(signal.SIGINT, signal.SIG_DFL) # Enable Ctrl-C
    app=QtGui.QApplication.instance() # checks if QApplication already exists 
    if not app: # create QApplication if it doesnt exist 
        app = QtGui.QApplication(sys.argv)
    spkcal = SpeakerCalibration()
    spkcal.show()
    sys.exit(app.exec_())
    '''
    if 1:
        cal=Calibration('/tmp/speaker_calibration_20140322175816.h5')
        print cal.find_amplitude(1200,60)
        print cal.find_amplitude(1200,40)
    '''

