from datetime import datetime
import typing
from typing import Type
import tables

from autopilot.data.interfaces.tables import H5F_Group, H5F_Table
from autopilot.data.modeling.base import Table, Group, Schema, Attributes
from autopilot.data.models.biography import Biography


class History(Table):
    """
    Table to describe parameter and protocol change history

    Attributes:
        time (str): timestamps
        type (str): Type of change - protocol, parameter, step
        name (str): Name - Which parameter was changed, name of protocol, manual vs. graduation step change
        value (str): Value - What was the parameter/protocol/etc. changed to, step if protocol.
    """
    time: datetime
    type: str
    name: str
    value: str
#
#
# class Hashes(Table):
#     """
#     Table to track changes in version over time
#
#     Attributes:
#         time (str): Timestamps for entries
#         hash (str): Hash of the currently checked out commit of the git repository.
#         version (str): Current Version of autopilot, if not run from a cloned repository
#         id (str): ID of the agent whose hash we are stashing (we want to keep track of all connected agents, ideally
#
#     """
#     time: Type =  datetime
#     hash: Type =  str
#     version: Type =  str
#     id: Type =  str
#
#
# class Weights(Table):
#     """
#     Class to describe table for weight history
#
#     Attributes:
#         start (float): Pre-task mass
#         stop (float): Post-task mass
#         date (str): Timestamp in simple format
#         session (int): Session number
#     """
#     start: Type = float
#     stop: Type  = float
#     date: Type  = datetime
#     session: Type  = int
#
#
# class History_Group(Group):
#     """
#     Group for collecting subject history tables
#     """
#     history: Table = History()
#     hashes: Table = Hashes()
#     weights: Table = Weights()
#     past_protocols: Group = Group()
#
#
# class Subject_Schema(Schema):
#     """
#     Structure of the :class:`.Subject` class's hdf5 file
#
#     .. todo::
#
#         Convert this into an abstract representation of data rather than literally hdf5 tables
#
#     """
#     info: Biography = Biography()
#     data: Group = Group(kwargs={'filters':tables.Filters(complevel=6, complib='blosc:lz4')})
#     history: History_Group = History_Group()
#



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


class _Hash_Table(H5F_Table):
    def __init__(self, **data):
        super().__init__(description=Hash_Table, **data)


class _History_Table(H5F_Table):
    def __init__(self, **data):
        super().__init__(description=History_Table, **data)


class _Weight_Table(H5F_Table):
    def __init__(self, **data):
        super().__init__(description=Weight_Table, **data)



class Subject_Structure(Schema):
    """
    Structure of the :class:`.Subject` class's hdf5 file
    """
    info = H5F_Group(path='/info', title="Subject Biographical Information")
    data = H5F_Group(path='/data', filters=tables.Filters(complevel=6, complib='blosc:lz4'))
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