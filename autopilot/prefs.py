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
from collections import OrderedDict as odict

prefdict = {}
"""
stores a dictionary of preferences that mirrors the global variables.
"""

INITIALIZED = False

def init(fn=None):
    """
    Initialize prefs on autopilot start.

    Args:
        fn (str, dict): a path to `prefs.json` or a dictionary of preferences
    """
    if isinstance(fn, str):
        with open(fn, 'r') as pfile:
            prefs = json.load(pfile)
    elif isinstance(fn, dict):
        prefs = fn
    elif fn is None:
        # try to load from default location
        autopilot_wayfinder = os.path.join(os.path.expanduser('~'), '.autopilot')
        if os.path.exists(autopilot_wayfinder):
            with open(autopilot_wayfinder, 'r') as wayfinder_f:
                fn = os.path.join(wayfinder_f.read(), 'prefs.json')
        else:
            fn = os.path.join(os.path.expanduser('~'), 'autopilot', 'prefs.json')

        if not os.path.exists(fn):
            # tried to load defaults, return quietly
            return

        with open(fn, 'r') as pfile:
            prefs = json.load(pfile)

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

    globals()['INITIALIZED'] = True

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
        # type: (list[str]) -> str
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
    """

    Args:
        path:
        calibration:
        do_return:

    Returns:

    """
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
        lut_fn = os.path.join(globals()['BASEDIR'], 'port_calibration_fit.json')
        with open(lut_fn, 'w') as lutf:
            json.dump(luts, lutf)





#######################3
##########################
# SECTION OF NOT HARDCODED PARAMS
# null values of params that every agent should have
if 'AGENT' not in globals().keys():
    add('AGENT', '')

add('AUTOPILOT_ROOT', os.path.dirname(os.path.abspath(__file__)))

if not INITIALIZED:
    init()
#
# HARDWARE_PREFS = odict({
#             'HARDWARE':{
#                 'POKES':{
#                     'L':self.add(nps.TitleText, name="HARDWARE - POKES - L", value="24"),
#                     'C': self.add(nps.TitleText, name="HARDWARE - POKES - C", value="8"),
#                     'R': self.add(nps.TitleText, name="HARDWARE - POKES - R", value="10"),
#                 },
#                 'LEDS': {
#                     'L': self.add(nps.TitleText, name="HARDWARE - LEDS - L", value="[11, 13, 15]"),
#                     'C': self.add(nps.TitleText, name="HARDWARE - LEDS - C", value="[22, 18, 16]"),
#                     'R': self.add(nps.TitleText, name="HARDWARE - LEDS - R", value="[19, 21, 23]"),
#                 },
#                 'PORTS': {
#                     'L': self.add(nps.TitleText, name="HARDWARE - PORTS - L", value="31"),
#                     'C': self.add(nps.TitleText, name="HARDWARE - PORTS - C", value="33"),
#                     'R': self.add(nps.TitleText, name="HARDWARE - PORTS - R", value="37"),
#                 },
#                 'FLAGS': {
#                     'L': self.add(nps.TitleText, name="HARDWARE - FLAGS - L", value=""),
#                     'R': self.add(nps.TitleText, name="HARDWARE - FLAGS - R", value="")
#                 }},
#             'PULLUPS': self.add(nps.TitleText, name="Pins to pull up on boot",
#                                 value="[7]"),
#             'PULLDOWNS': self.add(nps.TitleText, name="Pins to pull down on boot",
#                                   value="[]"),
#     'AUDIO':{
#         'AUDIOSERVER': self.add(nps.TitleSelectOne, max_height:4, "default": [0, ], name: "Audio Server:", "default"
# s: ["jack", "pyo", "none"], scroll_exit: True},
#
# 'NCHANNELS'  : {"text": "N Audio Channels", "default": "1"},
#     'OUTCHANNELS': {"text": "List of output ports for jack audioserver to connect to", "default": "[1]"},
#     'FS'         : {"text": "Audio Sampling Rate", "default": "192000"},
#     'JACKDSTRING': {"text"   : "Command used to launch jackd - note that \'fs\' will be replaced with above FS",
#                     "default": "jackd -P75 -p16 -t2000 -dalsa -dhw:sndrpihifiberry -P -rfs -n3 -s &"},
#     }
# })
#
# PILOT_PREFS = BASE_PREFS
# PILOT_PREFS.update(odict({
#     'PIGPIOMASK' : {"text":"Binary mask to enable pigpio to access pins according to the BCM numbering", "default":"1111110000111111111111110000"},
#                           }))
#
# TERMINAL_PREFS = BASE_PREFS

