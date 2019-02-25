"""
Module to hold module-global variables as preferences.

Warning:
    DO NOT hardcode prefs here.

A prefs.json file should be generated with an appropriate :mod:`rpilot.setup` routine

Before importing any other RPilot module,

Examples:

    from rpilot import prefs
    prefs_file = '/usr/rpilot/prefs.json' # or some .json prefs file
    prefs.init(prefs_file)

And to add a pref

Examples:
    prefs.add('PARAM', 'VALUE")
"""

# this is strictly a placeholder module to
# allow global access to prefs without explicit passing.
#
# DO NOT hardcode prefs here. only add placeholder values for certain 'universal' params
#
# A prefs.json file should be generated with an appropriate setup routine
# (see setup dir)
# then you should call prefs.init(prefs.json) if the if __name__=="__main__" block

import json
import subprocess
import os

prefdict = {}
"""
stores a dictionary of preferences that mirrors the global variables.
"""

def init(fn):
    """
    Initialize prefs on rpilot start.

    Args:
        fn (str, dict): a path to `prefs.json` or a dictionary of preferences
    """
    if isinstance(fn, basestring):
        with open(fn, 'r') as pfile:
            prefs = json.load(pfile)
    elif isinstance(fn, dict):
        prefs = fn

    try:
        assert(isinstance(prefs, dict))
    except AssertionError:
        print(prefs)
        Exception('prefs must return a dict')

    # Get the current git hash
    prefs['HASH'] = git_version(prefs['REPODIR'])

    global prefdict

    # assign key values to module globals so can access with prefs.pref1
    for k, v in prefs.items():
        globals()[k] = v
        prefdict[k] = v

    # also store as a dictionary so other modules can have one if they want it
    globals()['__dict__'] = prefs

def add(param, value):
    """
    Add a pref after init

    Args:
        param (str): Allcaps parameter name
        value: Value of the pref
    """
    globals()[param] = value

    global prefdict
    prefdict[param] = value

# Return the git revision as a string
def git_version(repo_dir):
    """
    Get the git hash of the current commit.

    Stolen from `numpy's setup <https://github.com/numpy/numpy/blob/master/setup.py#L70-L92>`_

    and linked by ryanjdillon on `SO <https://stackoverflow.com/a/40170206>`_


    Args:
        repo_dir (str): directory of the git repository.

    Returns:
        unicode: git commit hash.
    """
    def _minimal_ext_cmd(cmd):
        # type: (List[str]) -> str
        # construct minimal environment
        env = {}
        for k in ['SYSTEMROOT', 'PATH']:
            v = os.environ.get(k)
            if v is not None:
                env[k] = v
        # LANGUAGE is used on win32
        env['LANGUAGE'] = 'C'
        env['LANG'] = 'C'
        env['LC_ALL'] = 'C'
        out = subprocess.Popen(cmd, stdout = subprocess.PIPE, env=env).communicate()[0]
        return out

    try:
        out = _minimal_ext_cmd(['git','-C',repo_dir, 'rev-parse', 'HEAD'])
        GIT_REVISION = out.strip().decode('ascii')
    except OSError:
        GIT_REVISION = "Unknown"

    return GIT_REVISION



#######################3
##########################
# SECTION OF NOT HARDCODED PARAMS
# null values of params that every agent should have
if 'AGENT' not in globals().keys():
    add('AGENT', '')

