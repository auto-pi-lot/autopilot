import tables

from autopilot.data.interfaces.tables import H5F_Table


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


