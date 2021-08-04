import pytest
import warnings

from autopilot import prefs

@pytest.mark.parametrize('default_pref', [(k, v) for k, v in prefs._DEFAULTS.items()])
def test_prefs_defaults(default_pref):

    # make sure that we didnt' actually load anything from some phantom uh prefs file idk

    # if prefs._INITIALIZED.value:
    #     warnings.warn('prefs was initialized, so defaults could not be tested')
    #     return
    # save any existing set prefs to restore at the end
    existing_prefs = prefs._PREFS._getvalue().copy()
    prefs._PREFS = prefs._PREF_MANAGER.dict()

    if 'default' in default_pref[1].keys():
        with pytest.warns(UserWarning):
            assert prefs.get(default_pref[0]) == default_pref[1]['default']
    else:
        assert prefs.get(default_pref[0]) is None

    # restore
    for k, v in existing_prefs.items():
        prefs._PREFS[k] = v


def test_prefs_deprecation():
    """
    If there is a string in the ``'deprecation'`` field of a pref in `_DEFAULTS`,
    a warning is raised printing the string.
    """

    # add a fake deprecated pref
    prefs._DEFAULTS['DEPRECATEME'] = {
        'type': 'int',
        "text": "A pref that was born just to die",
        "default": 4,
        "scope": prefs.Scopes.COMMON,
        'deprecation': 'This pref will be DECIMATED i mean DEPRECATED in a future version'
    }

    with pytest.warns(FutureWarning):
        pref_val = prefs.get('DEPRECATEME')

    assert pref_val == 4
