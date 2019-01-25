# this is strictly a placeholder module to
# allow global access to prefs without explicit passing.
#
# DO NOT hardcode prefs here.
#
# A prefs.json file should be generated with an appropriate setup routine
# (see setup dir)
# then you should call prefs.init(prefs.json) if the if __name__=="__main__" block

import json
import subprocess
import os

prefdict = None

def init(fn):
    """
    Args:
        fn:
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
    prefs['HASH'] = git_version()

    # assign key values to module globals so can access with prefs.pref1
    for k, v in prefs.items():
        globals()[k] = v

    # also store as a dictionary so other modules can have one if they want it
    globals()['__dict__'] = prefs

def add(param, value):
    globals()[param] = value

# Return the git revision as a string
def git_version():
    # Stolen from numpy's setup https://github.com/numpy/numpy/blob/master/setup.py#L70-L92
    # and linked by ryanjdillon on SO https://stackoverflow.com/a/40170206
    def _minimal_ext_cmd(cmd):
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
        out = _minimal_ext_cmd(['git', 'rev-parse', 'HEAD'])
        GIT_REVISION = out.strip().decode('ascii')
    except OSError:
        GIT_REVISION = "Unknown"

    return GIT_REVISION




