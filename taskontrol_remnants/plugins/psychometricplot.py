#!/usr/bin/env python

'''
Plugin to show the average fraction of correct trials for each value of a parameter.
'''


__version__ = '0.1'
__author__ = 'Santiago Jaramillo <sjara@uoregon.edu>'
__created__ = '2014-08-07'


from PySide import QtCore 
from PySide import QtGui 
import numpy as np
import pyqtgraph as pg


def set_pg_colors(form):
    '''Set default BG and FG color for pyqtgraph plots.'''
    bgColorRGBA = form.palette().color(QtGui.QPalette.ColorRole.Window)
    fgColorRGBA = form.palette().color(QtGui.QPalette.ColorRole.WindowText)
    pg.setConfigOption('background', bgColorRGBA)
    pg.setConfigOption('foreground', fgColorRGBA)
    pg.setConfigOptions(antialias=True)  ## this will be expensive for the local plot
    #pg.setConfigOptions(antialias=False)  ##


class PsychometricPlot(pg.PlotWidget):
    '''
    Plot average fraction of correct trials for each value of a parameter.
    '''
    def __init__(self, parent=None, widgetSize=(200,200),xlabel='',ylabel=''):
        if parent is not None:
            set_pg_colors(parent)
        super(PsychometricPlot, self).__init__(parent)

        self.xLabel = xlabel
        self.yLabel = ylabel

        self.initialSize = widgetSize
        self.mainPlot = pg.ScatterPlotItem(size=8, symbol='o', pxMode=True,
                                           pen='k', brush='k')
        self.addItem(self.mainPlot)
        # -- Graphical adjustments --
        yAxis = self.getAxis('left')
        self.setLabel('left', self.yLabel ,units='%')
        self.setLabel('bottom', self.xLabel)
        #self.setXRange(0, )
        self.setYRange(-5, 100)
        yAxis.setTicks([[[0,'0'],[50,'50'],[100,'100']],
                        [[25,'25'],[75,'75']]])
        #self.addItem(pg.InfiniteLine(pos=50, angle=0, pen=pg.mkPen('k')))
        yAxis.setGrid(20)

    def update(self,xValues,yValues,xlim=None):
        self.mainPlot.setData(x=xValues, y=yValues)
        if xlim is not None:
            self.setXRange(*xlim)
        pass

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
    #form.resize(200,200)
    set_pg_colors(form)
    
    psyplot = PsychometricPlot(xlabel='Frequency',ylabel='Rightward choice')
    psyplot.update([1,2,3,4,5,6],[0,10,30,70,90,100],xlim=[0,7])

    layoutMain = QtGui.QHBoxLayout()
    layoutMain.addWidget(psyplot)
    form.setLayout(layoutMain)
    form.show()
    app.exec_()
