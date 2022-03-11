import typing
from abc import abstractmethod
from typing import Optional

import tables

import autopilot
from autopilot import Autopilot_Type
from autopilot.stim.sound.sounds import STRING_PARAMS


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


class Hash_Table(tables.IsDescription):
    """
    Class to describe table for hash history

    Attributes:
        time (str): Timestamps
        hash (str): Hash of the currently checked out commit of the git repository.
    """
    time = tables.StringCol(256)
    hash = tables.StringCol(40)


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


class H5F_Node(Autopilot_Type):
    """
    Base class for H5F Nodes
    """
    path:str
    title:Optional[str]=''
    filters:Optional[tables.filters.Filters]=None
    attrs:Optional[dict]=None

    @property
    def parent(self) -> str:
        """
        The parent node under which this node hangs.

        Eg. if ``self.path`` is ``/this/is/my/path``, then
        parent will be ``/this/is/my``

        Returns:
            str
        """
        return '/'.join(self.path.split('/')[:-1])

    @property
    def name(self) -> str:
        """
        Our path without :attr:`.parent`

        Returns:
            str
        """
        return self.path.split('/')[-1]

    @abstractmethod
    def make(self, h5f:tables.file.File):
        """
        Abstract method to make whatever this node is
        """

    class Config:
        arbitrary_types_allowed = True


class H5F_Group(H5F_Node):
    """
    Description of a pytables group and its location
    """

    def make(self, h5f:tables.file.File):
        """
        Make the group, if it doesn't already exist.

        If it exists, do nothing

        Args:
            h5f (:class:`tables.file.File`): The file to create the table in
        """

        try:
            node = h5f.get_node(self.path)
            # if no exception, already exists
            if not isinstance(node, tables.group.Group):
                raise ValueError(f'{self.path} already exists, but it isnt a group! instead its a {type(node)}')
        except tables.exceptions.NoSuchNodeError:
            group = h5f.create_group(self.parent, self.name,
                             title=self.title, createparents=True,
                             filters=self.filters)
            if self.attrs is not None:
                group._v_attrs.update(self.attrs)


class H5F_Table(H5F_Node):
    description: tables.description.MetaIsDescription
    expectedrows:int=10000

    def make(self,  h5f:tables.file.File):
        """
        Make this table according to its description

        Args:
            h5f (:class:`tables.file.File`): The file to create the table in
        """
        try:
            node = h5f.get_node(self.path)
            if not isinstance(node, tables.table.Table):
                raise ValueError(f'{self.path} already exists, but it isnt a Table! instead its a {type(node)}')
        except tables.exceptions.NoSuchNodeError:
            tab = h5f.create_table(self.parent, self.name, self.description,
                             title=self.title, filters=self.filters,
                             createparents=True,expectedrows=self.expectedrows)
            if self.attrs is not None:
                tab._v_attrs.update(self.attrs)

    class Config:
        fields = {'description': {'exclude': True}}


class _Hash_Table(H5F_Table):
    def __init__(self, **data):
        super().__init__(description=Hash_Table, **data)


class _History_Table(H5F_Table):
    def __init__(self, **data):
        super().__init__(description=History_Table, **data)


class _Weight_Table(H5F_Table):
    def __init__(self, **data):
        super().__init__(description=Weight_Table, **data)


class Subject_Structure(Autopilot_Type):
    """
    Structure of the :class:`.Subject` class's hdf5 file
    """
    data = H5F_Group(path='/data', filters=tables.Filters(complevel=6, complib='blosc:lz4'))
    history = H5F_Group(path='/history')
    past_protocols = H5F_Group(path='/history/past_protocols', title='Past Protocol Files')
    info = H5F_Group(path='/info', title="Biographical Info")
    hashes = _Hash_Table(path = '/history/hashes', title="Git commit hash history")
    history_table = _History_Table(path = '/history/history', title="Change History")
    weight_table = _Weight_Table(path = '/history/weights', title= "Subject Weights")

    def make(self, h5f:tables.file.File):
        """
        Make all the nodes!

        Args:
            h5f (:class:`tables.file.File`): The h5f file to make the groups in!
        """
        for _, node in self.dict():
            node.make(h5f)


class Protocol_Group(H5F_Group):
    """
    The group and subgroups for a given protocol.

    For each protocol, a main group is created that has the name of the protocol,
    and then subgroups are created for each of its steps.

    Within each step group, a table is made for TrialData, and tables are created
    as-needed for continuous data.

    For Example::

        / data
        |--- protocol_name
            |--- S##_step_name
            |   |--- trial_data
            |   |--- continuous_data
            |--- ... additional steps

    .. todo::

        Also make a Step group... what's the matter with ya.

    """
    protocol_name: str
    protocol: typing.List[dict]
    groups: typing.List[H5F_Group]
    tabs: typing.List[H5F_Table]
    steps: typing.List[H5F_Group]
    trial_tabs: typing.List[H5F_Table]

    def __init__(self,
                 protocol_name: str,
                 protocol: typing.List[dict],
                 structure:Subject_Structure=Subject_Structure(),
                 **data):
        """
        Override default __init__ method to populate a task's groups

        A custom :class:`.Subject_Structure` can be passed if a nonstandard layout
        is being used. Groups will be created beneath :attr:`.Subject_Structure.data`

        """
        path = '/'.join([structure.data.path, protocol_name])
        groups = []
        steps = []
        trial_tabs = []
        _tables = []

        for i, step in enumerate(protocol):
            # group for this step
            step_name = step['step_name']
            group_name = f"S{i:02d}_{step_name}"
            group_path = '/'.join([path, group_name])
            group = H5F_Group(path=group_path)
            groups.append(group)
            steps.append(group)

            # group for continuous data
            groups.append(H5F_Group(path='/'.join([group_path, 'continuous_data'])))

            # make trialData table if present
            task_class = autopilot.get_task(step['task_type'])
            if hasattr(task_class, 'TrialData'):
                trial_tab = self._trial_table(
                    trial_descriptor=task_class.TrialData,
                    step=step, group_path=group_path
                )

            else:
                class BaseDescriptor(tables.IsDescription):
                    session = tables.Int32Col()
                    trial_num = tables.Int32Col()

                trial_tab = self._trial_table(
                    trial_descriptor=BaseDescriptor,
                    step=step, group_path=group_path
                )
            _tables.append(trial_tab)
            trial_tabs.append(trial_tab)

        super().__init__(
            protocol_name=protocol_name,
            protocol=protocol,
            groups=groups,
            tabs=_tables,
            steps=steps,
            trial_tabs=trial_tabs,
            **data)

    def make(self, h5f:tables.file.File):
        for group in self.groups:
            group.make(h5f)
        for tab in self.tabs:
            tab.make(h5f)

    def _trial_table(self, trial_descriptor:tables.IsDescription, step, group_path) -> H5F_Table:
        # add a session column, everyone needs a session column
        if 'session' not in trial_descriptor.columns.keys():
            trial_descriptor.columns.update({'session': tables.Int32Col()})
        # same thing with trial_num
        if 'trial_num' not in trial_descriptor.columns.keys():
            trial_descriptor.columns.update({'trial_num': tables.Int32Col()})
        if 'stim' in step.keys():
            trial_descriptor = self._make_stim_descriptors(step['stim'], trial_descriptor)

        return H5F_Table(path='/'.join([group_path, 'trial_data']),
                         description=trial_descriptor)

    def _make_stim_descriptors(self, stim:dict, descriptor:tables.IsDescription) -> tables.IsDescription:
        # FIXME: this sucks. fix when tasks and stimuli have better models.
        if 'groups' in stim.keys():
            # managers have stim nested within groups, but this is still really ugly
            sound_params = {}
            for g in stim['groups']:
                for side, sounds in g['sounds'].items():
                    for sound in sounds:
                        for k, v in sound.items():
                            if k in STRING_PARAMS:
                                sound_params[k] = tables.StringCol(1024)
                            else:
                                sound_params[k] = tables.Float64Col()
            descriptor.columns.update(sound_params)

        elif 'sounds' in stim.keys():
            # for now we just assume they're floats
            sound_params = {}
            for side, sounds in stim['sounds'].items():
                # each side has a list of sounds
                for sound in sounds:
                    for k, v in sound.items():
                        if k in STRING_PARAMS:
                            sound_params[k] = tables.StringCol(1024)
                        else:
                            sound_params[k] = tables.Float64Col()
            descriptor.columns.update(sound_params)

        return descriptor