import pytest

from autopilot import prefs

@pytest.mark.parametrize('default_pref', [(k, v) for k, v in prefs._DEFAULTS.items()])
def test_prefs_defaults(default_pref):

    # make sure that we didnt' actually load anything from some phantom uh prefs file idk
    assert not prefs._INITIALIZED.value

    if hasattr(default_pref[1], 'default'):
        assert prefs.get(default_pref[0]) == default_pref[1]['default']
    else:
        assert prefs.get(default_pref[0]) is None

