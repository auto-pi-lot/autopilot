"""
I must have gotten distracted while doing this, as reward management is not implemented yet,
rewards are managed by the :meth:`~autopilot.tasks.task.Task.set_reward` method in the :class:`~autopilot.tasks.task.Task` class
in a pretty embarassing division of labor.

Will make a new ``managers`` top-level module for stimulus and reward managers.
"""

from autopilot import prefs
import os


class Reward(object):
    """
    Base reward class
    """

    PARAMS = []
    TYPE = ''

    def __init__(self):
        pass

    def as_dict(self):
        """
        Create dictionary representation::

            {'type': REWARD_TYPE,
             'params' : {'param_1': PARAM_1, ... }
            }

        :return:
        """
        params = {k:getattr(self, k) for k in self.PARAMS}

        return_dict = {'type': self.TYPE}


class Constant_Time(Reward):
    """
    Deliver a reward for a constant time

    Default reward class for solenoids that lack calibration (see :class:`.gui.Calibrate_Water`)
    """
    PARAMS = ['duration']
    TYPE = 'time'


    def __init__(self, duration = 20):
        """
        Args:
            duration (int): duration of reward in ms
        """
        self.duration = duration


class Constant_Volume(Reward):
    """
    Deliver a constant volume of reward.

    Requires a solenoid to be calibrated, see :class:`~.gui.Calibrate_Water`
    """

    PARAMS = ['volume']
    TYPE = 'volume'


    def __init__(self, volume = .1):
        """
        Args:
            volume (float): volume of reward in mL
        """
        self.volume = volume

        # try to find calibration
        #cal_path = 0

    def compute_duration(self):
        pass





REWARD_LIST = {
    'constant_time': Constant_Time,
    'constant_volume': Constant_Volume
}