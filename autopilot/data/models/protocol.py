import typing
from typing import Optional, Type

import tables
from pydantic import Field

import autopilot
from autopilot.root import Autopilot_Type
from autopilot.data.interfaces.tables import H5F_Group, H5F_Table
from autopilot.data.modeling.base import Table
# from autopilot.data.models.subject import Subject_Schema
from autopilot.stim.sound.sounds import STRING_PARAMS

class Task_Params(Autopilot_Type):
    """
    Metaclass for storing task parameters
    """

class Trial_Data(Table):
    """
    Base class for declaring trial data.

    Tasks should subclass this and add any additional parameters that are needed.
    The subject class will then use this to create a table in the hdf5 file.
    """
    group: str = Field(..., description="Path of the parent step group")
    session: int = Field(..., description="Current training session, increments every time the task is started")
    session_uuid: str = Field(..., description="Each session gets a unique uuid, regardless of the session integer, to enable independent addressing of sessions when session numbers might overlap (eg. reassignment)")
    trial_num: int = Field(..., description="Trial data is grouped within, well, trials, which increase (rather than resetting) across sessions within a task")



class Step_Group(H5F_Group):
    """
    An hdf5 group for an individual step within a protocol.

    Typically this is populated by passing a step number and a dictionary of step parameters.
    """
    step_name: str
    step: int
    path: str
    trial_data: Optional[Type[Trial_Data]] = Trial_Data
    continuous_data: Optional[H5F_Group] = None

    def __init__(self,
                 step: int,
                 step_dict: Optional[dict] = None,
                 step_name: Optional[str] = None,
                 trial_data: Optional[Type[Trial_Data]] = None,
                 group_path: Optional[str] = '/data'):
        if step_name is None and step_dict is None:
            raise ValueError('Need to give us something that will let us identify where to make this table!')

        if step_name is not None:
            step_name = step_dict['step_name']

        if trial_data is None and step_dict:

            task_class = autopilot.get_task(step_dict['task_type'])
            if hasattr(task_class, 'TrialData'):
                trial_data = task_class.TrialData
            else:
                trial_data = Trial_Data
        else:
            trial_data = Trial_Data

        # complete table decription with any stim parameters
        if step_dict and 'stim' in step_dict.keys():
            trial_data = self._make_stim_descriptors(step_dict['stim'], trial_data)

        group_name = f"S{step:02d}_{step_name}"
        path = '/'.join([group_path, group_name])

        continuous_group = H5F_Group(path='/'.join([path, 'continuous_data']))



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







    def make(self):
        pass


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
    steps: typing.List[Step_Group]
    trial_tabs: typing.List[H5F_Table]

    def __init__(self,
                 protocol_name: str,
                 protocol: typing.List[dict],
                 **data):
        """
        Override default __init__ method to populate a task's groups

        """
        path = '/data'
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


