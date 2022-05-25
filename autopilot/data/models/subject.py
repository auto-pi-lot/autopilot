"""
Data models used by the :class:`.Subject` class
"""

from datetime import datetime
import typing
from typing import Type, List, Union, Optional
import tables
from pydantic import Field, validator


from autopilot.data.interfaces.tables import H5F_Group, H5F_Table
from autopilot.data.modeling.base import Table, Group, Schema, Attributes
from autopilot.data.models.biography import Biography
from autopilot.data.models.protocol import Protocol_Data

class History(Table):
    """
    Table to describe parameter and protocol change history
    """
    time: List[datetime]
    """Timestamps for history changes"""
    type: List[str]
    """Type of change - protocol, parameter, step"""
    name: List[str]
    """Which parameter was changed, name of protocol, manual vs. graduation step change"""
    value: List[Union[str, List[dict]]]
    """What was the parameter/protocol/etc. changed to, step if protocol."""

    @validator('time', each_item=True, allow_reuse=True, pre=True)
    def simple_time(cls, v):
        return datetime.strptime(v, '%y%m%d-%H%M%S')


class Hashes(Table):
    """
    Table to track changes in version over time
    """
    time: List[datetime]
    """Timestamps for entries"""
    hash:  List[str]
    """Hash of the currently checked out commit of the git repository."""
    version: List[str]
    """Current Version of autopilot, if not run from a cloned repository"""
    id: List[str]
    """ID of the agent whose hash we are stashing (we want to keep track of all connected agents, ideally"""


class Weights(Table):
    """
    Class to describe table for weight history
    """
    start: List[float]
    """Pre-task mass"""
    stop: List[float]
    """Post-task mass"""
    date: List[datetime]
    """Timestamp of task start"""
    session: List[int]
    """Session number"""

    @validator('date', each_item=True, allow_reuse=True, pre=True)
    def simple_time(cls, v):
        return datetime.strptime(v, '%y%m%d-%H%M%S')

class History_Group(Group):
    """
    Group for collecting subject history tables.

    Typically stored in ``/history`` in the subject .h5f file
    """
    history: History
    hashes:  Hashes
    weights: Weights
    past_protocols: Group

class Protocol_Status(Attributes):
    """
    Status of assigned protocol. Accessible from the :attr:`.Subject.protocol` getter/setter

    See :meth:`.Subject.assign_protocol`.
    """
    current_trial: int
    """Current or last trial that was run in the particular level of the protocol. Continues to increment across sessions, resets across different levels of the protocol."""
    session: int
    """Session number. Increments every time the subject is run."""
    step: int
    """Current step of the protocol that the subject is running."""
    protocol: typing.List[dict]
    """The full definition of the steps (individual tasks) that define the protocol"""
    protocol_name: str
    """Name of the assigned protocol, typically the filename this protocol is stored in minus .json"""
    pilot: Optional[str] = Field(None, description="Pilot that this subject runs on")
    """The ID of the pilot that this subject does their experiment on"""
    assigned: datetime = Field(default_factory=datetime.now)
    """The time that this protocol was assigned. If not passed explicitly, generated each time the protocol status is changed."""






class _Hash_Table(H5F_Table):
    def __init__(self, **data):
        super().__init__(description=Hashes.to_pytables_description(), **data)


class _History_Table(H5F_Table):
    def __init__(self, **data):
        super().__init__(description=History.to_pytables_description(), **data)


class _Weight_Table(H5F_Table):
    def __init__(self, **data):
        super().__init__(description=Weights.to_pytables_description(), **data)





class Subject_Structure(Schema):
    """
    Structure of the :class:`.Subject` class's hdf5 file
    """
    info = H5F_Group(path='/info', title="Subject Biographical Information")
    data = H5F_Group(path='/data', filters=tables.Filters(complevel=6, complib='blosc:lz4'))
    protocol = H5F_Group(path='/protocol', title="Metadata for the currently assigned protocol")
    history = H5F_Group(path='/history', children=[
        H5F_Group(path='/history/past_protocols', title='Past Protocol Files'),
        _Hash_Table(path='/history/hashes', title="Git commit hash history"),
        _History_Table(path='/history/history', title="Change History"),
        _Weight_Table(path='/history/weights', title="Subject Weights")
    ])

    def make(self, h5f:tables.file.File):
        """
        Make all the nodes!

        Args:
            h5f (:class:`tables.file.File`): The h5f file to make the groups in!
        """
        for _, node in self._iter():
            node.make(h5f)



class Subject_Schema(Schema):
    """
    Structure of the :class:`.Subject` class's hdf5 file

    .. todo::

        Convert this into an abstract representation of data rather than literally hdf5 tables.

        At the moment twins :class:`.Subject_Structure`

    """
    info: Biography
    data: Protocol_Data
    protocol: Protocol_Status
    past_protocols: List[Protocol_Status]
    history: History_Group


