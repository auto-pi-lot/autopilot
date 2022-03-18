"""
Test interface methods for using abstract data structures with pytables
"""

from datetime import datetime

import tables

from autopilot.data.modeling.base import Table
from autopilot.data.interfaces.tables import model_to_table

class TEST_TABLE(Table):
    booly: bool
    inty: int
    floaty: float
    stringy: str
    bytey: bytes
    datey: datetime

class TEST_DESCRIPTION(tables.IsDescription):
    booly = tables.BoolCol()
    inty = tables.Int64Col()
    floaty = tables.Float64Col()
    stringy = tables.StringCol(1024)
    bytey = tables.StringCol(1024)
    datey = tables.StringCol(1024)


def test_model_to_table():
    """
    Test that a data model can create a pytables description
    """

    table_converted = model_to_table(TEST_TABLE)

    assert table_converted.columns == TEST_DESCRIPTION.columns

    method_converted = TEST_TABLE.to_pytables_description()

    assert method_converted.columns == TEST_DESCRIPTION.columns

