from datetime import datetime
import typing
from typing import Type, List, Union
import tables
from pydantic import Field, validator


from autopilot.data.interfaces.tables import H5F_Group, H5F_Table
from autopilot.data.modeling.base import Table, Group, Schema, Attributes
from autopilot.data.models.biography import Biography
from autopilot.data.models.protocol import Protocol_Data

class History(Table):
    """
    Table to describe parameter and protocol change history

    Attributes:
        time (str): timestamps
        type (str): Type of change - protocol, parameter, step
        name (str): Name - Which parameter was changed, name of protocol, manual vs. graduation step change
        value (str): Value - What was the parameter/protocol/etc. changed to, step if protocol.
    """
    time: List[datetime]
    type: List[str]
    name: List[str]
    value: List[Union[str, List[dict]]]

    @validator('time', each_item=True, allow_reuse=True, pre=True)
    def simple_time(cls, v):
        return datetime.strptime(v, '%y%m%d-%H%M%S')


class Hashes(Table):
    """
    Table to track changes in version over time

    Attributes:
        time (str): Timestamps for entries
        hash (str): Hash of the currently checked out commit of the git repository.
        version (str): Current Version of autopilot, if not run from a cloned repository
        id (str): ID of the agent whose hash we are stashing (we want to keep track of all connected agents, ideally

    """
    time: List[datetime]
    hash:  List[str]
    version: List[str]
    id: List[str]


class Weights(Table):
    """
    Class to describe table for weight history

    Attributes:
        start (float): Pre-task mass
        stop (float): Post-task mass
        date (str): Timestamp in simple format
        session (int): Session number
    """
    start: List[float]
    stop: List[float]
    date: List[datetime]
    session: List[int]

    @validator('date', each_item=True, allow_reuse=True, pre=True)
    def simple_time(cls, v):
        return datetime.strptime(v, '%y%m%d-%H%M%S')

class History_Group(Group):
    """
    Group for collecting subject history tables
    """
    history: History
    hashes:  Hashes
    weights: Weights
    past_protocols: Group

class Protocol_Status(Attributes):
    current_trial: int
    session: int
    step: int
    protocol: typing.List[dict]
    protocol_name: str
    assigned: datetime = Field(default_factory=datetime.now)






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

        Convert this into an abstract representation of data rather than literally hdf5 tables

    """
    info: Biography
    data: Protocol_Data
    protocol: Protocol_Status
    past_protocols: List[Protocol_Status]
    history: History_Group


