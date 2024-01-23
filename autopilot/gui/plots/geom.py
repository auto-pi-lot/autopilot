import numpy as np
import pandas as pd
import pyqtgraph as pg
from PySide6 import QtWidgets


class Point(pg.PlotDataItem):
    """
    A simple point.

    Attributes:
        brush (:class:`QtWidgets.QBrush`)
        pen (:class:`QtWidgets.QPen`)
    """

    def __init__(self, color=(0,0,0), size=5, **kwargs):
        """
        Args:
            color (tuple): RGB color of points
            size (int): width in px.
        """
        super(Point, self).__init__()

        self.continuous = False
        if 'continuous' in kwargs.keys():
            self.continuous = kwargs['continuous']

        self.brush = pg.mkBrush(color)
        self.pen   = pg.mkPen(color, width=size)
        self.size  = size

    def update(self, data):
        """
        Args:
            data (:class:`numpy.ndarray`): an x_width x 2 array where
                column 0 is trial number and column 1 is the value,
                where value can be "L", "C", "R" or a float.
        """
        # data should come in as an n x 2 array,
        # 0th column - trial number (x), 1st - (y) value

        data[data=="R"] = 1
        data[data=="C"] = 0.5
        data[data=="L"] = 0
        data = data.astype(np.float)

        self.scatter.setData(x=data[...,0], y=data[...,1], size=self.size,
                             brush=self.brush, symbol='o', pen=self.pen)


class Line(pg.PlotDataItem):
    """
    A simple line
    """

    def __init__(self, color=(0,0,0), size=1, **kwargs):
        super(Line, self).__init__(**kwargs)

        self.brush = pg.mkBrush(color)
        self.pen = pg.mkPen(color, width=size)
        self.size = size

    def update(self, data):
        data[data=="R"] = 1
        data[data=="L"] = 0
        data[data=="C"] = 0.5
        data = data.astype(np.float)

        self.curve.setData(data[...,0], data[...,1])


class Segment(pg.PlotDataItem):
    """
    A line segment that draws from 0.5 to some endpoint.
    """
    def __init__(self, **kwargs):
        # type: () -> None
        super(Segment, self).__init__(**kwargs)

    def update(self, data):
        """
        data is doubled and then every other value is set to 0.5,
        then :meth:`~pyqtgraph.PlotDataItem.curve.setData` is used with
        `connect='pairs'` to make line segments.

        Args:
            data (:class:`numpy.ndarray`): an x_width x 2 array where
                column 0 is trial number and column 1 is the value,
                where value can be "L", "C", "R" or a float.
        """
        # data should come in as an n x 2 array,
        # 0th column - trial number (x), 1st - (y) value
        data[data=="R"] = 1
        data[data=="L"] = 0
        data[data=="C"] = 0.5
        data = data.astype(np.float)

        xs = np.repeat(data[...,0],2)
        ys = np.repeat(data[...,1],2)
        ys[::2] = 0.5

        self.curve.setData(xs, ys, connect='pairs', pen='k')


class Roll_Mean(pg.PlotDataItem):
    """
    Shaded area underneath a rolling average.

    Typically used as a rolling mean of corrects, so area above and below 0.5 is drawn.
    """
    def __init__(self, winsize=10, **kwargs):
        # type: (int) -> None
        """
        Args:
            winsize (int): number of trials in the past to take a rolling mean of
        """
        super(Roll_Mean, self).__init__()

        self.winsize = winsize

        self.setFillLevel(0.5)

        self.series = pd.Series()

        self.brush = pg.mkBrush((0,0,0,100))
        self.setBrush(self.brush)

    def update(self, data):
        """
        Args:
            data (:class:`numpy.ndarray`): an x_width x 2 array where
                column 0 is trial number and column 1 is the value.
        """
        # data should come in as an n x 2 array,
        # 0th column - trial number (x), 1st - (y) value
        data = data.astype(np.float)

        self.series = pd.Series(data[...,1])
        ys = self.series.rolling(self.winsize, min_periods=0).mean().to_numpy()

        #print(ys)

        self.curve.setData(data[...,0], ys, fillLevel=0.5)


class Shaded(pg.PlotDataItem):
    """
    Shaded area for a continuous plot
    """

    def __init__(self, **kwargs):
        super(Shaded, self).__init__()

        #self.dur = float(dur) # duration of time to display points in seconds
        self.setFillLevel(0)
        self.series = pd.Series()

        self.getBoundingParents()


        self.brush = pg.mkBrush((0,0,0,100))
        self.setBrush(self.brush)

        self.max_num = 0


    def update(self, data):
        """
        Args:
            data (:class:`numpy.ndarray`): an x_width x 2 array where
                column 0 is time and column 1 is the value.
        """
        # data should come in as an n x 2 array,
        # 0th column - trial number (x), 1st - (y) value
        data = data.astype(np.float)

        self.max_num = float(np.abs(np.max(data[:,1])))

        if self.max_num > 1.0:
            data[:,1] = (data[:,1]/(self.max_num*2.0))+0.5
        #print(ys)

        self.curve.setData(data[...,0], data[...,1], fillLevel=0)


class HLine(QtWidgets.QFrame):
    """
    A Horizontal line.
    """
    def __init__(self):
        # type: () -> None
        super(HLine, self).__init__()
        self.setFrameShape(QtWidgets.QFrame.HLine)
        self.setFrameShadow(QtWidgets.QFrame.Sunken)


PLOT_LIST = {
    'point': Point,
    'segment': Segment,
    'rollmean': Roll_Mean,
    'shaded': Shaded,
    'line': Line
    # 'highlight':Highlight
}
"""
A dictionary connecting plot keys to objects.

TODO:
    Just reference the plot objects.
"""