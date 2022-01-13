import pytest
from pathlib import Path
from autopilot.prefs import _DEFAULTS, Scopes, get, set
from autopilot.external import start_jackd

@pytest.fixture
def default_dirs():
    for k, v in _DEFAULTS.items():
        if v['scope'] == Scopes.DIRECTORY and 'default' in v.keys():
            Path(v['default']).mkdir(parents=True, exist_ok=True)


@pytest.fixture(scope='session')
def jack_server():
    pass

