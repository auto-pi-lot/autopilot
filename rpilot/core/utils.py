# import numpy as np
from rpilot import prefs
if prefs.AGENT in ("terminal", "docs"):
    from PySide import QtCore
import json
import pandas as pd
from scipy.stats import linregress
# from subprocess import call
from threading import Thread
import os

class Param(object):
    """
    In the future, we will implement a coherent Parameter management system

    Warning:
        Not Implemented.
    """
    # Class to hold and verify task and gui parameters
    tag = None # human-readable description of parameter
    type = None # string that describes the type of input or param

    # possible types
    types = ['int', 'check', 'list']

    def __init__(self, **kwargs):
        """
        Args:
            **kwargs:
        """
        for k, v in kwargs.items():
            setattr(self, k, v)

    # enable dictionary-like behavior
    def __getitem__(self, key):
        """
        Args:
            key:
        """
        return self.__dict__[key]

    def __setitem__(self, key, value):
        """
        Args:
            key:
            value:
        """
        self.__dict__[key] = value

    def __delitem__(self, key):
        """
        Args:
            key:
        """
        del self.__dict__[key]

    def __contains__(self, key):
        """
        Args:
            key:
        """
        return key in self.__dict__

    def __len__(self):
        return len(self.__dict__)

    # def validate(self):
    #     if all([self.id, self.to, self.sender, self.key]):
    #         return True
    #     else:
    #         return False




if prefs.AGENT in ["terminal", "docs"]:
    class InvokeEvent(QtCore.QEvent):
        """
        Sends signals to the main QT thread from spawned message threads

        See `stackoverflow <https://stackoverflow.com/a/12127115>`_
        """

        EVENT_TYPE = QtCore.QEvent.Type(QtCore.QEvent.registerEventType())

        def __init__(self, fn, *args, **kwargs):
            # type: (function, object, object) -> None
            """
            Accepts a function, its args and kwargs and wraps them as a
            :class:`QtCore.QEvent`

            """
            QtCore.QEvent.__init__(self, InvokeEvent.EVENT_TYPE)
            self.fn = fn
            self.args = args
            self.kwargs = kwargs


    class Invoker(QtCore.QObject):
        """
        Wrapper that calls an evoked event made by :class:`.InvokeEvent`
        """
        def event(self, event):
            """
            Args:
                event:
            """
            event.fn(*event.args, **event.kwargs)
            return True


class ReturnThread(Thread):
    """
    Thread whose .join() method returns the value from the function
    thx to https://stackoverflow.com/a/6894023
    """
    def __init__(self, group=None, target=None, name=None,
                 args=(), kwargs={}, Verbose=None):
        Thread.__init__(self, group, target, name, args, kwargs, Verbose)
        self._return = None
    def run(self):
        if self._Thread__target is not None:
            self._return = self._Thread__target(*self._Thread__args,
                                                **self._Thread__kwargs)
    def join(self, timeout=None):
        Thread.join(self, timeout)

        return self._return

def compute_calibration(path=None, calibration=None, do_return=False):


    if not calibration:
        # if we weren't given calibration results, load them
        if path:
            open_fn = path
        else:
            open_fn = os.path.join(prefs.BASEDIR, "port_calibration.json")

        with open(open_fn, 'r') as open_f:
            calibration = json.load(open_f)

    luts = {}
    for port, samples in calibration.items():
        sample_df = pd.DataFrame(samples)
        # TODO: Filter for only most recent timestamps

        # volumes are saved in mL because of how they are measured, durations are stored in ms
        # but reward volumes are typically in the uL range, so we make the conversion
        # by multiplying by 1000
        line_fit = linregress((sample_df['vol'] / sample_df['n_clicks']) * 1000., sample_df['dur'])
        luts[port] = {'intercept': line_fit.intercept,
                      'slope': line_fit.slope}

    # write to file, overwriting any previous
    if do_return:
        return luts

    else:
        # do write
        lut_fn = os.path.join(prefs.BASEDIR, 'port_calibration_fit.json')
        with open(lut_fn, 'w') as lutf:
            json.dump(luts, lutf)



#
# def update_pis(github=True, apt=False, pilot_select = None, prefs_fn = None):
#     """
#     Args:
#         github:
#         apt:
#         pilot_select:
#         prefs_fn:
#     """
#     # update github, or apt?
#     # should limit pilots or use all?
#     # load prefs from default location or use different?
#     if prefs_fn is None:
#         prefs = get_prefs()
#     else:
#         prefs = get_prefs(prefs_fn)
#
#     # get ips from pilot db
#     with open(prefs['PILOT_DB'], 'r') as pilot_db:
#         pilots = json.load(pilot_db)
#
#     # if we were passed a list of pilots to subset then do it
#     if pilot_select is not None:
#         pilots = {k: v for k, v in pilots.items() if k in pilot_select }
#
#     if github is True:
#         ips = ['pi@'+v['ip'] for k,v in pilots.items()]
#         ip_string = " ".join(ips)
#         call('parallel-ssh', '-H', ip_string, 'git --git-dir=/home/pi/git/RPilot/.git pull')







