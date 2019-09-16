"""
Module to hold module-global variables as preferences.

Warning:
    DO NOT hardcode prefs here.

A prefs.json file should be generated with an appropriate :mod:`autopilot.setup` routine

Before importing any other autopilot module,

Examples:

    from autopilot import prefs
    prefs_file = '/usr/autopilot/prefs.json' # or some .json prefs file
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
    Initialize prefs on autopilot start.

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

    # Load any calibration data
    cal_path = os.path.join(prefs['BASEDIR'], 'port_calibration_fit.json')
    cal_raw = os.path.join(prefs['BASEDIR'], 'port_calibration.json')

    #TODO: make fit calibration update if new calibration results received
    # aka check if dates in raw results are more recent than date in a 'info' field, for example
    if os.path.exists(cal_path):
        with open(cal_path, 'r') as calf:
            cal_fns = json.load(calf)

        prefs['PORT_CALIBRATION'] = cal_fns
    elif os.path.exists(cal_raw):
        # aka raw calibration results exist but no fit has been computed
        luts = compute_calibration(path=cal_raw, do_return=True)
        with open(cal_path, 'w') as calf:
            json.dump(luts, calf)
        prefs['PORT_CALIBRATION'] = luts



    ###########################

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


def compute_calibration(path=None, calibration=None, do_return=False):

    # FIXME: UGLY HACK - move this function to another module
    import pandas as pd
    from scipy.stats import linregress

    if not calibration:
        # if we weren't given calibration results, load them
        if path:
            open_fn = path
        else:
            open_fn = "/usr/autopilot/port_calibration.json"

        with open(open_fn, 'r') as open_f:
            calibration = json.load(open_f)

    luts = {}
    for port, samples in calibration.items():
        sample_df = pd.DataFrame(samples)
        # TODO: Filter for only most recent timestamps

        # volumes are saved in mL because of how they are measured, durations are stored in ms
        # but reward volumes are typically in the uL range, so we make the conversion
        # by multiplying by 1000
        line_fit = linregress((sample_df['vol'] / sample_df['n_clicks']) * 1000., sample_df['dur'])
        luts[port] = {'intercept': line_fit.intercept,
                      'slope': line_fit.slope}

    # write to file, overwriting any previous
    if do_return:
        return luts

    else:
        # do write
        lut_fn = os.path.join(prefs.BASEDIR, 'port_calibration_fit.json')
        with open(lut_fn, 'w') as lutf:
            json.dump(luts, lutf)





#######################3
##########################
# SECTION OF NOT HARDCODED PARAMS
# null values of params that every agent should have
if 'AGENT' not in globals().keys():
    add('AGENT', '')

