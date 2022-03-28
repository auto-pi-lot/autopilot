"""
Test the subject data interface
"""
from pathlib import Path
import json
import pdb

import pytest

from autopilot.data.models import biography, subject as subject_model
from autopilot.data.subject import Subject
from autopilot import prefs

from .fixtures import dummy_biography, default_dirs, dummy_protocol, dummy_protocol_file

def test_new(dummy_biography: biography.Biography, default_dirs):
    """
    Test that we can make a new file from dummy biography and default structure
    """
    out_path = Path(prefs.get('DATADIR')).resolve() / (dummy_biography.id + '.h5')
    if out_path.exists():
        out_path.unlink()

    assert not out_path.exists()

    sub = Subject.new(dummy_biography)

    assert out_path.exists()
    assert sub.info == dummy_biography

    out_path.unlink()

@pytest.fixture
def dummy_subject(dummy_biography) -> Subject:
    sub = Subject.new(dummy_biography)
    yield sub
    sub.file.unlink()



def test_assign(dummy_subject:Subject, dummy_protocol_file:Path):
    """
    Test that a protocol can be assigned to a subject who previously does not have a protocol assigned
    """
    protocol_name = dummy_protocol_file.stem
    dummy_subject.assign_protocol(protocol_name)

    with open(dummy_protocol_file, 'r') as pfile:
        protocol_list = json.load(pfile)

    prot_status = subject_model.Protocol_Status(
        current_trial = 0,
        session = 0,
        step = 0,
        protocol = protocol_list,
        protocol_name = protocol_name
    )

    assigned_dict = dummy_subject.protocol.dict()
    del assigned_dict['assigned']

    made_dict = prot_status.dict()
    del made_dict['assigned']

    assert assigned_dict == made_dict

    # ensure we logged this in the history table
    history = dummy_subject.history.dict()
    assert history['type'] == ['protocol', 'step']
    assert str(protocol_list) == history['value'][0]
    assert '0' == history['value'][1]





