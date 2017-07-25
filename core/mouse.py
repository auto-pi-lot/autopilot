#!/usr/bin/python2.7

'''
Base Mouse Class.
Methods for storing data like mass, DOB, etc. as well as assigned protocols and trial data
'''

#from taskontrol.settings import rpisettings as rpiset
#from taskontrol import templates
import os
#import h5py
import tables
import datetime
from importlib import import_module
import json
import numpy as np
import warnings

class Mouse:
    """Mouse object for managing protocol, parameters, and data"""
    # hdf5 structure is split into two groups, mouse info and trial data.

    def __init__(self, name, dir='/usr/rpilot/data', new=0, biography=None, protocol=None):
        #TODO: Pass dir from prefs
        self.name = str(name)
        self.file = os.path.join(dir, name + '.h5')
        if new or not os.path.isfile(self.file):
            print("\nNo file detected or flagged as new.")
            self.new_mouse_file(biography, protocol)
        else:
            # .new_mouse() opens the file
            self.h5f    = tables.open_file(self.file, 'r+')
        # TODO figure out pytables swmr mode
        self.h5info = self.h5f.root.info._v_attrs  #TODO: Check if can directly assign to self.h5info
        self.h5data = self.h5f.root.data

        # TODO: Check that self.h5info imports as a dict, if not, do so

        # Load Task if Exists
        # TODO make this more robust for multiple tasks - saving position, etc.
        self.task = None
        # if self.h5data._v_children.keys():
        #     self.load_protocol()

    def new_mouse_file(self, biography, protocol):
        if os.path.isfile(self.file):
            overw = str(raw_input("\nMouse already has file, overwrite and make new file? (y/n)\n   >>"))
            if overw == 'y':
                self.h5f = tables.open_file(rpiset.PI_DATA_DIR + self.name + '.hdf5', mode='w')
            elif overw == 'n':
                self.h5f = tables.open_file(rpiset.PI_DATA_DIR + self.name + '.hdf5', mode='a')
                return
            else:
                return
        else:
            print("\nNo file found, making a new file.")
            print(self.file)
            self.h5f = tables.open_file(self.file, mode='w')
            # TODO ask if user wants to redefine all params or just set new protocol.

        # Basic file structure
        self.h5f.create_group("/","data","Trial Record Data")
        self.h5f.create_group("/","info","Biographical Info")

        for k, v in biography.items():
            self.h5f.root.info._v_attrs[k] = v

        # self.assign_protocol(protocol=protocol)



        #
        # # TODO when terminal built, have terminal stash what types of biographical information we want/allow new fields to be defined.
        # # Basic info about the mouse
        # self.info               = dict()
        # self.info['name']       = self.name
        # self.info['start_date'] = datetime.date.today().isoformat()
        #
        # try:
        #     self.info['baseline_mass'] = float(raw_input("\nWhat is {}'s baseline mass?\n    >".format(self.name)))
        #     self.info['minimum_mass']  = float(raw_input("\nAnd what is {}'s minimum mass? (eg. 80% of baseline?)\n    >".format(self.name)))
        #     self.info['box']           = int(raw_input("\nWhat box will {} be run in?\n    >".format(self.name)))
        # except ValueError:
        #     print "\nNumber must be convertible to a float, input only numbers in decimal format like 12.3.\nTrying again..."
        #     self.info['baseline_mass'] = float(raw_input("\nWhat is {}'s baseline mass?\n    >".format(self.name)))
        #     self.info['minimum_mass']  = float(raw_input("\nAnd what is {}'s minimum mass? (eg. 80% of baseline?)\n    >".format(self.name)))
        #     self.info['box']           = int(raw_input("\nWhat box will {} be run in?\n    >".format(self.name)))
        #
        # # Make hdf5 structure and Save info to hdf5
        # self.h5info = self.h5f.create_group("/","info","biographical information")
        # self.h5data = self.h5f.create_group("/","data","trial record data")
        # self.h5info.info_table = self.h5f.create_table(self.h5info, 'info',Biography, "A mouse's biographical information table")
        # for k,v in self.info.items():
        #     self.h5info.info_table.row[k] = v
        # self.h5info.info_table.row.append()
        # self.h5info.info_table.flush()
        #
        # # TODO make "schedule" table that lists which trial #s were done when, which steps, etc.
        #
        self.h5f.flush()

    def update_biography(self, params):
        for k, v in params.items():
            self.h5f.root.info._v_attrs[k] = v




    def assign_protocol(self,protocol,params=None):
        # Will need to change this to be protocols rather than individual steps, developing the skeleton.
        #Condition the size of numvars on the number of vars to be stored
        # Assign the names of columns as .attrs['column names']
        self.task_type = protocol

        if params:
            self.task_params = params
        else:
            pass
            #TODO: Created without params from terminal, need to be set by prefs pane

        # Import the task class from its module
        template_module = import_module('taskontrol.templates.{}'.format(protocol))
        task_class = getattr(template_module,template_module.TASK)

        self.task_data_list = task_class.DATA_LIST
        self.task_data_class = task_class.DataTypes
        if 'trial_num' not in self.task_data_list.keys():
            warnings.warn('You didn\'t declare you wanted trial numbers saved. Inserted, but go back and check your task class')
            self.task_data_list.update({'trial_num':'i32'})
            self.task_data_class.trial_num = tables.Int32Col()

        # Check if params are a dict of params or a string referring to a premade parameter set
        if isinstance(params, basestring):
            self.param_template = params
            self.task_params = getattr(template_module, params)
            self.task = task_class(**self.task_params)
        elif isinstance(params, dict):
            self.param_template = False
            self.task = task_class(**self.task_params)
        else:
            raise TypeError('Not sure what to do with your Params, need dict or string reference to parameter set in template')

        # Make dataset in the hdf5 file to store trial records. When protocols are multiple steps, this will be multiple datasets
        # dtask_data_class arg - We have to specifically declare the type of data we are storing since we are likely to have multiple types
            # We do so with a subclass of the task class of type tables.IsDescription.
            # See http://www.pytables.org/usersguide/tutorials.html
        if 'step_num' and 'protocol_type' in self.task_params.keys():
            self.h5trial_records = self.h5f.create_table(self.h5data,
                                                         self.task_params['protocol_type'] + '_' + self.params['step_num'],
                                                         self.task_data_class,
                                                         expectedrows=50000)
        elif 'description' in self.task_params.keys():
            self.h5trial_records = self.h5f.create_table(self.h5data,
                                                         self.task_params['description'],
                                                         self.task_data_class,
                                                         expectedrows=50000)
        else:
            self.h5trial_records = self.h5f.create_table(self.h5data,
                                                         'task_' + str(len(self.h5data._v_children.keys()) + 1),
                                                         self.task_data_class, expectedrows=50000)

        # Save task parameters as table attributes
        self.h5trial_records.attrs.task_type      = self.task_type
        self.h5trial_records.attrs.date_assigned  = datetime.date.today().isoformat()
        self.h5trial_records.attrs.params         = self.task_params
        self.h5trial_records.attrs.data_list      = self.task_data_list
        self.h5trial_records.attrs.param_template = self.param_template
        self.trial_row                            = self.h5trial_records.row
        self.h5f.flush()

    def load_protocol(self,step_number=-1):
        # If no step_number passed, load the last step assigned
        # TODO: dicts are mutable, so last number won't necessarily be last assigned. Fix when multi-step protocols made - use odicts
        last_assigned_task   = self.h5data._v_children.keys()[step_number]
        self.h5trial_records = self.h5data._f_get_child(last_assigned_task)
        self.trial_row       = self.h5trial_records.row
        self.task_type       = self.h5trial_records.attrs.task_type
        self.task_params     = self.h5trial_records.attrs.params
        self.param_template  = self.h5trial_records.attrs.param_template
        self.task_data_list  = self.h5trial_records.attrs.data_list
        # TODO Check if template has changed since assign
        # Import the task class from its module & make
        template_module = import_module('taskontrol.templates.{}'.format(self.task_type))
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
