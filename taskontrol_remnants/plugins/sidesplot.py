#!/usr/bin/env python

'''
Plugin to show the correct choice on each trial and the outcome (reward/punishment)
'''


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

class SidesPlot(pg.PlotWidget):
    """FROM MATLAB: CurrentTrial, SideList, HitHistory, TrialType)"""
    def __init__(self, parent=None, widgetSize=(200,100),nTrials=100):

        """
        Args:
            parent:
            widgetSize:
            nTrials:
        """
        super(SidesPlot, self).__init__(parent)
        self.initialSize = widgetSize

        self.nTrialsToPlot = nTrials
        self.trialsToPlot = np.arange(self.nTrialsToPlot)

        self.mainPlot = pg.ScatterPlotItem(size=4, symbol='o', pxMode=True)
        self.addItem(self.mainPlot)

        self.outcomeIDs = {'correct':1,'error':0,'invalid':2,'free':3,'nochoice':4,'aftererror':5,'aborted':6} 
        # XFIXME: This should come from somewhere else (to be consisten with the rest)

        # -- Graphical adjustments --
        yAxis = self.getAxis('left')
        #self.setLabel('left', 'Reward\nport') #units='xxx'
        self.setLabel('bottom', 'Trial')
        self.setXRange(0, self.nTrialsToPlot)
        self.setYRange(-0.5, 1.5)
        yAxis.setTicks([[[0,'Left '],[1,'Right ']]])


        '''
        hiddenX = -1*np.ones(self.nTrialsToPlot)
        hiddenY = np.zeros(self.nTrialsToPlot)
        self.mainPlot.addPoints(x=hiddenX,y=hiddenY,
                                pen=self.nTrialsToPlot*[pg.mkPen('b')],
                                brush=self.nTrialsToPlot*[pg.mkBrush('b')])
        self.mainPlot.addPoints(x=hiddenX,y=hiddenY,
                                pen=self.nTrialsToPlot*[pg.mkPen('g')],
                                brush=self.nTrialsToPlot*[pg.mkBrush('g')])
        '''
        #self.mainPlot.addPoints(x=hiddenX,y=hiddenY,
        #                        pen=nTrialsToPlot*[pg.mkPen('r')],
        #                        brush=nTrialsToPlot*[pg.mkBrush('r')])
        

    def make_pens(self,points):
        """points should be a list of tuples of the form [ntrials,'colorname']

        Args:
            points:
        """
        '''
        self.penSide = self.nTrialsToPlot*[pg.mkPen('b')]
        self.brushSide = self.nTrialsToPlot*[pg.mkBrush('b')]
        self.penCorrect = self.nTrialsToPlot*[pg.mkPen('g')]
        self.brushCorrect = self.nTrialsToPlot*[pg.mkBrush('g')]
        self.penError = self.nTrialsToPlot*[pg.mkPen('r')]
        self.brushError = self.nTrialsToPlot*[pg.mkBrush('r')]
        self.brushes = np.concatenate([self.brushSide,self.brushCorrect,self.brushError])
        '''
        pensList = []
        brushesList = []
        for item in points:
            pensList.append(item[0]*[ pg.mkPen(item[1]) ])
            brushesList.append(item[0]*[ pg.mkBrush(item[1]) ])
        self.pens = np.concatenate(pensList)
        self.brushes = np.concatenate(brushesList)

    def update(self,sides=[],outcome=[],currentTrial=0):
        """
        Args:
            sides:
            outcome:
            currentTrial:
        """
        xd = np.tile(range(self.nTrialsToPlot),3)
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

    def sizeHint(self):
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

    ntrials = 1000
    splot = SidesPlot(nTrials=50)
    xd=np.arange(ntrials);
    #sides=(xd%3)>1
    sides = np.random.randint(0,2,ntrials)
    outcome = np.random.randint(0,4,ntrials)
    #outcome = np.array([0,0,0,1,1,0,1,1,1,1])
    splot.update(sides,outcome,currentTrial=90)
    layoutMain = QtGui.QHBoxLayout()
    layoutMain.addWidget(splot)
    form.setLayout(layoutMain)
    form.show()
    app.exec_()
