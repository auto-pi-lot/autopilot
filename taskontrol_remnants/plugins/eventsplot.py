#!/usr/bin/env python

'''
Plot state matrix events and states as they happen.
'''

__version__ = '0.0.1'
__author__ = 'Santiago Jaramillo <jara@cshl.edu>'
__created__ = '2013-04-06'


from PySide import QtCore 
from PySide import QtGui 
import numpy as np
import pyqtgraph as pg


class EventsPlot(pg.PlotWidget):
    """Plot state matrix events and states as they happen."""
    def __init__(self, parent=None, xlim=[0,10], initialSize=(200,40)):
        """
        Args:
            parent:
            xlim:
            initialSize:
        """
        super(EventsPlot, self).__init__(parent)
        self.initialSize = initialSize

        #self.setFixedHeight(40)
        self.stateRect = list()

        self.pX = 4                  # Origin X
        self.pY = 1                  # Origin Y
        self.pH = 0.5*self.height()  # Plot Height
        self.pW = self.pWidth()      # Plot Width
        self.labelsY = 0.85*self.height()

        self.xLims = xlim
        self.xLen = self.xLims[1]-self.xLims[0]
        self.xTicks = range(self.xLims[0],self.xLims[1])

        self._lastStatesOnset  = []
        self._lastStatesOffset = []
        self._lastStatesColor  = []

        self.statesColor = np.array([])

        # -- Set axis limits --
        self.setXRange(*self.xLims)
        self.setYRange(0,1)
        self.showAxis('left', False)
        self.setLabel('bottom', 'Time', units='s')

    def sizeHint(self):
        return QtCore.QSize(self.initialSize[0],self.initialSize[1])

    def center_in_screen(self):
        qr = self.frameGeometry()
        cp = QtGui.QDesktopWidget().availableGeometry().center()
        qr.moveCenter(cp)
        self.move(qr.topLeft())

    def set_states_color(self,statesColorDict,statesNameToIndex):
        """Set colors for each state.

        statesColorsDict is a dict mapping state names to colors.
        statesNameToIndex is a dict mapping states names to indexes. A valid
        color is a list of 3 elements in the range 0-255

        Args:
            statesColorDict:
            statesNameToIndex:
        """

        self.statesColor = 127*np.ones((len(statesNameToIndex),3))
        for (stateName,color) in statesColorDict.iteritems():
            stateIndex = statesNameToIndex[stateName]
            self.statesColor[stateIndex,:] = color

    '''
    def setStatesColorList(self,newColors):
        ''A valid color is a list of 3 elements in the range 0-255''
        self.statesColor = []
        for color in newColors:
            self.statesColor.append(QtGui.QColor(*color))
    '''

    def update_plot(self,timesAndStates,etime):
        """Updates the plot. This method expects a numpy array where each row is
        of the form [time, state]

        Args:
            timesAndStates:
            etime:
        """
        # -- Find states to plot --
        axLims = self.viewRect().getCoords()
        earliestTime = etime-axLims[2]  #self.xLims[1]
        eventsToInclude = timesAndStates[:,0]>=earliestTime
        if sum(eventsToInclude)>0:
            # XFIXME: Ugly way of adding an extra state (with onset outside range)
            eventsToInclude = np.r_[eventsToInclude[1:],eventsToInclude[0]] | eventsToInclude
            self._lastStatesOnset = etime - timesAndStates[eventsToInclude,0]
            self._lastStatesOnset[0] = self.xLims[1]
            self._lastStatesOffset = np.r_[self._lastStatesOnset[1:],0]
            lastStates = timesAndStates[eventsToInclude,1].astype('int')
            #self._lastStatesColor = self.statesColor[lastStates]
            # XFIXME: there must be a better way!
            self._lastStatesColor = [self.statesColor[s] for s in lastStates]
        # -- Plot states --
        self.clear()
        for oneOnset,oneOffset,oneColor in zip(self._lastStatesOnset,
                                               self._lastStatesOffset,
                                               self._lastStatesColor):
            rect = QtGui.QGraphicsRectItem(QtCore.QRectF(oneOnset, 0, oneOffset-oneOnset, 1))
            #rect.setPen(pg.mkPen(None))
            rect.setPen(pg.mkPen('k'))
            rect.setBrush(pg.mkBrush(oneColor))
            self.addItem(rect)

    def OLD_paintEvent(self, event):
        """
        Args:
            event:
        """
        self.pW = self.pWidth()      # Update plot width
        painter = QtGui.QPainter()
        painter.begin(self)
        painter.setPen(QtCore.Qt.NoPen)
        for oneOnset,oneOffset,oneColor in zip(self._lastStatesOnset,
                                               self._lastStatesOffset,
                                               self._lastStatesColor):
            painter.setBrush(QtGui.QBrush(oneColor))
            (pOnset,pOffset) = map(self.valueToPixel,(oneOnset,oneOffset))
            oneRect = QtCore.QRectF(pOnset,self.pY+1,pOffset-pOnset,self.pH-1)
            painter.drawRect(oneRect)
        self.drawAxis(painter)
        painter.end()


    def pWidth(self):
        """Width of axes in pixels"""
        return self.width()-2*self.pX


    def valueToPixel(self,xval):
        """
        Args:
            xval:
        """
        return (float(xval-self.xLims[0])/self.xLen)*self.pW + self.pX


    def drawAxis(self,painter):
        """
        Args:
            painter:
        """
        painter.setPen(QtGui.QColor(QtCore.Qt.gray))
        painter.setBrush(QtCore.Qt.NoBrush)
        painter.drawRect(self.pX,self.pY,self.pW,self.pH)

        painter.setPen(QtGui.QColor(0,0,0))
        for oneTick in self.xTicks:
            posX = self.valueToPixel(oneTick)
            tickPos = QtCore.QPointF(posX-3,self.labelsY)
            #painter.drawText(tickPos, QtCore.QString(str(oneTick)))
            painter.drawText(tickPos, str(oneTick))


if __name__ == "__main__":

    import sys, signal

    signal.signal(signal.SIGINT, signal.SIG_DFL) # Enable Ctrl-C

    app=QtGui.QApplication.instance() # checks if QApplication already exists 
    if not app: # create QApplication if it doesnt exist 
        app = QtGui.QApplication(sys.argv)
    evplot = EventsPlot(xlim=[-1,5],initialSize=(300,100))
    evplot.center_in_screen()


    statesColorDict = {'wait_for_cpoke': [127,127,255],
                       'play_target':    [255,255,0],
                       'wait_for_apoke': [191,191,255],
                       'reward':         [0,255,0],
                       'punish':         [255,0,0],
                       'ready_next_trial':   [127,127,127]}
    statesNameToIndex = {'wait_for_cpoke': 1, 'play_target': 2,
                       'wait_for_apoke': 3, 'reward': 4,
                       'punish': 5, 'ready_next_trial': 0}
    evplot.set_states_color(statesColorDict,statesNameToIndex)

    eventsList = np.array([[0.1,0],[0.5,1],[2,2],[2.5,0]])
    evplot.update_plot(eventsList, 3)
    evplot.show()
    app.exec_()
