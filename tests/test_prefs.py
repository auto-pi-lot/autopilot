import pytest
import warnings
import os

from autopilot import prefs
from autopilot.exceptions import DefaultPrefWarning

@pytest.fixture(scope='function')
def clean_prefs(request):
    """
    Clear and stash prefs, restore on finishing
    """
    existing_prefs = prefs._PREFS._getvalue().copy()
    prefs._PREFS = prefs._PREF_MANAGER.dict()

    def restore_prefs():
        for k, v in existing_prefs.items():
            prefs._PREFS[k] = v

    request.addfinalizer(restore_prefs)


@pytest.mark.parametrize('default_pref', [(k, v) for k, v in prefs._DEFAULTS.items()])
def test_prefs_defaults(default_pref, clean_prefs):

    if 'default' in default_pref[1].keys():
        assert prefs.get(default_pref[0]) == default_pref[1]['default']
    else:
        assert prefs.get(default_pref[0]) is None



@pytest.mark.parametrize('default_pref', [(k, v) for k, v in prefs._DEFAULTS.items()])
def test_prefs_warnings(default_pref, clean_prefs):
    """
    Test that getting a default pref warns once and only once
    """
    os.environ['AUTOPILOT_WARN_DEFAULTS'] = '1'

    if 'default' in default_pref[1].keys():
        # if we have a default...
        # first make sure that it's not in the "warned" list
        try:
            prefs._WARNED.remove(default_pref[0])
        except ValueError:
            pass


        with pytest.warns(DefaultPrefWarning, match='Returning default prefs') as record:
            # warn when first getting, should warn
            assert prefs.get(default_pref[0]) == default_pref[1]['default']
            # get again, should only emit one warning
            assert prefs.get(default_pref[0]) == default_pref[1]['default']

        # filter to just default warnings
        _warns = [r.category == DefaultPrefWarning for r in record]
        assert sum(_warns) == 1

    del os.environ['AUTOPILOT_WARN_DEFAULTS']


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
