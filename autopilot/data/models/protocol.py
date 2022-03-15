import typing

import tables

import autopilot
from autopilot.data.interfaces.tables import H5F_Group, H5F_Table
from autopilot.data.subject import Subject_Structure
from autopilot.stim.sound.sounds import STRING_PARAMS


class Step_Group(H5F_Group):
    """
    An hdf5 group for an individual step within a protocol.
    """



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
                 structure: Subject_Structure = Subject_Structure(),
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