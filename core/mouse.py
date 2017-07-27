#!/usr/bin/python2.7

'''
Base Mouse Class.
Methods for storing data like mass, DOB, etc. as well as assigned protocols and trial data
'''

#from taskontrol.settings import rpisettings as rpiset
#from taskontrol import tasks
import os
#import h5py
import tables
from tables.nodes import filenode
import datetime
from time import time
from importlib import import_module
import json
import numpy as np
import warnings

class Mouse:
    """Mouse object for managing protocol, parameters, and data"""
    # hdf5 structure is split into two groups, mouse info and trial data.

    def __init__(self, name, dir='/usr/rpilot/data', new=0, biography=None):
        #TODO: Pass dir from prefs
        self.name = str(name)
        self.file = os.path.join(dir, name + '.h5')
        if new or not os.path.isfile(self.file):
            self.new_mouse_file(biography)
        else:
            # .new_mouse() opens the file
            self.h5f    = tables.open_file(self.file, 'r+')
        # TODO figure out pytables swmr mode

        # Make shortcuts for direct assignation
        self.info = self.h5f.root.info._v_attrs
        self.data = self.h5f.root.data
        self.history = self.h5f.root.history.history

        # If mouse has a protocol, load it to a dict
        if "/current" in self.h5f:
            current_node = filenode.open_node(self.h5f.root.current)
            protocol_string = current_node.readall()
            self.current = json.loads(protocol_string)
            self.step = int(current_node.attrs['step'])


    def new_mouse_file(self, biography):
        # If a file already exists, we open it for appending so we don't lose data.
        # For now we are assuming that the existing file has the basic structure,
        # but that's probably a bad assumption for full reliability
        if os.path.isfile(self.file):
            self.h5f = tables.open_file(self.file, mode='a')
        else:
            self.h5f = tables.open_file(self.file, mode='w')

            # Make Basic file structure
            self.h5f.create_group("/","data","Trial Record Data")
            self.h5f.create_group("/","info","Biographical Info")
            history_group = self.h5f.create_group("/","history","History")

            # When a whole protocol is changed, we stash the old protocol as a filenode in the past_protocols group
            self.h5f.create_group("/history", "past_protocols",'Past Protocol Files')

            # Also canonical to the basic file structure is the 'current' filenode which stores the current protocol,
            # but since we want to be able to tell that a protocol hasn't been assigned yet we don't instantiate it here
            # See http://www.pytables.org/usersguide/filenode.html
            # filenode.new_node(self.h5f, where="/", name="current")

            # We keep track of changes to parameters, promotions, etc. in the history table
            self.h5f.create_table(history_group, 'history', self.History_Table, "Change History")


        # Save biographical information as node attributes
        for k, v in biography.items():
            self.h5f.root.info._v_attrs[k] = v

        self.h5f.flush()

    def update_biography(self, params):
        for k, v in params.items():
            self.h5f.root.info._v_attrs[k] = v

    def update_history(self, type, name, value):
        # Make sure the updates are written to the mouse file
        if type == 'param':
            self.current[self.step][name] = value
            self.flush_current()
        if type == 'step':
            self.step = int(value)
            self.h5f.root.current.attrs['step'] = self.step
            self.flush_current()

        # Check that we're all strings in here
        if not isinstance(type, basestring):
            type = str(type)
        if not isinstance(name, basestring):
            name = str(name)
        if not isinstance(value, basestring):
            value = str(value)

        history_row = self.h5f.root.history.history.row

        history_row['time'] = self.get_timestamp(string=True)
        history_row['type'] = type
        history_row['name'] = name
        history_row['value'] = value
        history_row.append()

    def update_params(self, param, value):
        pass

    def assign_protocol(self, protocol, step=0):
        # Protocol will be passed as a .json filename in prefs['PROTOCOLDIR']
        # The full filename is passed because we don't want to assume knowledge of prefs in the mouse data model

        # Check if there is an existing protocol, archive it if there is.
        if "/current" in self.h5f:
            # We store it as the date that it was changed followed by its name if it has one
            current_node = filenode.open_node(self.h5f.root.current)
            old_protocol = current_node.readall()

            archive_name = datetime.datetime.now().strftime('%y%m%d-%H%M')

            if 'protocol_name' in self.h5f.root.current.attrs._v_attrnames:
                protocol_name = self.h5f.root.current.attrs._v_attrnames['protocol_name']
                archive_name = '_'.join([archive_name, protocol_name])

            archive_node = filenode.new_node(self.h5f, where='/history/past_protocols', name=archive_name)
            archive_node.write(old_protocol)

            self.h5f.remove_node('/current')

        # Assign new protocol
        # Load protocol to dict
        with open(protocol) as protocol_file:
            self.protocol = json.load(protocol_file)

        # Make filenode and save as string
        current_node = filenode.new_node(self.h5f, where='/', name='current')
        current_node.write(json.dumps(self.protocol))

        # Set name and step
        # Strip off path and extension to get the protocol name
        protocol_name = os.path.splitext(protocol)[0].split(os.sep)[-1]
        current_node.attrs['protocol_name'] = protocol_name
        current_node.attrs['step'] = step

        # Update history (flushes the file so we don't have to here)
        self.update_history('protocol', protocol_name, step)

    def flush_current(self):
        step = self.h5f.root.current.attrs['step']
        protocol_name = self.h5f.root.current.attrs['protocol_name']
        self.h5f.remove_node('/current')
        current_node = filenode.new_node(self.h5f, where='/', name='current')
        current_node.write(json.dumps(self.current))
        current_node.attrs['step'] = step
        current_node.attrs['protocol_name'] = protocol_name
        self.h5f.flush()



    def load_protocol(self,step_number=-1):
        # If no step_number passed, load the last step assigned
        # TODO: dicts are mutable, so last number won't necessarily be last assigned. Fix when multi-step protocols made - use odicts
        last_assigned_task   = self.data._v_children.keys()[step_number]
        self.h5trial_records = self.data._f_get_child(last_assigned_task)
        self.trial_row       = self.h5trial_records.row
        self.task_type       = self.h5trial_records.attrs.task_type
        self.task_params     = self.h5trial_records.attrs.params
        self.param_template  = self.h5trial_records.attrs.param_template
        self.task_data_list  = self.h5trial_records.attrs.data_list
        # TODO Check if template has changed since assign
        # Import the task class from its module & make
        template_module = import_module('taskontrol.tasks.{}'.format(self.task_type))
        task_class = getattr(template_module,template_module.TASK)
        self.task = task_class(**self.task_params)

    def receive_sounds(self,sounds,sound_lookup):
        # To be passed by RPilot after initing the Mouse
        # We do this here because the Mouse is in charge of its records, and also has access to its task.
        # TODO some error checking, ie. do we have a task already loaded, etc.
        self.task.sounds = sounds
        self.task.sound_lookup = sound_lookup
        # Update records with lookup table. Append date of lookup if conflicts
        #if not set(sound_lookup.items()).issubset(set(self.h5trial_records.attrs.params['sounds'])):
            # TODO: error checking here, need to keep record if param changes, keep record. This is a more general problem so not implementing yet
            # pass

    def save_trial(self,data):
        # TODO Error checking: does the data dict contain all the columns of the table?
        # TODO Error checking: handling basic type mismatches

        for k,v in data.items():
            self.trial_row[k] = v
        self.trial_row.append()
        self.h5trial_records.flush() # FIXME: pytables might do a decent job of flushing when buffer's full - we might gain fluidity by letting it handle flushing.

    def put_away(self):
        self.h5f.flush()
        self.h5f.close()

    def get_timestamp(self, string=False):
        # Timestamps have two different applications, and thus two different formats:
        # coarse timestamps that should be human-readable
        # fine timestamps for data analysis that don't need to be
        if string:
            return datetime.datetime.now().strftime('%y%m%d-%H%M')
        else:
            return time()

    class History_Table(tables.IsDescription):
        # Class to describe parameter and protocol change history
        # Columns:
            # Timestamp
            # Type of change - protocol, parameter, step
            # Name - Which parameter was changed, name of protocol, manual vs. graduation step change
            # Value - What was the parameter/protocol/etc. changed to, step if protocol.
        time = tables.StringCol(64)
        type = tables.StringCol(64)
        name = tables.StringCol(64)
        value = tables.StringCol(64)


############################################################################################
# Utility functions and classes


def flatten_dict(d, parent_key=''):
    """
    h5py has trouble with nested dicts which are likely to be common w/ complex params. Flatten a dict s.t.:
        {
    Lifted from : http://stackoverflow.com/questions/6027558/flatten-nested-python-dictionaries-compressing-keys/6043835#6043835
    """
    items = []
    for k, v in d.items():
        try:
            if type(v) == type([]):
                for n, l in enumerate(v):
                    items.extend(flatten_dict(l, '%s%s.%s.' % (parent_key, k, n)).items())
            else:
                items.extend(flatten_dict(v, '%s%s.' % (parent_key, k)).items())
        except AttributeError:
            items.append(('%s%s' % (parent_key, k), v))
    return dict(items)


def expand_dict(d):
    """
    Recover flattened dicts
    """
    items = dict()
    for k,v in d.items():
        if len(k.split('.'))>1:
            current_level = items
            for i in k.split('.')[:-1]: #all but the last entry
                try:
                    # If we come across an integer, we make a list of dictionaries
                    i_int = int(i)
                    if not isinstance(current_level[j],list):
                        current_level[j] = list() # get the last entry and make it a list
                    if i_int >= len(current_level[j]): # If we haven't populated this part of the list yet, fill.
                        current_level[j].extend(None for _ in range(len(current_level[j]),i_int+1))
                    if not isinstance(current_level[j][i_int],dict):
                        current_level[j][i_int] = dict()
                    current_level = current_level[j][i_int]
                except ValueError:
                    # Otherwise, we make a sub-dictionary
                    try:
                        current_level = current_level[j]
                    except:
                        pass
                    if i not in current_level:
                        current_level[i] = {}
                    j = i #save this entry so we can enter it next round if it's not a list
                    # If the last entry, enter the dict
                    if i == k.split('.')[-2]:
                        current_level = current_level[i]
            current_level[k.split('.')[-1]] = v
        else:
            items[k] = v
    return items

class Biography(tables.IsDescription):
    '''
    pytables descriptor class for biographical information.
    '''
    name = tables.StringCol(32)
    start_date = tables.StringCol(10)
    baseline_mass = tables.Float32Col()
    minimum_mass = tables.Float32Col()
    box = tables.Int32Col()

class DataTest(tables.IsDescription):
    test = tables.StringCol(32)
