#!/usr/bin/env python

"""
Plugin to show the correct choice on each trial and the outcome (reward/punishment)
"""


__version__ = '0.1'
__author__ = 'Santiago Jaramillo <sjara@uoregon.edu>'
__created__ = '2013-07-21'

from PySide import QtCore 
from PySide import QtGui 
import numpy as np
import pyqtgraph as pg

def set_pg_colors(form):
    """Set default BG and FG color for pyqtgraph plots.

    Args:
        form:
    """
    bgColorRGBA = form.palette().color(QtGui.QPalette.ColorRole.Window)
    fgColorRGBA = form.palette().color(QtGui.QPalette.ColorRole.WindowText)
    pg.setConfigOption('background', bgColorRGBA)
    pg.setConfigOption('foreground', fgColorRGBA)
    pg.setConfigOptions(antialias=True)  ## this will be expensive for the local plot
    #pg.setConfigOptions(antialias=False)  ##

MAXNTRIALS = 10000

class PerformanceDynamicsPlot(pg.PlotWidget):
    """FROM MATLAB: CurrentTrial, SideList, HitHistory, TrialType)"""
    def __init__(self, parent=None, widgetSize=(200,140),nTrials=100,winsize=10):

        """
        Args:
            parent:
            widgetSize:
            nTrials:
            winsize:
        """
        if parent is not None:
            set_pg_colors(parent)
            #XFIXME: when done this way, x-axis starts at -40, not 0
        super(PerformanceDynamicsPlot, self).__init__(parent)

        self.initialSize = widgetSize

        self.nTrialsToPlot = nTrials
        self.trialsToPlot = np.arange(self.nTrialsToPlot)

        self.movingAverageBoth = np.tile(-1,MAXNTRIALS).astype(float)
        self.movingAverageLeft = np.tile(-1,MAXNTRIALS).astype(float)
        self.movingAverageRight = np.tile(-1,MAXNTRIALS).astype(float)
        self.windowSize = winsize

        self.mainPlot = pg.ScatterPlotItem(size=4, symbol='o', pxMode=True,
                                           pen='k', brush='k')
        self.perfLeftPlot = pg.ScatterPlotItem(size=4, symbol='o', pxMode=True,
                                               pen='#4DB8B8', brush='#4DB8B8')
        self.perfRightPlot = pg.ScatterPlotItem(size=4, symbol='o', pxMode=True,
                                               pen='#CC33FF', brush='#CC33FF')
        self.addItem(self.mainPlot)
        self.addItem(self.perfLeftPlot)
        self.addItem(self.perfRightPlot)

        self.outcomeIDs = {'correct':1,'error':0,'invalid':2,'free':3,
                           'nochoice':4,'aftererror':5,'aborted':6} 
        # XFIXME: This should come from somewhere else (to be consisten with the rest)

        # -- Graphical adjustments --
        yAxis = self.getAxis('left')
        #self.setLabel('left', 'Correct',units='%') #units='xxx'
        self.setLabel('bottom', 'Valid trial')
        self.setXRange(0, self.nTrialsToPlot)
        self.setYRange(-0.05, 1.05)
        #yAxis.setTicks([[[0,'Left '],[1,'Right ']]])
        yAxis.setTicks([[[0,'0'],[0.5,'50'],[1,'100']],
                        [[0.25,'25'],[0.75,'75']]])
        pg.InfiniteLine(pos=0.5, angle=0, pen=pg.mkPen('k'))
        #self.addItem(pg.InfiniteLine(pos=0.5, angle=0, pen=pg.mkPen('k')))
        yAxis.setGrid(20)

    def make_pens(self,points):
        """points should be a list of tuples of the form [ntrials,'colorname']

        Args:
            points:
        """
        pensList = []
        brushesList = []
        for item in points:
            pensList.append(item[0]*[ pg.mkPen(item[1]) ])
            brushesList.append(item[0]*[ pg.mkBrush(item[1]) ])
        self.pens = np.concatenate(pensList)
        self.brushes = np.concatenate(brushesList)

    def update(self,sides=[],sidesLabels={},outcome=[],outcomeLabels={},currentTrial=0):
        """
        Args:
            sides:
            sidesLabels:
            outcome:
            outcomeLabels:
            currentTrial:
        """
        xd = np.tile(range(self.nTrialsToPlot),3)
        validLabels = [outcomeLabels['correct'],outcomeLabels['error']]
        # XFIXME: this should ask if outcome in [someset] (using ismember)
        validTrials = np.zeros(currentTrial,dtype=bool)
        for oneValidLabel in validLabels:
            validTrials[outcome[:currentTrial]==oneValidLabel] = True
        validLeft  = (sides[:currentTrial]==sidesLabels['left'])[validTrials]
        validRight = (sides[:currentTrial]==sidesLabels['right'])[validTrials]


        nValid = np.sum(validTrials) #Maybe just add one every this is called
        #nValidLeft = np.sum(validLeft) #Maybe just add one every this is called
        correct = outcome==self.outcomeIDs['correct'] # SIZE:nTrials
        # XFIXME: the following should not be hardcoded but use sidesLabels
        #leftCorrect = ((sides==0) & correct)[:currentTrial][validTrials]
        #rightCorrect = ((sides==1) & correct)[:currentTrial][validTrials]
        validCorrect = correct[validTrials] # SIZE:nValid

        if len(validTrials) and validTrials[-1]:
            #trialsToAverage = np.arange(max(0,nValid-self.windowSize),nValid)
            trialsToAverage = np.zeros(nValid,dtype=bool) # SIZE:nValid
            trialsToAverage[np.arange(max(0,nValid-self.windowSize),nValid)]=True
            #trialsToAverageLeft = np.arange(max(0,nValid-self.windowSize),nValid)
            self.movingAverageBoth[nValid-1] = np.mean(validCorrect[trialsToAverage])
            if np.any(trialsToAverage&validLeft):
                self.movingAverageLeft[nValid-1] = np.mean(validCorrect[trialsToAverage&validLeft])
            if np.any(trialsToAverage&validRight):
                self.movingAverageRight[nValid-1] = np.mean(validCorrect[trialsToAverage&validRight])
            #print self.movingAverage[:nValid-1]
            #print trialsToAverage&validLeft
            #print self.movingAverageRight
            #print self.movingAverageLeft

            xValues = np.arange(nValid)
            #yAll = self.movingAverageBoth[xValues]
            #self.make_pens([ [len(xMAboth),'k'],
            #                 [len(xMAleft),'c'], [len(xMAright),'m'],])
            #self.mainPlot.setData(x=xValues, y=yAll, pen=self.pens, brush=self.brushes)
            self.mainPlot.setData(x=xValues, y=self.movingAverageBoth[xValues])
            self.perfLeftPlot.setData(x=xValues, y=self.movingAverageLeft[xValues])
            self.perfRightPlot.setData(x=xValues, y=self.movingAverageRight[xValues])
            minTrial = max(0,nValid-self.nTrialsToPlot)
            self.setXRange(minTrial, minTrial+self.nTrialsToPlot)

        '''
        maxPastTrials = (self.nTrialsToPlot*2)//3
        minTrial = max(0,currentTrial-maxPastTrials)
        xPastTrials = np.arange(minTrial,currentTrial)
        xSide = np.arange(currentTrial,minTrial+self.nTrialsToPlot)
        xCorrect = np.flatnonzero(outcome[xPastTrials]==self.outcomeIDs['correct'])+minTrial
        xError = np.flatnonzero(outcome[xPastTrials]==self.outcomeIDs['error'])+minTrial
        xInvalid = np.flatnonzero(outcome[xPastTrials]==self.outcomeIDs['invalid'])+minTrial
        xFree = np.flatnonzero(outcome[xPastTrials]==self.outcomeIDs['free'])+minTrial
        xNoChoice = np.flatnonzero(outcome[xPastTrials]==self.outcomeIDs['nochoice'])+minTrial
        xAfterError = np.flatnonzero(outcome[xPastTrials]==self.outcomeIDs['aftererror'])+minTrial
        xAborted = np.flatnonzero(outcome[xPastTrials]==self.outcomeIDs['aborted'])+minTrial
        xAll = np.concatenate((xSide,xCorrect,xError,xInvalid,xFree,xNoChoice,xAfterError,xAborted))
        yAll = sides[xAll]
        green=(0,212,0)
        gray = 0.75
        pink = (255,192,192)
        self.make_pens([ [len(xSide),'b'], [len(xCorrect),green], [len(xError),'r'],
                         [len(xInvalid),gray], [len(xFree),'c'], [len(xNoChoice),'w'],
                         [len(xAfterError),pink],[len(xAborted),'k']])
        self.mainPlot.setData(x=xAll, y=yAll, pen=self.pens, brush=self.brushes)
        self.setXRange(minTrial, minTrial+self.nTrialsToPlot)
        #print minTrial, minTrial+self.nTrialsToPlot ### DEBUG
        '''

    def sizeHint(self):
        """

        Returns:

        """
        return QtCore.QSize(self.initialSize[0],self.initialSize[1])



if __name__ == "__main__":
    import signal
    signal.signal(signal.SIGINT, signal.SIG_DFL) # Enable Ctrl-C
    import sys

    # -- A workaround to enable re-running the app in ipython after closing --
    app=QtGui.QApplication.instance() # checks if QApplication already exists 
    if not app: # create QApplication if it doesnt exist 
        app = QtGui.QApplication(sys.argv)
    form = QtGui.QDialog()
    form.resize(600,140)
    set_pg_colors(form)

    ntrials = 100
    splot = PerformanceDynamicsPlot(nTrials=20)
    xd=np.arange(ntrials);
    #sides=(xd%3)>1
    #sides = np.random.randint(0,2,ntrials)
    #outcome = np.random.randint(0,4,ntrials)
    sides   = np.array([0,1,0,1,0,1,0,1, 0,1,0,1,0,1,0,1, 0,1,0,1,0,1,0,1, 0,1,0,1,0,1,0,1])
    outcome = np.array([0,1,2,3,0,1,2,3, 0,1,2,3,0,1,2,3, 0,1,2,3,0,1,2,3, 0,1,2,3,0,1,2,3,])
    ###valid = np.random.randint(0,2,ntrials).astype(bool)
    #outcome = np.array([0,0,0,1,1,0,1,1,1,1])
    for currentTrial in range(16):
        splot.update(sides,{'left':0,'right':1},outcome,{'error':0,'correct':1},currentTrial=currentTrial)
    # XFIXME: add outcomeLabels to update()

    layoutMain = QtGui.QHBoxLayout()
    layoutMain.addWidget(splot)
    form.setLayout(layoutMain)
    form.show()
    app.exec_()
    '''
    '''
