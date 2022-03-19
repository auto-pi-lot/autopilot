"""
Test interface methods for using abstract data structures with pytables
"""
import pdb

import pytest
import uuid
from pathlib import Path
from typing import List

from datetime import datetime

import tables

from autopilot.data.modeling.base import Table
from autopilot.data.interfaces.tables import model_to_table, table_to_model
from autopilot.data.models.protocol import Protocol_Group

class TEST_TABLE(Table):
    booly: List[bool]
    inty: List[int]
    floaty: List[float]
    stringy: List[str]
    bytey: List[bytes]
    datey: List[datetime]

class TEST_DESCRIPTION(tables.IsDescription):
    booly = tables.BoolCol()
    inty = tables.Int64Col()
    floaty = tables.Float64Col()
    stringy = tables.StringCol(1024)
    bytey = tables.StringCol(1024)
    datey = tables.StringCol(1024)

TEST_PROTOCOL = [
    {
        "allow_repeat": True,
        "graduation": {
            "type": "NTrials",
            "value": {
                "n_trials": "100",
                "type": "NTrials"
            }
        },
        "reward": 10,
        "step_name": "Free_Water",
        "task_type": "Free_Water"
    },
    {
        "bias_mode": "None",
        "correction": True,
        "graduation": {
            "type": "Accuracy",
            "value": {
                "threshold": ".99",
                "type": "Accuracy",
                "window": "1000"
            }
        },
        "punish_dur": 20,
        "punish_stim": True,
        "req_reward": True,
        "reward": 10,
        "step_name": "Nafc",
        "stim": {
            "sounds": {
                "L": [
                    {
                        "amplitude": "0.1",
                        "duration": "100",
                        "frequency": "1000",
                        "type": "Tone"
                    }
                ],
                "R": [
                    {
                        "amplitude": "0.1",
                        "duration": "100",
                        "frequency": "2000",
                        "type": "Tone"
                    }
                ]
            },
            "tag": "Sounds",
            "type": "sounds"
        },
        "task_type": "Nafc"
    }
]

@pytest.fixture()
def h5file():
    path = Path.home() / (str(uuid.uuid4()) + '.h5')
    try:
        h5f = tables.open_file(str(path), 'w')
        yield h5f
    finally:
        h5f.close()
        path.unlink()


def test_model_to_table():
    """
    Test that a data model can create a pytables description
    """

    table_converted = model_to_table(TEST_TABLE)

    assert table_converted.columns == TEST_DESCRIPTION.columns

    method_converted = TEST_TABLE.to_pytables_description()

    assert method_converted.columns == TEST_DESCRIPTION.columns

def _compare_fields(tab1, tab2):
    # bytes are always string columns, so they're degenerate to pytables and always
    # get converted to str
    t1fields = tab1.__fields__.copy()
    t2fields = tab2.__fields__.copy()
    skipfields = ('bytey', 'datey')
    assert len(t1fields) == len(t2fields)
    for key, field in t1fields.items():
        if key in skipfields:
            continue
        assert field.type_ == t2fields[key].type_

def test_table_to_model():
    """Test making a TrialTable from a pytables description"""
    model = table_to_model(TEST_DESCRIPTION, Table)
    _compare_fields(model, TEST_TABLE)

    method_converted = Table.from_pytables_description(TEST_DESCRIPTION)
    _compare_fields(method_converted, TEST_TABLE)

def test_protocol_group(h5file):
    """
    Test that a protocol group is correctly made from a protocol dictionary
    """
    pgroup = Protocol_Group(protocol_name='TEST_PROCOTOL', protocol=TEST_PROTOCOL)

    pgroup.make(h5file)
    test_tables = ['/data/TEST_PROCOTOL/S00_Free_Water/trial_data', '/data/TEST_PROCOTOL/S01_Nafc/trial_data']

    # just check that one of the default columsn is present because that means we should have the rest!
    for tab in test_tables:
        tabnode = h5file.get_node(tab)
        assert isinstance(tabnode, tables.table.Table)
        assert hasattr(tabnode.cols, 'session_uuid')


