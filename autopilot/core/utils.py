# import numpy as np
from autopilot import prefs
# if prefs.AGENT in ("TERMINAL", "DOCS"):
HAVE_PYSIDE = False
try:
    from PySide2 import QtCore
    HAVE_PYSIDE = True
except ImportError:
    pass

import json
import pandas as pd
from scipy.stats import linregress
# from subprocess import call
from threading import Thread
import os
import numpy as np

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
    types = ['int', 'bool', 'list']

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




if HAVE_PYSIDE:
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

def list_subjects(pilot_db=None):
    """
    Given a dictionary of a pilot_db, return the subjects that are in it.

    Args:
        pilot_db (dict): a pilot_db. if None tried to load pilot_db with :method:`.load_pilotdb`

    Returns:
        subjects (list): a list of currently active subjects

    """

    if pilot_db is None:
        pilot_db = load_pilotdb()

    subjects = []
    for pilot, values in pilot_db.items():
        if 'subjects' in values.keys():
            subjects.extend(values['subjects'])

    return subjects

def load_pilotdb(file_name=None, reverse=False):
    """
    Try to load the file_db

    Args:
        reverse:
        file_name:

    Returns:

    """

    if file_name is None:
        file_name = '/usr/autopilot/pilot_db.json'

    with open(file_name) as pilot_file:
        pilot_db = json.load(pilot_file)

    if reverse:
        # simplify pilot db
        pilot_db = {k: v['subjects'] for k, v in pilot_db.items()}
        pilot_dict = {}
        for pilot, subjectlist in pilot_db.items():
            for ms in subjectlist:
                pilot_dict[ms] = pilot
        pilot_db = pilot_dict

    return pilot_db

def coerce_discrete(df, col, mapping={'L':0, 'R':1}):
    """
    Coerce a discrete/string column of a pandas dataframe into numeric values

    Default is to map 'L' to 0 and 'R' to 1 as in the case of Left/Right 2AFC tasks

    Args:
        df (:class:`pandas.DataFrame`) : dataframe with the column to transform
        col (str):  name of column
        mapping (dict): mapping of strings to numbers

    Returns:
        df (:class:`pandas.DataFrame`) : transformed dataframe

    """

    for key, val in mapping.items():
        df.loc[df[col]==key,col] = val

    # if blanks, warn and remove
    if '' in df[col].unique():
        n_blanks = sum(df[col]=='')
        Warning('{} blank rows detected, removing.'.format(n_blanks))
        df.drop(df.index[df[col]==''], axis=0, inplace=True)

    df = df.astype({col:float})
    return df


def find_recursive(key, dictionary):
    """
    Find all instances of a key in a dictionary, recursively.

    Args:
        key:
        dictionary:

    Returns:
        list
    """
    for k, v in dictionary.iteritems():
        if k == key:
            yield v
        elif isinstance(v, dict):
            for result in find_recursive(key, v):
                yield result
        elif isinstance(v, list):
            for d in v:
                for result in find_recursive(key, d):
                    yield result



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
#         call('parallel-ssh', '-H', ip_string, 'git --git-dir=/home/pi/git/autopilot/.git pull')







