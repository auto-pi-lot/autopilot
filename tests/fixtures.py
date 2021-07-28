import pytest
from pathlib import Path
from autopilot.prefs import _DEFAULTS, Scopes

@pytest.fixture
def default_dirs():
    for k, v in _DEFAULTS.items():
        if v['scope'] == Scopes.DIRECTORY and 'default' in v.keys():
            Path(v['default']).mkdir(parents=True, exist_ok=True)

