import numpy as np
from PySide import QtCore
import json
from subprocess import call

def dict_from_HDF5(dictGroup):
    newDict={}
    for k,v in dictGroup.iteritems():
        newDict[k]=v[()]
        newDict[v[()]]=k
    return newDict


# Stuff to send signals to the main QT thread from spawned message threads
# https://stackoverflow.com/a/12127115

class InvokeEvent(QtCore.QEvent):
    EVENT_TYPE = QtCore.QEvent.Type(QtCore.QEvent.registerEventType())

    def __init__(self, fn, *args, **kwargs):
        QtCore.QEvent.__init__(self, InvokeEvent.EVENT_TYPE)
        self.fn = fn
        self.args = args
        self.kwargs = kwargs


class Invoker(QtCore.QObject):
    def event(self, event):
        event.fn(*event.args, **event.kwargs)
        return True


def get_prefs(prefs_fn = '/usr/rpilot/prefs.json'):
    # convenience function to get prefs

    with open(prefs_fn) as prefs_file:
        prefs = json.load(prefs_file)

    return prefs

def update_pis(github=True, apt=False, pilot_select = None, prefs_fn = None):
    # update github, or apt?
    # should limit pilots or use all?
    # load prefs from default location or use different?
    if prefs_fn is None:
        prefs = get_prefs()
    else:
        prefs = get_prefs(prefs_fn)

    # get ips from pilot db
    with open(prefs['PILOT_DB'], 'r') as pilot_db:
        pilots = json.load(pilot_db)

    # if we were passed a list of pilots to subset then do it
    if pilot_select is not None:
        pilots = {k: v for k, v in pilots.items() if k in pilot_select }

    if github is True:
        ips = ['pi@'+v['ip'] for k,v in pilots.items()]
        ip_string = " ".join(ips)
        call('parallel-ssh', '-H', ip_string, 'git --git-dir=/home/pi/git/RPilot/.git pull')

def dummy():
    # testing if update pi works
    pass






