#!/usr/bin/python2.7

'''
Base Mouse Class.
Methods for storing data like mass, DOB, etc. as well as assigned protocols and trial data
'''

import os
import sys
import tables
from tables.nodes import filenode
import datetime
from time import time
import json
import pandas as pd
import warnings
sys.path.append('~/git/RPilot')
import tasks
import threading
from stim.sound.sounds import STRING_PARAMS

if sys.version_info >= (3,0):
    import queue
else:
    import Queue as queue


class Mouse:
    """Mouse object for managing protocol, parameters, and data"""

    def __init__(self, name, dir='/usr/rpilot/data', new=False, biography=None):
        # we need to use a lock to not corrupt the file, see
        # https://www.pytables.org/cookbook/threading.html
        # and https://www.pytables.org/FAQ.html#can-pytables-be-used-in-concurrent-access-scenarios
        self.lock = threading.Lock()

        #TODO: Pass dir from prefs
        self.name = str(name)
        self.file = os.path.join(dir, name + '.h5')
        if new or not os.path.isfile(self.file):
            self.new_mouse_file(biography)

        h5f = tables.open_file(self.file, 'r+')



        # Make shortcuts for direct assignation
        self.info = h5f.root.info._v_attrs
        self.data = h5f.root.data
        self.history = h5f.root.history.history

        # If mouse has a protocol, load it to a dict
        self.current = None
        self.step    = None
        self.protocol_name = None
        if "/current" in h5f:
            # We load the info from 'current' but don't keep the node open
            # Stash it as a dict so better access from Python
            current_node = filenode.open_node(h5f.root.current)
            protocol_string = current_node.readall()
            self.current = json.loads(protocol_string)
            self.step = int(current_node.attrs['step'])
            self.protocol_name = current_node.attrs['protocol_name']
            self.current_group = h5f.get_node('/data',self.protocol_name)

        # We will get handles to trial and continuous data when we start running
        self.trial_table = None
        self.trial_row   = None
        self.trial_keys  = None
        self.cont_table  = None
        self.cont_row    = None
        self.cont_keys   = None
        self.current_trial  = None

        # Is the mouse currently running (ie. we expect data to be incoming)
        # Used to keep the mouse object alive, otherwise we close the file whenever we don't need it
        self.running = False

        # We use a threading queue to dump data into a kept-alive h5f file
        self.data_queue = None
        self.thread = None
        self.did_graduate = threading.Event()


        # we have to always open and close the h5f
        h5f.close()

    def open_hdf(self, mode='r+'):
        with self.lock:
            return tables.open_file(self.file, mode=mode)

    def close_hdf(self, h5f):
        with self.lock:
            h5f.flush()
            return h5f.close()

    def new_mouse_file(self, biography):
        # If a file already exists, we open it for appending so we don't lose data.
        # For now we are assuming that the existing file has the basic structure,
        # but that's probably a bad assumption for full reliability
        if os.path.isfile(self.file):
            h5f = self.open_hdf(mode='a')
        else:
            h5f = self.open_hdf(mode='w')

            # Make Basic file structure
            h5f.create_group("/","data","Trial Record Data")
            h5f.create_group("/","info","Biographical Info")
            history_group = h5f.create_group("/","history","History")

            # When a whole protocol is changed, we stash the old protocol as a filenode in the past_protocols group
            h5f.create_group("/history", "past_protocols",'Past Protocol Files')

            # Also canonical to the basic file structure is the 'current' filenode which stores the current protocol,
            # but since we want to be able to tell that a protocol hasn't been assigned yet we don't instantiate it here
            # See http://www.pytables.org/usersguide/filenode.html
            # filenode.new_node(h5f, where="/", name="current")

            # We keep track of changes to parameters, promotions, etc. in the history table
            h5f.create_table(history_group, 'history', self.History_Table, "Change History")

            # Make table for weights
            h5f.create_table(history_group, 'weights', self.Weight_Table, "Mouse Weights")

        # Save biographical information as node attributes
        if biography:
            for k, v in biography.items():
                h5f.root.info._v_attrs[k] = v

        self.close_hdf(h5f)

    def update_biography(self, params):
        h5f = self.open_hdf()
        for k, v in params.items():
            h5f.root.info._v_attrs[k] = v
        _ = self.close_hdf(h5f)

    def update_history(self, type, name, value, step=None):
        # Make sure the updates are written to the mouse file
        if type == 'param':
            if not step:
                self.current[self.step][name] = value
            else:
                self.current[step][name] = value
            self.flush_current()
        elif type == 'step':
            self.step = int(value)
            self.flush_current()
        elif type == 'protocol':
            self.flush_current()


        # Check that we're all strings in here
        if not isinstance(type, basestring):
            type = str(type)
        if not isinstance(name, basestring):
            name = str(name)
        if not isinstance(value, basestring):
            value = str(value)

        h5f = self.open_hdf()
        history_row = h5f.root.history.history.row

        history_row['time'] = self.get_timestamp(string=True)
        history_row['type'] = type
        history_row['name'] = name
        history_row['value'] = value
        history_row.append()

        _ = self.close_hdf(h5f)

    def update_weights(self, start=None, stop=None):
        h5f = self.open_hdf()
        if start is not None:
            weight_row = h5f.root.history.weights.row
            weight_row['date'] = self.get_timestamp(string=True)
            weight_row['session'] = self.session
            weight_row['start'] = float(start)
            weight_row.append()
        elif stop is not None:
            # TODO: Make this more robust - don't assume we got a start weight
            h5f.root.history.weights.cols.stop[-1] = stop
        else:
            Warning("Need either a start or a stop weight")

        _ = self.close_hdf(h5f)

    def update_params(self, param, value):
        # TODO: this
        pass

    def assign_protocol(self, protocol, step_n=0):
        # Protocol will be passed as a .json filename in prefs['PROTOCOLDIR']
        # The full filename is passed because we don't want to assume knowledge of prefs in the mouse data model

        # Check if there is an existing protocol, archive it if there is.
        h5f = self.open_hdf()

        if "/current" in h5f:
            _ = self.close_hdf(h5f) # TODO: See if this is necessary or if we can have multiple handles open
            self.stash_current()
            h5f = self.open_hdf()

        ## Assign new protocol
        # Load protocol to dict
        with open(protocol) as protocol_file:
            self.current = json.load(protocol_file)

        # Make filenode and save as serialized json
        current_node = filenode.new_node(h5f, where='/', name='current')
        current_node.write(json.dumps(self.current))
        h5f.flush()

        # Set name and step
        # Strip off path and extension to get the protocol name
        protocol_name = os.path.splitext(protocol)[0].split(os.sep)[-1]
        current_node.attrs['protocol_name'] = protocol_name
        self.protocol_name = protocol_name

        current_node.attrs['step'] = step_n
        self.step = int(step_n)

        # Make file group for protocol
        if "/data/{}".format(protocol_name) not in h5f:
            self.current_group = h5f.create_group('/data', protocol_name)
        else:
            self.current_group = h5f.get_node('/data', protocol_name)

        # Create groups for each step
        # There are two types of data - continuous and trialwise.
        # Each gets a single table within a group: since each step should have
        # consistent data requirements over time and hdf5 doesn't need to be in
        # memory, we can just keep appending to keep things simple.
        for i, step in enumerate(self.current):
            # First we get the task class for this step
            task_class = tasks.TASK_LIST[step['task_type']]
            step_name = step['step_name']
            # group name is S##_'step_name'
            group_name = "S{:02d}_{}".format(i, step_name)

            if group_name not in self.current_group:
                step_group = h5f.create_group(self.current_group, group_name)
            else:
                step_group = self.current_group._f_get_child(group_name)

            # The task class *should* have at least one PyTables DataTypes descriptor
            try:
                if hasattr(task_class, "TrialData"):
                    trial_descriptor = task_class.TrialData
                    # add a session column, everyone needs a session column
                    if 'session' not in trial_descriptor.columns.keys():
                        trial_descriptor.columns.update({'session': tables.Int32Col()})
                    # if this task has sounds, make columns for them
                    if 'sounds' in step.keys():
                        # for now we just assume they're floats
                        sound_params = {}
                        for side, sounds in step['sounds'].items():
                            # each side has a list of sounds
                            for sound in sounds:
                                for k, v in sound.items():
                                    if k in STRING_PARAMS:
                                        sound_params[k] = tables.StringCol(1024)
                                    else:
                                        sound_params[k] = tables.Float64Col()
                        trial_descriptor.columns.update(sound_params)

                    h5f.create_table(step_group, "trial_data", trial_descriptor)
            except tables.NodeError:
                # we already have made this table, that's fine
                pass
            try:
                if hasattr(task_class, "ContinuousData"):
                    cont_descriptor = task_class.ContinuousData
                    cont_descriptor.columns.update({'session': tables.Int32Col()})
                    h5f.create_table(step_group, "continuous_data", cont_descriptor)
            except tables.NodeError:
                # already made it
                pass

        _ = self.close_hdf(h5f)

        # Update history
        self.update_history('protocol', protocol_name, self.current)

    def flush_current(self):
        # Flush the 'current' attribute in the mouse object to the .h5
        # makes sure the stored .json representation of the current task stays up to date
        # with the params set in the mouse object
        h5f = self.open_hdf()
        h5f.remove_node('/current')
        current_node = filenode.new_node(h5f, where='/', name='current')
        current_node.write(json.dumps(self.current))
        current_node.attrs['step'] = self.step
        current_node.attrs['protocol_name'] = self.protocol_name
        _ = self.close_hdf(h5f)

    def stash_current(self):
        # Save the current protocol in the history group and delete the node
        # Typically this should only be called when assigning a new protocol but what do I know

        # We store it as the date that it was changed followed by its name if it has one
        h5f = self.open_hdf()
        try:
            protocol_name = h5f.get_node_attr('/current', 'protocol_name')
            archive_name = '_'.join([self.get_timestamp(string=True), protocol_name])
        except AttributeError:
            warnings.warn("protocol_name attribute couldn't be accessed, using timestamp to stash protocol")
            archive_name = self.get_timestamp(string=True)

        # TODO: When would we want to prefer the .h5f copy over the live one?
        #current_node = filenode.open_node(h5f.root.current)
        #old_protocol = current_node.readall()

        archive_node = filenode.new_node(h5f, where='/history/past_protocols', name=archive_name)
        archive_node.write(json.dumps(self.current))

        h5f.remove_node('/current')
        self.close_hdf(h5f)

    def prepare_run(self):
        #trial_table = None
        cont_table = None

        h5f = self.open_hdf()

        # Get current task parameters and handles to tables
        task_params = self.current[self.step]
        step_name = task_params['step_name']

        # file structure is '/data/protocol_name/##_step_name/tables'
        group_name = "/data/{}/S{:02d}_{}".format(self.protocol_name, self.step, step_name)
        #try:
        trial_table = h5f.get_node(group_name, 'trial_data')
        #self.trial_row = self.trial_table.row
        #self.trial_keys = self.trial_table.colnames

        # get last trial number and session
        try:
            self.current_trial = trial_table.cols.trial_num[-1]+1
        except IndexError:
            self.current_trial = 0

        try:
            self.session = trial_table.cols.session[-1]+1
        except IndexError:
            self.session = 0

        try:
            cont_table = h5f.get_node(group_name, 'continuous_data')
            #self.cont_row   = self.cont_table.row
            #self.cont_keys  = self.cont_table.colnames
        except:
            pass

        if not any([cont_table, trial_table]):
            Exception("No data tables exist for step {}! Is there a Trial or Continuous data descriptor in the task class?".format(self.step))

        # TODO: Spawn graduation checking object!
        if 'graduation' in task_params.keys():
            grad_type = task_params['graduation']['type']
            grad_params = task_params['graduation']['value'].copy()

            # add other params asked for by the task class
            grad_obj = tasks.GRAD_LIST[grad_type]

            if hasattr(grad_obj, 'PARAMS'):
                # these are params that should be set in the protocol settings
                for param in grad_obj.PARAMS:
                    if param not in grad_params.keys():
                        # for now, try to find it in our attributes
                        # TODO: See where else we would want to get these from
                        if hasattr(self, param):
                            grad_params.update({param:getattr(self, param)})

            if hasattr(grad_obj, 'COLS'):
                # these are columns in our trial table
                for col in grad_obj.COLS:
                    try:
                        grad_params.update({col: trial_table.col(col)})
                    except KeyError:
                        Warning('Graduation object requested column {}, but it was not found in the trial table'.format(col))



            #grad_params['value']['current_trial'] = str(self.current_trial) # str so it's json serializable
            self.graduation = grad_obj(**grad_params)
            self.did_graduate.clear()
        else:
            self.graduation = None

        self.close_hdf(h5f)

        # spawn thread to accept data
        self.data_queue = queue.Queue()
        self.thread = threading.Thread(target=self.data_thread, args=(self.data_queue,))
        self.thread.start()
        self.running = True

    def data_thread(self, queue):

        h5f = self.open_hdf()

        task_params = self.current[self.step]
        step_name = task_params['step_name']

        # file structure is '/data/protocol_name/##_step_name/tables'
        group_name = "/data/{}/S{:02d}_{}".format(self.protocol_name, self.step, step_name)
        #try:
        trial_table = h5f.get_node(group_name, 'trial_data')
        trial_keys = trial_table.colnames
        trial_row = trial_table.row

        # start getting data
        # stop when 'END' gets put in the queue
        for data in iter(queue.get, 'END'):
            for k, v in data.items():
                if k in trial_keys:
                    trial_row[k] = v
            if 'TRIAL_END' in data.keys():
                trial_row['session'] = self.session
                trial_row.append()
                trial_table.flush()
                if self.graduation:
                    # set our graduation flag, the terminal will get the rest rolling
                    did_graduate = self.graduation.update(trial_row)
                    if did_graduate is True:
                        self.did_graduate.set()

        self.close_hdf(h5f)

    def save_data(self, data):
        self.data_queue.put(data)

    def stop_run(self):
        self.data_queue.put('END')
        self.thread.join(5)
        self.running = False
        if self.thread.is_alive():
            Warning('Data thread did not exit')

    def get_trial_data(self, step=-1):
        # step= -1 is just most recent step,
        # step= int is an integer specified step
        # step= [n1, n2] is from step n1 to n2 inclusive
        # step= 'all' or anything that isn't an int or a list is all steps
        h5f = self.open_hdf()
        group_name = "/data/{}".format(self.protocol_name)
        group = h5f.get_node(group_name)
        step_groups = sorted(group._v_children.keys())

        if step == -1:
            # find the last trial step with data
            for step_name in reversed(step_groups):
                if group._v_children[step_name].trial_data.attrs['NROWS']>0:
                    step_groups = [step_name]
                    break
        elif isinstance(step, int):
            step_groups = step_groups[step]
        elif isinstance(step, list):
            step_groups = step_groups[int(step[0]):int(step[1])]

        for step_key in step_groups:
            step_n = int(step_key[1:3]) # beginning of keys will be 'S##'
            step_tab = group._v_children[step_key]._v_children['trial_data']
            step_df = pd.DataFrame(step_tab.read())
            step_df['step'] = step_n
            try:
                return_df = return_df.append(step_df, ignore_index=True)
            except NameError:
                return_df = step_df

        self.close_hdf(h5f)

        return return_df


    def get_step_history(self):
        h5f = self.open_hdf()
        history = h5f.root.history.history
        # return a dataframe of step number, datetime and step name
        step_df = pd.DataFrame([(x['value'], x['time'], x['name']) for x in history.iterrows() if x['type'] == 'step'])
        step_df = step_df.rename({0: 'step_n',
                                  1: 'timestamp',
                                  2: 'name'}, axis='columns')

        step_df['timestamp'] = pd.to_datetime(step_df['timestamp'],
                                              format='%y%m%d-%H%M%S')

        self.close_hdf(h5f)
        return step_df










    def get_timestamp(self, string=False):
        # Timestamps have two different applications, and thus two different formats:
        # coarse timestamps that should be human-readable
        # fine timestamps for data analysis that don't need to be
        if string:
            return datetime.datetime.now().strftime('%y%m%d-%H%M%S')
        else:
            return time()

    def get_weight(self, which='last', include_baseline=False):
        # get either the last start/stop weights, optionally including baseline
        # TODO: Get by session
        weights = {}

        h5f = self.open_hdf()
        weight_table = h5f.root.history.weights
        if which == 'last':
            for column in weight_table.colnames:
                weights[column] = weight_table.read(-1, field=column)[0]
        if include_baseline is True:
            try:
                baseline = float(h5f.root.info._v_attrs['baseline_mass'])
            except KeyError:
                baseline = 0.0
            minimum = baseline*0.8
            weights['baseline_mass'] = baseline
            weights['minimum_mass'] = minimum

        self.close_hdf(h5f)
        return weights



    def graduate(self):
        if len(self.current)<=self.step+1:
            Warning('Tried to graduate from the last step!\n Task has {} steps and we are on {}'.format(len(self.current), self.step+1))
            return

        # increment step, update_history should handle the rest
        step = self.step+1
        name = self.current[step]['step_name']
        self.update_history('step', name, step)

    class History_Table(tables.IsDescription):
        # Class to describe parameter and protocol change history
        # Columns:
            # Timestamp
            # Type of change - protocol, parameter, step
            # Name - Which parameter was changed, name of protocol, manual vs. graduation step change
            # Value - What was the parameter/protocol/etc. changed to, step if protocol.
        time = tables.StringCol(256)
        type = tables.StringCol(256)
        name = tables.StringCol(256)
        value = tables.StringCol(4028)

    class Weight_Table(tables.IsDescription):
        start = tables.Float32Col()
        stop  = tables.Float32Col()
        date  = tables.StringCol(256)
        session = tables.Int32Col()



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
