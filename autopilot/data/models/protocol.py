import typing
from typing import Optional, Type

import tables
from pydantic import Field, create_model
import pandas as pd

import autopilot
from autopilot.root import Autopilot_Type
from autopilot.data.interfaces.tables import H5F_Group, H5F_Table
from autopilot.data.modeling.base import Table, Schema
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
    continuous_group: Optional[H5F_Group] = None

    def __init__(self,
                 step: int,
                 group_path: str,
                 step_dict: Optional[dict] = None,
                 step_name: Optional[str] = None,
                 trial_data: Optional[Type[Trial_Data]] = None,
                 **data):
        self._init_logger()
        if step_name is None and step_dict is None:
            raise ValueError('Need to give us something that will let us identify where to make this table!')

        if step_name is None:
            step_name = step_dict['step_name']

        if trial_data is None and step_dict:

            task_class = autopilot.get_task(step_dict['task_type'])
            if hasattr(task_class, 'TrialData'):
                trial_data = task_class.TrialData
                if issubclass(trial_data, tables.IsDescription):
                    self._logger.warning("Using pytables descriptions as TrialData is deprecated! Update to the pydantic TrialData model! Converting to TrialData class")
                    trial_data = Trial_Data.from_pytables_description(trial_data)

            else:
                trial_data = Trial_Data
        else:
            trial_data = Trial_Data

        # complete table decription with any stim parameters
        if step_dict and 'stim' in step_dict.keys():
            trial_data = self._make_stim_descriptors(step_dict['stim'], trial_data)

        # make group descriptions and children to prepare for ``make``
        group_name = f"S{step:02d}_{step_name}"
        path = '/'.join([group_path, group_name])

        continuous_group = H5F_Group(path='/'.join([path, 'continuous_data']))
        trial_table = H5F_Table(path='/'.join([path, 'trial_data']),
                                description=trial_data.to_pytables_description(),
                                title='Trial Data')

        super().__init__(
            path = path,
            step_name = step_name,
            step = step,
            trial_data = trial_data,
            continuous_group = continuous_group,
            children = [trial_table, continuous_group],
            **data
        )


    def _make_stim_descriptors(self, stim:dict, trial_data: Type[Trial_Data]) -> Type[Trial_Data]:
        if 'groups' in stim.keys():
            # managers have stim nested within groups, but this is still really ugly
            sound_params = {}
            for g in stim['groups']:
                for side, sounds in g['sounds'].items():
                    for sound in sounds:
                        for k, v in sound.items():
                            if k in STRING_PARAMS:
                                sound_params[k] = (str, ...)
                            else:
                                sound_params[k] = (float, ...)

        elif 'sounds' in stim.keys():
            # for now we just assume they're floats
            sound_params = {}
            for side, sounds in stim['sounds'].items():
                # each side has a list of sounds
                for sound in sounds:
                    for k, v in sound.items():
                        if k in STRING_PARAMS:
                            sound_params[k] = (str, ...)
                        else:
                            sound_params[k] = (float, ...)

        else:
            raise ValueError(f'Dont know how to handle stim like {stim}')

        trial_data = create_model('Trial_Data', __base__ = trial_data, **sound_params)
        return trial_data



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
    tabs: typing.List[H5F_Table]
    steps: typing.List[Step_Group]

    def __init__(self,
                 protocol_name: str,
                 protocol: typing.List[dict],
                 **data):
        """
        Override default __init__ method to populate a task's groups

        """
        path = f'/data/{protocol_name}'
        steps = []
        _tables = []

        for i, step in enumerate(protocol):
            step_group = Step_Group(step=i, group_path=path, step_dict=step)
            steps.append(step_group)

        super().__init__(
            path=path,
            protocol_name=protocol_name,
            protocol=protocol,
            tabs=_tables,
            steps=steps,
            children=steps,
            **data)

class Step_Data(Schema):
    """
    Schema for storing data for a single step of a protocol
    """
    task: Task_Params
    trial_data_table: Table
    trial_data: Trial_Data
    continuous_data: typing.Dict[str, list]

class Protocol_Data(Schema):
    steps: typing.List[Step_Data]
