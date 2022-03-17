"""
Test the subject data interface
"""
from pathlib import Path

from autopilot.data.models import biography
from autopilot.data.subject import Subject
from autopilot import prefs

from .fixtures import dummy_biography

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





