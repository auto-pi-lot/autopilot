"""

Classes for managing data and protocol access and storage.

Currently named subject, but will likely be refactored to include other data
models should the need arise.

"""
import threading
import datetime
import json
import uuid
import warnings
import typing
from typing import Union, Optional
from copy import copy
from typing import Optional
from contextlib import contextmanager
from pathlib import Path

import pandas as pd
import numpy as np
import tables
from tables.nodes import filenode

import autopilot
from autopilot import prefs
from autopilot.data.modeling.base import Table
from autopilot.data.models.subject import Subject_Structure, Protocol_Status, Hashes, History, Weights
from autopilot.data.models.biography import Biography
from autopilot.data.models.protocol import Protocol_Group
from autopilot.core.loggers import init_logger

import queue

# suppress pytables natural name warnings
warnings.simplefilter('ignore', category=tables.NaturalNameWarning)

# --------------------------------------------------
# Classes to describe structure of subject files
# --------------------------------------------------


class Subject(object):
    """
    Class for managing one subject's data and protocol.

    Creates a :mod:`tables` hdf5 file in `prefs.get('DATADIR')` with the general structure::

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
        name (str): Subject ID
        file (str): Path to hdf5 file - usually `{prefs.get('DATADIR')}/{self.name}.h5`
        current (dict): current task parameters. loaded from
            the 'current' :mod:`~tables.filenode` of the h5 file
        step (int): current step
        protocol_name (str): name of currently assigned protocol
        current_trial (int): number of current trial
        running (bool): Flag that signals whether the subject is currently running a task or not.
        data_queue (:class:`queue.Queue`): Queue to dump data while running task
        _thread (:class:`threading.Thread`): thread used to keep file open while running task
        did_graduate (:class:`threading.Event`): Event used to signal if the subject has graduated the current step
        STRUCTURE (list): list of tuples with order:

            * full path, eg. '/history/weights'
            * relative path, eg. '/history'
            * name, eg. 'weights'
            * type, eg. :class:`.Subject.Weight_Table` or 'group'

        node locations (eg. '/data') to types, either 'group' for groups or a
            :class:`tables.IsDescriptor` for tables.
    """
    _VERSION = 1



    def __init__(self,
                 name: str=None,
                 dir: Optional[Path] = None,
                 file: Optional[Path] = None,
                 structure: Subject_Structure = Subject_Structure()):
        """
        Args:
            name (str): subject ID
            dir (str): path where the .h5 file is located, if `None`, `prefs.get('DATADIR')` is used
            file (str): load a subject from a filename. if `None`, ignored.
            new (bool): if True, a new file is made (a new file is made if one does not exist anyway)
            biography (dict): If making a new subject file, a dictionary with biographical data can be passed
            structure (:class:`.Subject_Schema`): Structure to use with this subject.
        """

        self.structure = structure

        self._lock = threading.Lock()

        # --------------------------------------------------
        # Find subject .h5 file
        # --------------------------------------------------

        if file:
            file = Path(file)
            if not name:
                name = file.stem

        else:
            if not name:
                raise FileNotFoundError('Need to either pass a name or a file, how else would we find the .h5 file?')

            if dir:
                dir = Path(dir)
            else:
                dir = Path(prefs.get('DATADIR'))

            file = dir / (name + '.h5')

        self.name = name
        self.logger = init_logger(self)
        self.file = file

        # make sure we have the expected structure
        with self._h5f as h5f:
            self.structure.make(h5f)

        self._session_uuid = None

        # Is the subject currently running (ie. we expect data to be incoming)
        # Used to keep the subject object alive, otherwise we close the file whenever we don't need it
        self.running = False

        # We use a threading queue to dump data into a kept-alive h5f file
        self.data_queue = None
        self._thread = None
        self.did_graduate = threading.Event()

        with self._h5f as h5f:
            # Every time we are initialized we stash the git hash
            history_row = h5f.root.history.hashes.row
            history_row['time'] = self._get_timestamp()
            try:
                history_row['hash'] = prefs.get('HASH')
                # FIXME: less implicit way of getting hash plz
            except AttributeError:
                history_row['hash'] = ''
            history_row.append()

    @property
    @contextmanager
    def _h5f(self) -> tables.file.File:
        """
        Context manager for access to hdf5 file.

        Examples:

            with self._h5f as h5f:
                # ... do hdf5 stuff

        Returns:
            function wrapped with contextmanager that will open the hdf file
        """

        # @contextmanager
        # def _h5f_context() -> tables.file.File:
        with self._lock:
            try:
                h5f = tables.open_file(str(self.file), mode="r+")
                yield h5f
            finally:
                h5f.flush()
                h5f.close()
        # return _h5f_context()

    @property
    def info(self) -> Biography:
        """
        Subject biographical information

        Returns:
            dict
        """
        with self._h5f as h5f:
            info = h5f.get_node(self.structure.info.path)
            biodict = {}
            for k in info._v_attrs._f_list():
                biodict[k] = info._v_attrs[k]

        return Biography(**biodict)

    @property
    def protocol(self) -> Union[Protocol_Status, None]:
        with self._h5f as h5f:
            protocol = h5f.get_node(self.structure.protocol.path)
            protocoldict = {}
            for k in protocol._v_attrs._f_list():
                protocoldict[k] = protocol._v_attrs[k]

        if len(protocoldict) == 0:
            return None
        else:
            return Protocol_Status(**protocoldict)

    @protocol.setter
    def protocol(self, protocol:Protocol_Status):
        if self.protocol is not None and protocol.protocol != self.protocol.protocol:
            archive_name = f"{self._get_timestamp(simple=True)}_{self.protocol_name}"
            self._write_attrs('/history/past_protocols/' + archive_name, self.protocol.dict())
            self.logger.debug(f"Stashed old protocol details in {'/history/past_protocols/' + archive_name}")

        # check for differences
        diffs = []
        if self.protocol is None:
            diffs.append('protocol')
            diffs.append('step')
        else:
            if protocol.protocol_name != self.protocol_name:
                diffs.append('protocol')
            if protocol.step != self.step:
                diffs.append('step')

        for diff in diffs:
            if diff == 'protocol':
                self.update_history('protocol', protocol.protocol_name, value=protocol.protocol)
            elif diff == 'step':
                self.update_history('step', name=protocol.protocol[protocol.step]['step_name'],
                                    value=protocol.step)


        # make sure that we have the required protocol structure
        self._make_protocol_structure(protocol.protocol_name, protocol.protocol)

        with self._h5f as h5f:
            protocol_node = h5f.get_node(self.structure.protocol.path)
            for k, v in protocol.dict().items():
                protocol_node._v_attrs[k] = v

        self.logger.debug(f"Saved new protocol status {Protocol_Status}")

    @property
    def protocol_name(self) -> str:
        return self.protocol.protocol_name

    @property
    def current_trial(self) -> int:
        return self.protocol.current_trial

    @current_trial.setter
    def current_trial(self, current_trial:int):
        protocol = self.protocol
        protocol.current_trial = current_trial
        self.protocol = protocol

    @property
    def session(self) -> int:
        return self.protocol.session

    @session.setter
    def session(self, session: int):
        protocol = self.protocol
        protocol.session = session
        self.protocol = protocol

    @property
    def step(self) -> int:
        return self.protocol.step

    @step.setter
    def step(self, step: int):
        protocol = self.protocol
        protocol.step = step
        self.protocol = protocol

    @property
    def task(self) -> dict:
        return self.protocol.protocol[self.step]

    @property
    def session_uuid(self) -> str:
        if self._session_uuid is None:
            self._session_uuid = str(uuid.uuid4())
        return self._session_uuid

    @property
    def history(self) -> History:
        return self._read_table('/history/history', History)

    @property
    def hashes(self) -> Hashes:
        return self._read_table('/history/hashes', Hashes)

    @property
    def weights(self) -> Weights:
        return self._read_table('/history/weights', Weights)


    def _write_attrs(self, path: str, attrs:dict):
        with self._h5f as h5f:
            try:
                node = h5f.get_node(path)

            except tables.exceptions.NoSuchNodeError:
                pathpieces = path.split('/')
                parent = '/' + '/'.join(pathpieces[:-1])
                node = h5f.create_group(parent, pathpieces[-1],
                                     title=pathpieces[-1], createparents=True)
            for k, v in attrs.items():
                node._v_attrs[k] = v

            h5f.flush()

    def _read_table(self, path:str, table:typing.Type[Table]) -> typing.Union[Table,pd.DataFrame]:
        with self._h5f as h5f:
            tab = h5f.get_node(path).read() # type: np.ndarray

        # unpack table to a dataframe
        df = pd.DataFrame.from_records(tab)
        for col in df.columns:
            if df[col].dtype == 'O':
                df[col] = df[col].str.decode("utf-8")

        try:
            return table(**df.to_dict(orient='list'))
        except Exception as e:
            self.logger.exception(f"Could not make table from loaded data, returning dataframe")
            return df

    @classmethod
    def new(cls,
            bio:Biography,
            structure: Optional[Subject_Structure] = Subject_Structure(),
            path: Optional[Path] = None,
            ) -> 'Subject':
        """
        Create a new subject file, make its structure, and populate its :class:`~.data.models.biography.Biography` .


        Args:
            biography (:class:`~.data.models.biography.Biography`): A collection of biographical information
                about the subject! Stored as attributes within `/info`
            structure (Optional[:class:`~.models.subject.Subject_Structure`]): The structure of tables and groups to
                use when creating this Subject. **Note:** This is not currently saved with the subject file,
                so if using a nonstandard structure, it needs to be passed every time on init. Sorry!
            path (Optional[:class:`pathlib.Path`]): Path of created file. If ``None``, make a file within
                the ``DATADIR`` within the user directory (typically ``~/autopilot/data``) using the subject ID as the filename.
                (eg. ``~/autopilot/data/{id}.h5``)

        Returns:
            :class:`.Subject` , Newly Created.
        """
        if path is None:
            path = Path(prefs.get('DATADIR')).resolve() / (bio.id + '.h5')
        else:
            path = Path(path)
            assert path.suffix == '.h5'

        if path.exists():
            raise FileExistsError(f"A subject file for {bio.id} already exists at {path}!")

        # use the open_file command directly here because we use mode="w"
        h5f = tables.open_file(filename=str(path), mode='w')

        # make basic structure
        structure.make(h5f)

        info_node = h5f.get_node(structure.info.path)
        for k, v in bio.dict().items():
            info_node._v_attrs[k] = v

        # compatibility - double `id` as name
        info_node._v_attrs['name'] = bio.id
        h5f.root._v_attrs['VERSION'] = cls._VERSION

        h5f.close()

        return Subject(name=bio.id, file=path)


    def update_history(self, type, name:str, value:typing.Any, step=None):
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
        self.logger.info(f'Updating subject {self.name} history - type: {type}, name: {name}, value: {value}, step: {step}')

        # Make sure the updates are written to the subject file


        # Check that we're all strings in here
        if not isinstance(type, str):
            type = str(type)
        if not isinstance(name, str):
            name = str(name)
        if not isinstance(value, str):
            value = str(value)

        # log the change
        with self._h5f as h5f:
            history_row = h5f.root.history.history.row

            history_row['time'] = self._get_timestamp(simple=True)
            history_row['type'] = type
            history_row['name'] = name
            history_row['value'] = value
            history_row.append()


    def _find_protocol(self, protocol:typing.Union[Path, str, typing.List[dict]],
                       protocol_name: Optional[str]=None) -> typing.Tuple[str, typing.List[dict]]:
        """
        Resolve a protocol from a name, path, etc. into a list of dictionaries

        Returns:
            tuple of (protocol_name, protocol)
        """

        if isinstance(protocol, str):
            # check if it's just a json encoded dictionary
            try:
                protocol = json.loads(protocol)
            except json.decoder.JSONDecodeError:
                # try it as a path
                if not protocol.endswith('.json'):
                    protocol += '.json'
                protocol = Path(protocol)

        if isinstance(protocol, Path):
            if not protocol.exists():
                if protocol.is_absolute():
                    protocol = protocol.relative_to(prefs.get('PROTOCOLDIR'))
                else:
                    protocol = Path(prefs.get('PROTOCOLDIR')) / protocol
            if not protocol.exists():
                raise FileNotFoundError(f"Could not find protocol file {protocol}!")

            protocol_name = protocol.stem

            with open(protocol, 'r') as pfile:
                protocol = json.load(pfile)

        elif isinstance(protocol, list):
            if protocol_name is None:
                raise ValueError(f"If passed protocol as a list of dictionaries, need to also pass protocol_name")

        return protocol_name, protocol

    def _make_protocol_structure(self, protocol_name:str, protocol:typing.List[dict] ):
        """
        Use a :class:`.Protocol_Group` to make the necessary tables for the given protocol.
        """
        # make protocol structure!
        protocol_structure = Protocol_Group(
            protocol_name=protocol_name,
            protocol=protocol,
            structure=self.structure
        )
        with self._h5f as h5f:
            protocol_structure.make(h5f)

    def assign_protocol(self, protocol:typing.Union[Path, str, typing.List[dict]],
                        step_n:int=0,
                        protocol_name:Optional[str]=None):
        """
        Assign a protocol to the subject.

        If the subject has a currently assigned task, stashes it with :meth:`~.Subject.stash_current`

        Creates groups and tables according to the data descriptions in the task class being assigned.
        eg. as described in :class:`.Task.TrialData`.

        Updates the history table.

        Args:
            protocol (Path, str, dict): the protocol to be assigned. Can be one of

                * the name of the protocol (its filename minus .json) if it is in `prefs.get('PROTOCOLDIR')`
                * filename of the protocol (its filename with .json) if it is in the `prefs.get('PROTOCOLDIR')`
                * the full path and filename of the protocol.
                * The protocol dictionary serialized to a string
                * the protocol as a list of dictionaries

            step_n (int): Which step is being assigned?
            protocol_name (str): If passing ``protocol`` as a dict, have to give a name to the protocol
        """
        # Protocol will be passed as a .json filename in prefs.get('PROTOCOLDIR')

        protocol_name, protocol = self._find_protocol(protocol, protocol_name)

        # check if this is the same protocol as we already have so we don't reset session number
        if self.protocol is not None and (protocol_name == self.protocol_name) and (step_n == self.step):
            session = self.session
            current_trial = self.current_trial

            self.logger.debug("Keeping existing session and current_trial counts")
        else:
            session = 0
            current_trial = 0

        status = Protocol_Status(
            current_trial=current_trial,
            session=session,
            step=step_n,
            protocol=protocol,
            protocol_name=protocol_name,
        )
        # set current status (this will also stash any existing status and update the trial history tables as needed)

        self.protocol = status

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
        if self.current is None:
            e = RuntimeError('No task assigned to subject, cant prepare_run. use Subject.assign_protocol or protocol reassignment wizard in the terminal GUI')
            self.logger.exception(f"{e}")
            raise e

        # get step history
        try:
            step_df = self.history.to_df()
            step_df = step_df[step_df['type'] == 'step']
        except Exception as e:
            self.logger.exception(f"Couldnt get step history to trim data given to graduation objects, got exception {e}")
            step_df = None


        protocol_groups = Protocol_Group(
            protocol_name = self.protocol_name,
            protocol = self.protocol.protocol,
            structure = self.structure
        )
        group_name = protocol_groups.steps[self.step].path

        # Get current task parameters and handles to tables
        task_params = self.protocol.protocol[self.step]

        with self._h5f as h5f:
            # tasks without TrialData will have some default table, so this should always be present
            trial_table = h5f.get_node(group_name, 'trial_data')

            ##################################3
            # first try and find some timestamp column to filter past data we give to the graduation object
            # in case the subject has been stepped back down to a previous stage, for example
            slice_start = 0
            try:
                ts_cols = [col for col in trial_table.colnames if 'timestamp' in col]
                # just use the first timestamp column
                if len(ts_cols) > 0:
                    trial_ts = pd.DataFrame({'timestamp': trial_table.col(ts_cols[0])})
                    trial_ts['timestamp'] = pd.to_datetime(trial_ts['timestamp'].str.decode('utf-8'))
                else:
                    self.logger.warning(
                        'No timestamp column could be found in trial data, cannot trim data given to graduation objects')
                    trial_ts = None

                if trial_ts is not None and step_df is not None:
                    # see where, if any, the timestamp column is older than the last time the step was changed
                    good_rows = np.where(trial_ts['timestamp'] >= step_df['time'].iloc[-1])[0]
                    if len(good_rows) > 0:
                        slice_start = np.min(good_rows)
                    # otherwise if it's because we found no good rows but have trials,
                    # we will say not to use them, otherwise we say not to use them by
                    # slicing at the end of the table
                    else:
                        slice_start = trial_table.nrows

            except Exception as e:
                self.logger.exception(
                    f"Couldnt trim data given to graduation objects with step change history, got exception {e}")

            trial_tab = trial_table.read(start=slice_start)
            trial_tab_keys = tuple(trial_tab.dtype.fields.keys())

            ##############################

            # get last trial number and session
            try:
                self.current_trial = trial_tab['trial_num'][-1]+1
            except IndexError:
                if 'trial_num' not in trial_tab_keys:
                    self.logger.info('No previous trials detected, setting current_trial to 0')
                self.current_trial = 0

            # should have gotten session from current node when we started
            # so sessions increment over the lifespan of the subject, even if
            # reassigned.
            if not self.session:
                try:
                    self.session = trial_tab['session'][-1]
                except IndexError:
                    if 'session' not in trial_tab_keys:
                        self.logger.warning('previous session couldnt be found, setting to 0')
                    self.session = 0

            self.session += 1
            h5f.root.info._v_attrs['session'] = self.session
            h5f.flush()

            # prepare continuous data group and tables
            task_class = autopilot.get_task(task_params['task_type'])
            if hasattr(task_class, 'ContinuousData'):
                cont_group = h5f.get_node(group_name, 'continuous_data')
                try:
                    session_group = h5f.create_group(cont_group, "session_{}".format(self.session))
                except tables.NodeError:
                    pass # fine, already made it

            self.graduation = None
            if 'graduation' in task_params.keys():
                try:
                    grad_type = task_params['graduation']['type']
                    grad_params = task_params['graduation']['value'].copy()

                    # add other params asked for by the task class
                    grad_obj = autopilot.get('graduation', grad_type)

                    if grad_obj.PARAMS:
                        # these are params that should be set in the protocol settings
                        for param in grad_obj.PARAMS:
                            #if param not in grad_params.keys():
                            # for now, try to find it in our attributes
                            # but don't overwrite if it already has what it needs in case
                            # of name overlap
                            # TODO: See where else we would want to get these from
                            if hasattr(self, param) and param not in grad_params.keys():
                                grad_params.update({param:getattr(self, param)})

                    if grad_obj.COLS:
                        # these are columns in our trial table

                        # then give the data to the graduation object
                        for col in grad_obj.COLS:
                            try:
                                grad_params.update({col: trial_tab[col]})
                            except KeyError:
                                self.logger.warning('Graduation object requested column {}, but it was not found in the trial table'.format(col))

                    #grad_params['value']['current_trial'] = str(self.current_trial) # str so it's json serializable
                    self.graduation = grad_obj(**grad_params)
                    self.did_graduate.clear()
                except Exception as e:
                    self.logger.exception(f'Exception in graduation parameter specification, graduation is disabled.\ngot error: {e}')
            else:
                self.graduation = None


        # spawn thread to accept data
        self.data_queue = queue.Queue()
        self._thread = threading.Thread(target=self.data_thread, args=(self.data_queue,))
        self._thread.start()
        self.running = True

        # return a task parameter dictionary
        task = copy(self.protocol.protocol[self.step])
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
        with self._h5f as h5f:

            task_params = self.current[self.step]
            step_name = task_params['step_name']

            # file structure is '/data/protocol_name/##_step_name/tables'
            group_name = f"/data/{self.protocol_name}/S{self.step:02d}_{step_name}"
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
                                    self.logger.warning('no timestamp sent with continuous data')
                                    continue


                                cont_tables[k] = h5f.create_table(session_group, k, description={
                                    k: tables.Col.from_atom(col_atom),
                                    'timestamp': tables.Col.from_atom(timestamp_atom)
                                })

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
                                self.logger.warning('Found multiple rows with same trial_num: {}'.format(data['trial_num']))
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
                                self.logger.warning("Data dropped: key: {}, value: {}".format(k, v))

                    # TODO: Or if all the values have been filled, shouldn't need explicit TRIAL_END flags
                    if 'TRIAL_END' in data.keys():
                        trial_row['session'] = self.session
                        if self.graduation:
                            # set our graduation flag, the terminal will get the rest rolling
                            did_graduate = self.graduation.update(trial_row)
                            if did_graduate is True:
                                self.did_graduate.set()
                        trial_row.append()
                        trial_table.flush()

                    # always flush so that our row iteration routines above will find what they're looking for
                    trial_table.flush()
                except Exception as e:
                    # we shouldn't throw any exception in this thread, just log it and move on
                    self.logger.exception(f'exception in data thread: {e}')

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
        self._thread.join(5)
        self.running = False
        if self._thread.is_alive():
            self.logger.warning('Data thread did not exit')

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
        with self._h5f as h5f:
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

        return return_data

    def _get_timestamp(self, simple=False):
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

        with self._h5f as h5f:
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

        with self._h5f as h5f:
            weight_table = h5f.root.history.weights
            # there should only be one matching row since it includes seconds
            for row in weight_table.where('date == b"{}"'.format(date)):
                row[col_name] = new_value
                row.update()


    def update_weights(self, start=None, stop=None):
        """
        Store either a starting or stopping mass.

        `start` and `stop` can be passed simultaneously, `start` can be given in one
        call and `stop` in a later call, but `stop` should not be given before `start`.

        Args:
            start (float): Mass before running task in grams
            stop (float): Mass after running task in grams.
        """
        with self._h5f as h5f:
            if start is not None:
                weight_row = h5f.root.history.weights.row
                weight_row['date'] = self._get_timestamp(simple=True)
                weight_row['session'] = self.session
                weight_row['start'] = float(start)
                weight_row.append()
            elif stop is not None:
                # TODO: Make this more robust - don't assume we got a start weight
                h5f.root.history.weights.cols.stop[-1] = stop
            else:
                self.logger.warning("Need either a start or a stop weight")

    def graduate(self):
        """
        Increase the current step by one, unless it is the last step.
        """
        if len(self.current)<=self.step+1:
            self.logger.warning('Tried to graduate from the last step!\n Task has {} steps and we are on {}'.format(len(self.current), self.step+1))
            return

        # increment step, update_history should handle the rest
        step = self.step+1
        name = self.current[step]['step_name']
        self.update_history('step', name, step)

