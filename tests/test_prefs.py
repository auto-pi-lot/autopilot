import warnings

import pytest


from autopilot import prefs

@pytest.mark.parametrize('default_pref', [(k, v) for k, v in prefs._DEFAULTS.items()])
def test_prefs_defaults(default_pref):

    # make sure that we didnt' actually load anything from some phantom uh prefs file idk
    if prefs._INITIALIZED.value:
        warnings.warn('prefs was initialized, so defaults could not be tested')
        return

    if 'default' in default_pref[1].keys():
        with pytest.warns(UserWarning):
            assert prefs.get(default_pref[0]) == default_pref[1]['default']
    else:
        assert prefs.get(default_pref[0]) is None

