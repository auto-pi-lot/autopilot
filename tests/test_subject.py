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

def test_history():
    """
    We correctly store changes in step, protocol, in the history table and can retreive them
    """

def test_hashes():
    """
    We store the correct hash of the running code when installed from source, or else we
    correctly store the version when installed from a wheel
    """

def test_weights():
    """
    We can store weights at the beginning and end of a session
    """

def test_prepare_run():
    """
    We can prepare to run our task
    * returning the task parameters
    """
    pass

def test_session_persistence():
    """
    Test that we increment session across prepared runs and correctly keep track of the current_trial_parameter
    """
    pass

def test_save_load_data():
    """
    We are able to iteratively save data from a task, correctly keeping track of rows, and then load it back to a correctly
    typed DataFrame. We also are able to cleanly stop storing data and then use the subject object afterwards
    """

def test_log_dropped_data():
    """
    Test that if we drop data because of not being in the trial table that it's always logged,
    """

def test_out_of_order():
    """
    We are able to receive trial data out of order, when properly addressed with a trial_num, without overwriting
    existing data, and without making a ton of empty cells
    """

def test_increment_trial():
    """
    When we increment trial, we do so, and prefill the next row with boilerplate variables.
    """

def test_no_overwrite_with_no_current_trial():
    """
    When we aren't given a correct current trial, we shouldn't overwrite any data, because
    we only consider writing to existing rows with a matching uuid
    Returns:

    """

def test_create_continuous_column():
    """
    We are able to make columns on the fly to store continuous data as well as timestamps
    """

def test_graduation_filtration():
    """
    After assigning steps out of order, test that we correctly filter data given to the graduation object
    """

def test_get_data_no_plugin():
    """
    We are able to load data from the subject even when we no longer have the plugin source in the plugin directory
    ie. the subject file is autonomous of any code but the subject class.
    """







