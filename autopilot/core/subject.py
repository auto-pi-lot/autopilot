"""

Classes for managing data and protocol access and storage.

Currently named subject, but will likely be refactored to include other data
models should the need arise.

"""

# TODO: store pilot in biography
import os
import sys
import threading
import tables
from tables.nodes import filenode
import datetime
import json
import pandas as pd
import warnings
import typing
from copy import copy
# sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from autopilot.tasks import GRAD_LIST, TASK_LIST
from autopilot import prefs
from autopilot.stim.sound.sounds import STRING_PARAMS

if sys.version_info >= (3,0):
    import queue
else:
    import Queue as queue

import pdb
import numpy as np


class Subject(object):
    """
    Class for managing one subject's data and protocol.

    Creates a :mod:`tables` hdf5 file in `prefs.DATADIR` with the general structure::

        / root
        |--- current (tables.filenode) storing the current task as serialized JSON
        |--- data (group)
        |    |--- task_name  (group)
        |         |--- S##_step_name
        |         |    |--- trial_data
        |         |    |--- continuous_data
        |         |--- ...
        |--- history (group)
        |    |--- hashes - history of git commit hashes
        |    |--- history - history of changes: protocols assigned, params changed, etc.
        |    |--- weights - history of pre and post-task weights
        |    |--- past_protocols (group) - stash past protocol params on reassign
        |         |--- date_protocol_name - tables.filenode of a previous protocol's params.
        |         |--- ...
        |--- info - group with biographical information as attributes

    Attributes:
        lock (:class:`threading.Lock`): manages access to the hdf5 file
        name (str): Subject ID
        file (str): Path to hdf5 file - usually `{prefs.DATADIR}/{self.name}.h5`
        current (dict): current task parameters. loaded from
            the 'current' :mod:`~tables.filenode` of the h5 file
        step (int): current step
        protocol_name (str): name of currently assigned protocol
        current_trial (int): number of current trial
        running (bool): Flag that signals whether the subject is currently running a task or not.
        data_queue (:class:`queue.Queue`): Queue to dump data while running task
        thread (:class:`threading.Thread`): thread used to keep file open while running task
        did_graduate (:class:`threading.Event`): Event used to signal if the subject has graduated the current step
        STRUCTURE (list): list of tuples with order:

            * full path, eg. '/history/weights'
            * relative path, eg. '/history'
            * name, eg. 'weights'
            * type, eg. :class:`.Subject.Weight_Table` or 'group'

        node locations (eg. '/data') to types, either 'group' for groups or a
            :class:`tables.IsDescriptor` for tables.
    """



    def __init__(self, name: str=None, dir: str=None, file: str=None,
                 new: bool=False, biography: dict=None):
        """
        Args:
            name (str): subject ID
            dir (str): path where the .h5 file is located, if `None`, `prefs.DATADIR` is used
            file (str): load a subject from a filename. if `None`, ignored.
            new (bool): if True, a new file is made (a new file is made if one does not exist anyway)
            biography (dict): If making a new subject file, a dictionary with biographical data can be passed
        """
        self.STRUCTURE = [
            ('/data', '/', 'data', 'group'),
            ('/history', '/', 'history' 'group'),
            ('/history/hashes', '/history', 'hashes', self.Hash_Table),
            ('/history/history', '/history', 'history', self.History_Table),
            ('/history/weights', '/history', 'weights', self.Weight_Table),
            ('/history/past_protocols', '/history', 'past_protocols', 'group'),
            ('/info', '/', 'info', 'group')
        ]

        # use a filter to compress continuous data
        self.continuous_filter = tables.Filters(complib='blosc', complevel=6)

        self.lock = threading.Lock()

        if not dir:
            try:
                dir = prefs.DATADIR
            except AttributeError:
                dir = os.path.split(file)[0]

        if not name:
            if not file:
                Exception('Need to either have a name or a file, how else would we find the .h5 file?')
            if not os.path.isfile(file):
                Exception('no file was found at passed file: {}'.format(file))
            self.file = file
        else:
            if file:
                Warning('file passed, but so was name, defaulting to using name + dir')

            self.name = str(name)
            self.file = os.path.join(dir, name + '.h5')
            if new or not os.path.isfile(self.file):
                self.new_subject_file(biography)

        # before we open, make sure we have the stuff we need
        self.ensure_structure()

        h5f = self.open_hdf()

        if not name:
            try:
                self.name = h5f.root.info._v_attrs['name']
            except KeyError:
                Warning('No Name attribute saved, trying to recover from filename')
                self.name = os.path.splitext(os.path.split(file)[-1])[0]



        # If subject has a protocol, load it to a dict
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

        # get last session number if we have it
        try:
            self.session = int(h5f.root.info._v_attrs['session'])
        except KeyError:
            self.session = None

        # We will get handles to trial and continuous data when we start running
        self.current_trial  = None

        # Is the subject currently running (ie. we expect data to be incoming)
        # Used to keep the subject object alive, otherwise we close the file whenever we don't need it
        self.running = False

        # We use a threading queue to dump data into a kept-alive h5f file
        self.data_queue = None
        self.thread = None
        self.did_graduate = threading.Event()

        # Every time we are initialized we stash the git hash
        history_row = h5f.root.history.hashes.row
        history_row['time'] = self.get_timestamp()
        try:
            history_row['hash'] = prefs.HASH
        except AttributeError:
            history_row['hash'] = ''
        history_row.append()

        # we have to always open and close the h5f
        _ = self.close_hdf(h5f)

    def open_hdf(self, mode='r+'):
        """
        Opens the hdf5 file.

        This should be called at the start of every method that access the h5 file
        and :meth:`~.Subject.close_hdf` should be called at the end. Otherwise
        the file will close and we risk file corruption.

        See the pytables docs
        `here <https://www.pytables.org/cookbook/threading.html>`_ and
        `here <https://www.pytables.org/FAQ.html#can-pytables-be-used-in-concurrent-access-scenarios>`_

        Args:
            mode (str): a file access mode, can be:

                * 'r': Read-only - no data can be modified.
                * 'w': Write - a new file is created (an existing file with the same name would be deleted).
                * 'a' Append - an existing file is opened for reading and writing, and if the file does not exist it is created.
                * 'r+' (default) - Similar to 'a', but file must already exist.

        Returns:
            :class:`tables.File`: Opened hdf file.
        """
        # TODO: Use a decorator around methods instead of explicitly calling
        with self.lock:
            return tables.open_file(self.file, mode=mode)

    def close_hdf(self, h5f):
        # type: (tables.file.File) -> None
        """
        Flushes & closes the open hdf file.
        Must be called whenever :meth:`~.Subject.open_hdf` is used.

        Args:
            h5f (:class:`tables.File`): the hdf file opened by :meth:`~.Subject.open_hdf`
        """
        with self.lock:
            h5f.flush()
            return h5f.close()

    def new_subject_file(self, biography):
        """
        Create a new subject file and make the general filestructure.

        If a file already exists, open it in append mode, otherwise create it.

        Args:
            biography (dict): Biographical details like DOB, mass, etc.
                Typically created by :class:`~.gui.New_Subject_Wizard.Biography_Tab`.
        """
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
            h5f.create_table(history_group, 'weights', self.Weight_Table, "Subject Weights")

            # And another table to stash the git hash every time we're open.
            h5f.create_table(history_group, 'hashes', self.Hash_Table, "Git commit hash history")

        # Save biographical information as node attributes
        if biography:
            for k, v in biography.items():
                h5f.root.info._v_attrs[k] = v

        h5f.root.info._v_attrs['name'] = self.name
        h5f.root.info._v_attrs['session'] = 0


        self.close_hdf(h5f)

    def ensure_structure(self):
        """
        Ensure that our h5f has the appropriate baseline structure as defined in `self.STRUCTURE`

        Checks that all groups and tables are made, makes them if not
        """
        h5f = self.open_hdf()

        for node in self.STRUCTURE:
            try:
                node = h5f.get_node(node[0])
            except tables.exceptions.NoSuchNodeError:
                #pdb.set_trace()
                # try to make it
                # python 3 compatibility
                if sys.version_info >= (3,0):
                    if isinstance(node[3], str):
                        if node[3] == 'group':
                            h5f.create_group(node[1], node[2])
                    elif issubclass(node[3], tables.IsDescription):
                        h5f.create_table(node[1], node[2], description=node[3])

                # python 2
                else:
                    if isinstance(node[3], str):
                        if node[3] == 'group':
                            h5f.create_group(node[1], node[2])
                    elif issubclass(node[3], tables.IsDescription):
                        h5f.create_table(node[1], node[2], description=node[3])

        self.close_hdf(h5f)


    def update_biography(self, params):
        """
        Change or make a new biographical attribute, stored as
        attributes of the `info` group.

        Args:
            params (dict): biographical attributes to be updated.
        """
        h5f = self.open_hdf()
        for k, v in params.items():
            h5f.root.info._v_attrs[k] = v
        _ = self.close_hdf(h5f)

    def update_history(self, type, name, value, step=None):
        """
        Update the history table when changes are made to the subject's protocol.

        The current protocol is flushed to the past_protocols group and an updated
        filenode is created.

        Note:
            This **only** updates the history table, and does not make the changes itself.

        Args:
            type (str): What type of change is being made? Can be one of

                * 'param' - a parameter of one task stage
                * 'step' - the step of the current protocol
                * 'protocol' - the whole protocol is being updated.

            name (str): the name of either the parameter being changed or the new protocol
            value (str): the value that the parameter or step is being changed to,
                or the protocol dictionary flattened to a string.
            step (int): When type is 'param', changes the parameter at a particular step,
                otherwise the current step is used.
        """
        # Make sure the updates are written to the subject file
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
        if not isinstance(type, str):
            type = str(type)
        if not isinstance(name, str):
            name = str(name)
        if not isinstance(value, str):
            value = str(value)

        # log the change
        h5f = self.open_hdf()
        history_row = h5f.root.history.history.row

        history_row['time'] = self.get_timestamp(simple=True)
        history_row['type'] = type
        history_row['name'] = name
        history_row['value'] = value
        history_row.append()

        _ = self.close_hdf(h5f)


    # def update_params(self, param, value):
    #     """
    #     Args:
    #         param:
    #         value:
    #     """
    #     # TODO: this
    #     pass

    def assign_protocol(self, protocol, step_n=0):
        """
        Assign a protocol to the subject.

        If the subject has a currently assigned task, stashes it with :meth:`~.Subject.stash_current`

        Creates groups and tables according to the data descriptions in the task class being assigned.
        eg. as described in :class:`.Task.TrialData`.

        Updates the history table.

        Args:
            protocol (str): the protocol to be assigned. Can be one of

                * the name of the protocol (its filename minus .json) if it is in `prefs.PROTOCOLDIR`
                * filename of the protocol (its filename with .json) if it is in the `prefs.PROTOCOLDIR`
                * the full path and filename of the protocol.

            step_n (int): Which step is being assigned?
        """
        # Protocol will be passed as a .json filename in prefs.PROTOCOLDIR

        h5f = self.open_hdf()

        ## Assign new protocol
        if not protocol.endswith('.json'):
            protocol = protocol + '.json'

        # try prepending the protocoldir if we were passed just the name
        if not os.path.exists(protocol):
            fullpath = os.path.join(prefs.PROTOCOLDIR, protocol)
            if not os.path.exists(fullpath):
                Exception('Could not find either {} or {}'.format(protocol, fullpath))
            protocol = fullpath

        # Set name and step
        # Strip off path and extension to get the protocol name
        protocol_name = os.path.splitext(protocol)[0].split(os.sep)[-1]

        # check if this is the same protocol so we don't reset session number
        same_protocol = False
        if (protocol_name == self.protocol_name) and (step_n == self.step):
            same_protocol = True

        # Load protocol to dict
        with open(protocol) as protocol_file:
            prot_dict = json.load(protocol_file)

        # Check if there is an existing protocol, archive it if there is.
        if "/current" in h5f:
            _ = self.close_hdf(h5f)
            self.update_history(type='protocol', name=protocol_name, value = prot_dict)
            self.stash_current()
            h5f = self.open_hdf()

        # Make filenode and save as serialized json
        current_node = filenode.new_node(h5f, where='/', name='current')
        current_node.write(json.dumps(prot_dict).encode('utf-8'))
        h5f.flush()

        # save some protocol attributes
        self.current = prot_dict

        current_node.attrs['protocol_name'] = protocol_name
        self.protocol_name = protocol_name

        current_node.attrs['step'] = step_n
        self.step = int(step_n)

        # always start out on session 0 on a new task
        # unless this is the same task as was already assigned
        if not same_protocol:
            h5f.root.info._v_attrs['session'] = 0
            self.session = 0

        # Make file group for protocol
        if "/data/{}".format(protocol_name) not in h5f:
            current_group = h5f.create_group('/data', protocol_name)
        else:
            current_group = h5f.get_node('/data', protocol_name)


        # Create groups for each step
        # There are two types of data - continuous and trialwise.
        # Each gets a single table within a group: since each step should have
        # consistent data requirements over time and hdf5 doesn't need to be in
        # memory, we can just keep appending to keep things simple.
        for i, step in enumerate(self.current):
            # First we get the task class for this step
            task_class = TASK_LIST[step['task_type']]
            step_name = step['step_name']
            # group name is S##_'step_name'
            group_name = "S{:02d}_{}".format(i, step_name)

            if group_name not in current_group:
                step_group = h5f.create_group(current_group, group_name)
            else:
                step_group = current_group._f_get_child(group_name)

            # The task class *should* have at least one PyTables DataTypes descriptor
            try:
                if task_class.TrialData is not None:
                    trial_descriptor = task_class.TrialData
                    # add a session column, everyone needs a session column
                    if 'session' not in trial_descriptor.columns.keys():
                        trial_descriptor.columns.update({'session': tables.Int32Col()})
                    # same thing with trial_num
                    if 'trial_num' not in trial_descriptor.columns.keys():
                        trial_descriptor.columns.update({'trial_num': tables.Int32Col()})
                    # if this task has sounds, make columns for them
                    # TODO: Make stim managers return a list of properties for their sounds
                    if 'stim' in step.keys():
                        if 'manager' in step['stim'].keys():
                            # managers have stim nested within groups, but this is still really ugly
                            sound_params = {}
                            for g in step['stim']['groups']:
                                for side, sounds in g['sounds'].items():
                                    for sound in sounds:
                                        for k, v in sound.items():
                                            if k in STRING_PARAMS:
                                                sound_params[k] = tables.StringCol(1024)
                                            else:
                                                sound_params[k] = tables.Float64Col()
                            trial_descriptor.columns.update(sound_params)

                        elif 'sounds' in step['stim'].keys():
                            # for now we just assume they're floats
                            sound_params = {}
                            for side, sounds in step['stim']['sounds'].items():
                                # each side has a list of sounds
                                for sound in sounds:
                                    for k, v in sound.items():
                                        if k in STRING_PARAMS:
                                            sound_params[k] = tables.StringCol(1024)
                                        else:
                                            sound_params[k] = tables.Float64Col()
                            trial_descriptor.columns.update(sound_params)

                    h5f.create_table(step_group, "trial_data", trial_descriptor)
                else:
                    h5f.create_table(step_group, "trial_data", {'session': tables.Int32Col(), 'trial_num': tables.Int32Col()})
            except tables.NodeError:
                # we already have made this table, that's fine
                pass
            try:
                # if we have continuous data, make a folder for each data stream.
                # each session will make its own subfolder,
                # which contains tables for each of the streams for that session
                if hasattr(task_class, "ContinuousData"):
                    cont_group = h5f.create_group(step_group, "continuous_data")

                    # save data names as attributes
                    data_names = tuple(task_class.ContinuousData.keys())

                    cont_group._v_attrs['data'] = data_names
                    #cont_descriptor = task_class.ContinuousData
                    #cont_descriptor.columns.update({'session': tables.Int32Col()})
                    #h5f.create_table(step_group, "continuous_data", cont_descriptor)
            except tables.NodeError:
                # already made it
                pass

        _ = self.close_hdf(h5f)

        # Update history
        self.update_history('protocol', protocol_name, self.current)

    def flush_current(self):
        """
        Flushes the 'current' attribute in the subject object to the current filenode
        in the .h5

        Used to make sure the stored .json representation of the current task stays up to date
        with the params set in the subject object
        """
        h5f = self.open_hdf()
        h5f.remove_node('/current')
        current_node = filenode.new_node(h5f, where='/', name='current')
        current_node.write(json.dumps(self.current).encode('utf-8'))
        current_node.attrs['step'] = self.step
        current_node.attrs['protocol_name'] = self.protocol_name
        self.close_hdf(h5f)

    def stash_current(self):
        """
        Save the current protocol in the history group and delete the node

        Typically this is called when assigning a new protocol.

        Stored as the date that it was changed followed by its name if it has one
        """
        h5f = self.open_hdf()
        try:
            protocol_name = h5f.get_node_attr('/current', 'protocol_name')
            archive_name = '_'.join([self.get_timestamp(simple=True), protocol_name])
        except AttributeError:
            warnings.warn("protocol_name attribute couldn't be accessed, using timestamp to stash protocol")
            archive_name = self.get_timestamp(simple=True)

        # TODO: When would we want to prefer the .h5f copy over the live one?
        #current_node = filenode.open_node(h5f.root.current)
        #old_protocol = current_node.readall()

        archive_node = filenode.new_node(h5f, where='/history/past_protocols', name=archive_name)
        archive_node.write(json.dumps(self.current).encode('utf-8'))

        h5f.remove_node('/current')
        self.close_hdf(h5f)

    def prepare_run(self):
        """
        Prepares the Subject object to receive data while running the task.

        Gets information about current task, trial number,
        spawns :class:`~.tasks.graduation.Graduation` object,
        spawns :attr:`~.Subject.data_queue` and calls :meth:`~.Subject.data_thread`.

        Returns:
            Dict: the parameters for the current step, with subject id, step number,
                current trial, and session number included.
        """

        trial_table = None
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

        # should have gotten session from current node when we started

        if not self.session:
            try:
                self.session = trial_table.cols.session[-1]
            except IndexError:
                self.session = 0

        self.session += 1
        h5f.root.info._v_attrs['session'] = self.session
        h5f.flush()

        # try:
        #     self.session = trial_table.cols.session[-1]+1
        # except IndexError:
        #     self.session = 0

        # prepare continuous data group and tables
        task_class = TASK_LIST[task_params['task_type']]
        cont_group = None
        if hasattr(task_class, 'ContinuousData'):

            cont_group = h5f.get_node(group_name, 'continuous_data')
            try:
                session_group = h5f.create_group(cont_group, "session_{}".format(self.session))
            except tables.NodeError:
                session_group = h5f.get_node(cont_group, "session_{}".format(self.session))

            # don't create arrays for each dtype here, we will create them as we receive data

        # try:
        #     #cont_table = h5f.get_node(group_name, 'continuous_data')
        #     #self.cont_row   = self.cont_table.row
        #     #self.cont_keys  = self.cont_table.colnames
        # except:
        #     pass

        if not any([cont_group, trial_table]):
            Exception("No data tables exist for step {}! Is there a Trial or Continuous data descriptor in the task class?".format(self.step))
        # TODO: Spawn graduation checking object!
        if 'graduation' in task_params.keys():
            grad_type = task_params['graduation']['type']
            grad_params = task_params['graduation']['value'].copy()

            # add other params asked for by the task class
            grad_obj = GRAD_LIST[grad_type]

            if grad_obj.PARAMS:
                # these are params that should be set in the protocol settings
                for param in grad_obj.PARAMS:
                    #if param not in grad_params.keys():
                    # for now, try to find it in our attributes
                    # TODO: See where else we would want to get these from
                    if hasattr(self, param):
                        grad_params.update({param:getattr(self, param)})

            if grad_obj.COLS:
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

        # return a task parameter dictionary

        task = copy(self.current[self.step])
        task['subject'] = self.name
        task['step'] = int(self.step)
        task['current_trial'] = int(self.current_trial)
        task['session'] = int(self.session)
        return task

    def data_thread(self, queue):
        """
        Thread that keeps hdf file open and receives data while task is running.

        receives data through :attr:`~.Subject.queue` as dictionaries. Data can be
        partial-trial data (eg. each phase of a trial) as long as the task returns a dict with
        'TRIAL_END' as a key at the end of each trial.

        each dict given to the queue should have the `trial_num`, and this method can
        properly store data without passing `TRIAL_END` if so. I recommend being explicit, however.

        Checks graduation state at the end of each trial.

        Args:
            queue (:class:`queue.Queue`): passed by :meth:`~.Subject.prepare_run` and used by other
                objects to pass data to be stored.
        """
        h5f = self.open_hdf()

        task_params = self.current[self.step]
        step_name = task_params['step_name']

        # file structure is '/data/protocol_name/##_step_name/tables'
        group_name = "/data/{}/S{:02d}_{}".format(self.protocol_name, self.step, step_name)
        #try:
        trial_table = h5f.get_node(group_name, 'trial_data')
        trial_keys = trial_table.colnames
        trial_row = trial_table.row

        # try to get continuous data table if any
        cont_data = tuple()
        cont_tables = {}
        cont_rows = {}
        try:
            continuous_group = h5f.get_node(group_name, 'continuous_data')
            session_group = h5f.get_node(continuous_group, 'session_{}'.format(self.session))
            cont_data = continuous_group._v_attrs['data']


            cont_tables = {}
            cont_rows = {}
            #continuous_keys  = continuous_table.colnames
            #continous_row    = continuous_table.row
        except AttributeError:
            continuous_table = False

        # start getting data
        # stop when 'END' gets put in the queue
        for data in iter(queue.get, 'END'):
            # wrap everything in try because this thread shouldn't crash
            try:
                # if we get continuous data, this should be simple because we always get a whole row
                # there must be a more elegant way to check if something is a key and it is true...
                # yet here we are
                if 'continuous' in data.keys():
                    for k, v in data.items():
                        # if this isn't data that we're expecting, ignore it
                        if k not in cont_data:
                            continue

                        # if we haven't made a table yet, do it
                        if k not in cont_tables.keys():
                            # make atom for this data
                            try:
                                # if it's a numpy array...
                                col_atom = tables.Atom.from_type(v.dtype.name, v.shape)
                            except AttributeError:
                                temp_array = np.array(v)
                                col_atom = tables.Atom.from_type(temp_array.dtype.name, temp_array.shape)
                            # should have come in with a timestamp
                            # TODO: Log if no timestamp is received
                            try:
                                temp_timestamp_arr = np.array(data['timestamp'])
                                timestamp_atom = tables.Atom.from_type(temp_timestamp_arr.dtype.name,
                                                                       temp_timestamp_arr.shape)

                            except KeyError:
                                Warning('no timestamp sent with continuous data')
                                continue


                            cont_tables[k] = h5f.create_table(session_group, k, description={
                                k: tables.Col.from_atom(col_atom),
                                'timestamp': tables.Col.from_atom(timestamp_atom)
                            }, filters=self.continuous_filter)

                            cont_rows[k] = cont_tables[k].row

                        cont_rows[k][k] = v
                        cont_rows[k]['timestamp'] = data['timestamp']
                        cont_rows[k].append()

                    # continue, the rest is for handling trial data
                    continue



                # Check if this is the same
                # if we've already recorded a trial number for this row,
                # and the trial number we just got is not the same,
                # we edit that row if we already have some data on it or else start a new row
                if 'trial_num' in data.keys():
                    if (trial_row['trial_num']) and (trial_row['trial_num'] is None):
                        trial_row['trial_num'] = data['trial_num']

                    if (trial_row['trial_num']) and (trial_row['trial_num'] != data['trial_num']):

                        # find row with this trial number if it exists
                        # this will return a list of rows with matching trial_num.
                        # if it's empty, we didn't receive a TRIAL_END and should create a new row
                        other_row = [r for r in trial_table.where("trial_num == {}".format(data['trial_num']))]

                        if len(other_row) == 0:
                            # proceed to fill the row below
                            trial_row.append()

                        elif len(other_row) == 1:
                            # update the row and continue so we don't double write
                            # have to be in the middle of iteration to use update()
                            for row in trial_table.where("trial_num == {}".format(data['trial_num'])):
                                for k, v in data.items():
                                    if k in trial_keys:
                                        row[k] = v
                                row.update()
                            continue

                        else:
                            # we have more than one row with this trial_num.
                            # shouldn't happen, but we dont' want to throw any data away
                            Warning('Found multiple rows with same trial_num: {}'.format(data['trial_num']))
                            # continue just for data conservancy's sake
                            trial_row.append()

                for k, v in data.items():
                    # some bug where some columns are not always detected,
                    # rather than failing out here, just log error
                    if k in trial_keys:
                        try:
                            trial_row[k] = v
                        except KeyError:
                            # TODO: Logging here
                            Warning("Data dropped: key: {}, value: {}".format(k, v))

                # TODO: Or if all the values have been filled, shouldn't need explicit TRIAL_END flags
                if 'TRIAL_END' in data.keys():
                    trial_row['session'] = self.session
                    trial_row.append()
                    trial_table.flush()
                    if self.graduation:
                        # set our graduation flag, the terminal will get the rest rolling
                        did_graduate = self.graduation.update(trial_row)
                        if did_graduate is True:
                            self.did_graduate.set()

                # always flush so that our row iteration routines above will find what they're looking for
                trial_table.flush()
            except Exception as e:
                # TODO: Get logger and log this
                # we shouldn't throw any exception in this thread, just log it and move on
                print(e)

        self.close_hdf(h5f)

    def save_data(self, data):
        """
        Alternate and equivalent method of putting data in the queue as `Subject.data_queue.put(data)`

        Args:
            data (dict): trial data. each should have a 'trial_num', and a dictionary with key
                'TRIAL_END' should be passed at the end of each trial.
        """
        self.data_queue.put(data)

    def stop_run(self):
        """
        puts 'END' in the data_queue, which causes :meth:`~.Subject.data_thread` to end.
        """
        self.data_queue.put('END')
        self.thread.join(5)
        self.running = False
        if self.thread.is_alive():
            Warning('Data thread did not exit')

    def to_csv(self, path, task='current', step='all'):
        """
        Export trial data to .csv

        Args:
            path (str): output path of .csv
            task (str, int):  not implemented, but in the future pull data from 'current' or other named task
            step (str, int, list, tuple): Step to select, see :meth:`.Subject.get_trial_data`
        """
        # TODO: Jonny just scratching out temporarily, doesn't have all features implemented
        df = self.get_trial_data(step=step)
        df['subject'] = self.name
        df.to_csv(path)
        print("""Subject {}
dataframe saved to:\n {}
========================
N Trials:   {}
N Sessions: {}""".format(self.name, path, df.shape[0], len(df.session.unique())))



    def get_trial_data(self,
                       step: typing.Union[int, list, str] = -1,
                       what: str ="data"):
        """
        Get trial data from the current task.

        Args:
            step (int, list, 'all'): Step that should be returned, can be one of

                * -1: most recent step
                * int: a single step
                * list of two integers eg. [0, 5], an inclusive range of steps.
                * string: the name of a step (excluding S##_)
                * 'all': all steps.

            what (str): What should be returned?

                * 'data' : Dataframe of requested steps' trial data
                * 'variables': dict of variables *without* loading data into memory

        Returns:
            :class:`pandas.DataFrame`: DataFrame of requested steps' trial data.
        """
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
            if step > len(step_groups):
                ValueError('You provided a step number ({}) greater than the number of steps in the subjects assigned protocol: ()'.format(step, len(step_groups)))
            step_groups = [step_groups[step]]

        elif isinstance(step, str) and step != 'all':

            # since step names have S##_ prepended in the hdf5 file,
            # but we want to be able to call them by their human readable name,
            # have to make sure we have the right form
            _step_groups = [s for s in step_groups if s == step]
            if len(_step_groups) == 0:
                _step_groups = [s for s in step_groups if step in s]
            step_groups = _step_groups

        elif isinstance(step, list):
            if isinstance(step[0], int):
                step_groups = step_groups[int(step[0]):int(step[1])]
            elif isinstance(step[0], str):
                _step_groups = []
                for a_step in step:
                    step_name = [s for s in step_groups if s==a_step]
                    if len(step_name) == 0:
                        step_name = [s for s in step_groups if a_step in s]
                    _step_groups.extend(step_name)

                step_groups = _step_groups
        print('step groups:')
        print(step_groups)

        if what == "variables":
            return_data = {}

        for step_key in step_groups:
            step_n = int(step_key[1:3]) # beginning of keys will be 'S##'
            step_tab = group._v_children[step_key]._v_children['trial_data']
            if what == "data":
                step_df = pd.DataFrame(step_tab.read())
                step_df['step'] = step_n
                step_df['step_name'] = step_key
                try:
                    return_data = return_data.append(step_df, ignore_index=True)
                except NameError:
                    return_data = step_df

            elif what == "variables":
                return_data[step_key] = step_tab.coldescrs


        self.close_hdf(h5f)

        return return_data

    def apply_along(self, along='session', step=-1):
        h5f = self.open_hdf()
        group_name = "/data/{}".format(self.protocol_name)
        group = h5f.get_node(group_name)
        step_groups = sorted(group._v_children.keys())

        if along == "session":
            if step == -1:
                # find the last trial step with data
                for step_name in reversed(step_groups):
                    if group._v_children[step_name].trial_data.attrs['NROWS'] > 0:
                        step_groups = [step_name]
                        break
            elif isinstance(step, int):
                if step > len(step_groups):
                    ValueError(
                        'You provided a step number ({}) greater than the number of steps in the subjects assigned protocol: ()'.format(
                            step, len(step_groups)))
                step_groups = [step_groups[step]]

            for step_key in step_groups:
                step_n = int(step_key[1:3])  # beginning of keys will be 'S##'
                step_tab = group._v_children[step_key]._v_children['trial_data']
                step_df = pd.DataFrame(step_tab.read())
                step_df['step'] = step_n
                yield step_df





    def get_step_history(self, use_history=True):
        """
        Gets a dataframe of step numbers, timestamps, and step names
        as a coarse view of training status.

        Args:
            use_history (bool): whether to use the history table or to reconstruct steps and dates from the trial table itself.
                compatibility fix for old versions that didn't stash step changes when the whole protocol was updated.

        Returns:
            :class:`pandas.DataFrame`

        """
        h5f = self.open_hdf()
        if use_history:
            history = h5f.root.history.history
            # return a dataframe of step number, datetime and step name
            step_df = pd.DataFrame([(x['value'], x['time'], x['name']) for x in history.iterrows() if x['type'] == 'step'])

            step_df = step_df.rename({0: 'step_n',
                                      1: 'timestamp',
                                      2: 'name'}, axis='columns')

            step_df['timestamp'] = pd.to_datetime(step_df['timestamp'],
                                                  format='%y%m%d-%H%M%S')

        else:
            group_name = "/data/{}".format(self.protocol_name)
            group = h5f.get_node(group_name)
            step_groups = sorted(group._v_children.keys())

            # find the last trial step with data
            for step_name in reversed(step_groups):
                if group._v_children[step_name].trial_data.attrs['NROWS']>0:
                    step_groups = [step_name]
                    break

            # Iterate through steps, find first timestamp, use that.
            for step_key in step_groups:
                step_n = int(step_key[1:3])  # beginning of keys will be 'S##'
                step_name = self.current[step_n]['step_name']
                step_tab = group._v_children[step_key]._v_children['trial_data']
                # find name of column that is a timestamp
                colnames = step_tab.cols._v_colnames
                try:
                    ts_column = [col for col in colnames if "timestamp" in col][0]
                    ts = step_tab.read(start=0, stop=1, field=ts_column)

                except IndexError:
                    Warning('No Timestamp column found, only returning step numbers and named that were reached')
                    ts = 0

                step_df = pd.DataFrame(
                    {'step_n':step_n,
                     'timestamp':ts,
                     'name':step_name
                    })
                try:
                    return_df = return_df.append(step_df, ignore_index=True)
                except NameError:
                    return_df = step_df

            step_df = return_df

        self.close_hdf(h5f)
        return step_df

    def get_timestamp(self, simple=False):
        # type: (bool) -> str
        """
        Makes a timestamp.

        Args:
            simple (bool):
                if True:
                    returns as format '%y%m%d-%H%M%S', eg '190201-170811'
                if False:
                    returns in isoformat, eg. '2019-02-01T17:08:02.058808'

        Returns:
            basestring
        """
        # Timestamps have two different applications, and thus two different formats:
        # coarse timestamps that should be human-readable
        # fine timestamps for data analysis that don't need to be
        if simple:
            return datetime.datetime.now().strftime('%y%m%d-%H%M%S')
        else:
            return datetime.datetime.now().isoformat()

    def get_weight(self, which='last', include_baseline=False):
        """
        Gets start and stop weights.

        TODO:
            add ability to get weights by session number, dates, and ranges.

        Args:
            which (str):  if 'last', gets most recent weights. Otherwise returns all weights.
            include_baseline (bool): if True, includes baseline and minimum mass.

        Returns:
            dict
        """
        # get either the last start/stop weights, optionally including baseline
        # TODO: Get by session
        weights = {}

        h5f = self.open_hdf()
        weight_table = h5f.root.history.weights
        if which == 'last':
            for column in weight_table.colnames:
                try:
                    weights[column] = weight_table.read(-1, field=column)[0]
                except IndexError:
                    weights[column] = None
        else:
            for column in weight_table.colnames:
                try:
                    weights[column] = weight_table.read(field=column)
                except IndexError:
                    weights[column] = None

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

    def set_weight(self, date, col_name, new_value):
        """
        Updates an existing weight in the weight table.

        TODO:
            Yes, i know this is bad. Merge with update_weights

        Args:
            date (str): date in the 'simple' format, %y%m%d-%H%M%S
            col_name ('start', 'stop'): are we updating a pre-task or post-task weight?
            new_value (float): New mass.
        """

        h5f = self.open_hdf()
        weight_table = h5f.root.history.weights
        # there should only be one matching row since it includes seconds
        for row in weight_table.where('date == b"{}"'.format(date)):
            row[col_name] = new_value
            row.update()

        self.close_hdf(h5f)


    def update_weights(self, start=None, stop=None):
        """
        Store either a starting or stopping mass.

        `start` and `stop` can be passed simultaneously, `start` can be given in one
        call and `stop` in a later call, but `stop` should not be given before `start`.

        Args:
            start (float): Mass before running task in grams
            stop (float): Mass after running task in grams.
        """
        h5f = self.open_hdf()
        if start is not None:
            weight_row = h5f.root.history.weights.row
            weight_row['date'] = self.get_timestamp(simple=True)
            weight_row['session'] = self.session
            weight_row['start'] = float(start)
            weight_row.append()
        elif stop is not None:
            # TODO: Make this more robust - don't assume we got a start weight
            h5f.root.history.weights.cols.stop[-1] = stop
        else:
            Warning("Need either a start or a stop weight")

        _ = self.close_hdf(h5f)

    def graduate(self):
        """
        Increase the current step by one, unless it is the last step.
        """
        if len(self.current)<=self.step+1:
            Warning('Tried to graduate from the last step!\n Task has {} steps and we are on {}'.format(len(self.current), self.step+1))
            return

        # increment step, update_history should handle the rest
        step = self.step+1
        name = self.current[step]['step_name']
        self.update_history('step', name, step)

    class History_Table(tables.IsDescription):
        """
        Class to describe parameter and protocol change history

        Attributes:
            time (str): timestamps
            type (str): Type of change - protocol, parameter, step
            name (str): Name - Which parameter was changed, name of protocol, manual vs. graduation step change
            value (str): Value - What was the parameter/protocol/etc. changed to, step if protocol.
        """

        time = tables.StringCol(256)
        type = tables.StringCol(256)
        name = tables.StringCol(256)
        value = tables.StringCol(4028)

    class Weight_Table(tables.IsDescription):
        """
        Class to describe table for weight history

        Attributes:
            start (float): Pre-task mass
            stop (float): Post-task mass
            date (str): Timestamp in simple format
            session (int): Session number
        """
        start = tables.Float32Col()
        stop  = tables.Float32Col()
        date  = tables.StringCol(256)
        session = tables.Int32Col()

    class Hash_Table(tables.IsDescription):
        """
        Class to describe table for hash history

        Attributes:
            time (str): Timestamps
            hash (str): Hash of the currently checked out commit of the git repository.
        """
        time = tables.StringCol(256)
        hash = tables.StringCol(40)

