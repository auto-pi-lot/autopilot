from time import time

import numpy as np
from PySide6 import QtWidgets, QtCore


class Timer(QtWidgets.QLabel):
    """
    A simple timer that counts... time...

    Uses a :class:`QtCore.QTimer` connected to :meth:`.Timer.update_time` .
    """
    def __init__(self):
        # type: () -> None
        super(Timer, self).__init__()

        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self.update_time)

        self.start_time = None

    def start_timer(self, update_interval=1000):
        """
        Args:
            update_interval (float): How often (in ms) the timer should be updated.
        """
        self.start_time = time()
        self.timer.start(update_interval)

    def stop_timer(self):
        """
        you can read the sign ya punk
        """
        self.timer.stop()
        self.setText("")

    def update_time(self):
        """
        Called every (update_interval) milliseconds to set the text of the timer.

        """
        secs_elapsed = int(np.floor(time()-self.start_time))
        self.setText("{:02d}:{:02d}:{:02d}".format(int(secs_elapsed/3600), int((secs_elapsed/60))%60, secs_elapsed%60))