"""
Module to hold module-global variables as preferences.

todo::

    JONNY THIS NEEDS TO BE TOTALLY REWRITTEN

    Should different scopes get different handlers, eg. directories can ensure they exist and handle creation of
    subsequent files? or is that one foot into overengineering hell?


A prefs.json file should be generated with an appropriate :mod:`autopilot.setup` routine

Before importing any other autopilot module,

Examples:

    from autopilot import prefs
    prefs_file = '~/autopilot/prefs.json' # or some .json prefs file
    prefs.init(prefs_file)

And to add a pref

Examples:
    prefs.add('PARAM', 'VALUE")

Warning:
    These are **not** hard coded prefs. :data:`_DEFAULTS` populates the *default* values for prefs, but local prefs are
    always restored from and saved to ``prefs.json`` . If you're editing this file and things aren't changing,
    you're in the wrong place!
"""

# this is strictly a placeholder module to
# allow global access to prefs without explicit passing.
#
# DO NOT hardcode prefs here. only add placeholder values for certain 'universal' params
#
# A prefs.json file should be generated with an appropriate setup routine
# (see setup dir)
# then you should call prefs.init(prefs.json) if the if __name__=="__main__" block

# Prefs is a top-level module! It shouldn't depend on anything else in Autopilot,
# and if it does, it should carefully import it where it is needed!
# (prefs needs to be possible to import everywhere, including eg. in setup_autopilot)

import json
import subprocess
import multiprocessing as mp
import os
import logging
import typing
from pathlib import Path
from ctypes import c_bool
from enum import Enum, auto

#from autopilot.core.loggers import init_logger
from collections import OrderedDict as odict

class Scopes(Enum):
    """
    Enum that lists available scopes and groups for prefs

    Scope can be an agent type, common (for everyone), or specify some
    subgroup of prefs that should be presented together (like directories)

    COMMON = All Agents
    DIRECTORY = Prefs group for specifying directory structure
    TERMINAL = prefs for Terminal Agents
    Pilot = Prefs for Pilot agents
    LINEAGE = prefs for networking lineage (until networking becomes more elegant ;)
    AUDIO = Prefs for configuring the Jackd audio server


    """
    COMMON = auto()
    TERMINAL = auto()
    PILOT = auto()
    DIRECTORY = auto()
    LINEAGE = auto()
    AUDIO = auto()




_PREF_MANAGER = mp.Manager() # type: mp.Manager
"""
The :class:`multiprocessing.Manager` that stores prefs during system operation and makes them available
and consistent across processes.
"""

_PREFS = _PREF_MANAGER.dict() # type: dict
"""
stores a dictionary of preferences that mirrors the global variables.
"""

_LOGGER = None # type: typing.Union[logging.Logger, None]
"""
Logger used by prefs initialized by :func:`.core.loggers.init_logger`

Initially None, created once prefs are populated because init_logger requires some prefs to be set (uh the logdir and level and stuff)
"""

_INITIALIZED = mp.Value(c_bool, False) # type: mp.Value
"""
Boolean flag to indicate whether prefs have been initialzied from ``prefs.json``
"""

_LOCK = mp.Lock()
"""
:class:`multiprocessing.Lock` to control access to ``prefs.json``
"""

# not documenting, just so that the full function doesn't need to be put in for each directory
# lol at this literal reanimated fossil halfway evolved between os.path and pathlib
_basedir = Path(os.path.join(os.path.expanduser("~"), "autopilot"))


_DEFAULTS = odict({
    'NAME': {
        'type': 'str',
        "text": "Agent Name:",
        "scope": Scopes.COMMON
    },
    'PUSHPORT': {
        'type': 'int',
        "text": "Push Port - Router port used by the Terminal or upstream agent:",
        "default": "5560",
        "scope": Scopes.COMMON
    },
    'MSGPORT': {
        'type': 'int',
        "text": "Message Port - Router port used by this agent to receive messages:",
        "default": "5565",
        "scope": Scopes.COMMON
    },
    'TERMINALIP': {
        'type': 'str',
        "text": "Terminal IP:",
        "default": "192.168.0.100",
        "scope": Scopes.COMMON
    },
    'LOGLEVEL': {
        'type': 'choice',
        "text": "Log Level:",
        "choices": ("DEBUG", "INFO", "WARNING", "ERROR"),
        "default": "WARNING",
        "scope": Scopes.COMMON
    },
    'LOGSIZE': {
        'type': 'int',
        "text": "Size of individual log file (in bytes)",
        "default": 5 * (2 ** 20),  # 50MB
        "scope": Scopes.COMMON
    },
    'LOGNUM': {
        'type': 'int',
        "text": "Number of logging backups to keep of LOGSIZE",
        "default": 4,
        "scope": Scopes.COMMON
    },
    # 4 * 5MB = 20MB per module
    'CONFIG': {
        'type': 'list',
        "text": "System Configuration",
        'hidden': True,
        "scope": Scopes.COMMON
    },
    'BASEDIR': {
        'type': 'str',
        "text": "Base Directory",
        "default": str(_basedir),
        "scope": Scopes.DIRECTORY
    },
    'DATADIR': {
        'type': 'str',
        "text": "Data Directory",
        "default": str(_basedir / 'data'),
        "scope": Scopes.DIRECTORY
    },
    'SOUNDDIR': {
        'type': 'str',
        "text": "Sound file directory",
        "default": str(_basedir / 'sounds'),
        "scope": Scopes.DIRECTORY
    },
    'LOGDIR': {
        'type': 'str',
        "text": "Log Directory",
        "default": str(_basedir / 'logs'),
        "scope": Scopes.DIRECTORY
    },
    'VIZDIR': {
        'type': 'str',
        "text": "Directory to store Visualization results",
        "default": str(_basedir / 'viz'),
        "scope": Scopes.DIRECTORY
    },
    'PROTOCOLDIR': {
        'type': 'str',
        "text": "Protocol Directory",
        "default": str(_basedir / 'protocols'),
        "scope": Scopes.DIRECTORY
    },
    'PLUGINDIR': {
        'type': 'str',
        "text": "Directory to import ",
        "default": os.path.join(os.path.expanduser("~"), "autopilot"),
        "scope": Scopes.DIRECTORY
    },
    'PIGPIOMASK': {
        'type': 'str',
        'text': 'Binary mask controlling which pins pigpio controls according to their BCM numbering, see the -x parameter of pigpiod',
        'default': "1111110000111111111111110000",
        "scope": Scopes.PILOT
    },
    'PIGPIOARGS': {
        'type': 'str',
        'text': 'Arguments to pass to pigpiod on startup',
        'default': '-t 0 -l',
        "scope": Scopes.PILOT
    },
    'PULLUPS': {
        'type': 'list',
        'text': 'Pins to pull up on system startup? (list of form [1, 2])',
        "scope": Scopes.PILOT
    },
    'PULLDOWNS': {
        'type': 'list',
        'text': 'Pins to pull down on system startup? (list of form [1, 2])',
        "scope": Scopes.PILOT
    },
    'DRAWFPS': {
        'type': 'int',
        "text": "FPS to draw videos displayed during acquisition",
        "default": "20",
        "scope": Scopes.TERMINAL
    },
    'PILOT_DB': {
        'type': 'str',
        'text': "filename to use for the .json pilot_db that maps pilots to subjects (relative to BASEDIR)",
        "default": str(_basedir / "pilot_db.json"),
        "scope": Scopes.TERMINAL
    },
    'LINEAGE': {
        'type': 'choice',
        "text": "Are we a parent or a child?",
        "choices": ("NONE", "PARENT", "CHILD"),
        "scope": Scopes.LINEAGE
    },
    'CHILDID': {
        'type': 'str',
        "text": "Child ID:",
        "depends": ("LINEAGE", "PARENT"),
        "scope": Scopes.LINEAGE
    },
    'PARENTID': {
        'type': 'str',
        "text": "Parent ID:",
        "depends": ("LINEAGE", "CHILD"),
        "scope": Scopes.LINEAGE
    },
    'PARENTIP': {
        'type': 'str',
        "text": "Parent IP:",
        "depends": ("LINEAGE", "CHILD"),
        "scope": Scopes.LINEAGE
    },
    'PARENTPORT': {
        'type': 'str',
        "text": "Parent Port:",
        "depends": ("LINEAGE", "CHILD"),
        "scope": Scopes.LINEAGE
    },
    'AUDIOSERVER': {
        'type': 'bool',
        'text': 'Enable jack audio server?',
        "scope": Scopes.AUDIO
    },
    'NCHANNELS': {
        'type': 'int',
        'text': "Number of Audio channels",
        'default': 1,
        'depends': 'AUDIOSERVER',
        "scope": Scopes.AUDIO
    },
    'OUTCHANNELS': {
        'type': 'list',
        'text': 'List of Audio channel indexes to connect to',
        'default': '[1]',
        'depends': 'AUDIOSERVER',
        "scope": Scopes.AUDIO
    },
    'FS': {
        'type': 'int',
        'text': 'Audio Sampling Rate',
        'default': 192000,
        'depends': 'AUDIOSERVER',
        "scope": Scopes.AUDIO
    },
    'JACKDSTRING': {
        'type': 'str',
        'text': 'Arguments to pass to jackd, see the jackd manpage',
        'default': 'jackd -P75 -p16 -t2000 -dalsa -dhw:sndrpihifiberry -P -rfs -n3 -s &',
        'depends': 'AUDIOSERVER',
        "scope": Scopes.AUDIO
    },

})
"""
Ordered Dictionary containing default values for prefs.

An Ordered Dictionary lets the prefs be displayed in gui elements in a predictable order, but prefs are stored in ``prefs.json`` in
alphabetical order and the 'live' prefs used during runtime are stored in :data:`._PREFS`

Each entry should be a dict with the following structure::

    "PREF_NAME": {
        "type": (str, int, bool, choice, list) # specify the appropriate GUI input, str or int are validators, 
        choices are a 
            # dropdown box, and lists allow users to specify lists of values like "[0, 1]"
        "default": If possible, assign default value, otherwise None
        "text": human-readable text that described the pref
        "scope": to whom does this pref apply? see :class:`.Scopes`
        "depends": name of another pref that needs to be supplied/enabled for this one to be enabled (eg. don't set sampling rate of audio server if audio server disabled)
            can also be specified as a tuple like ("LINEAGE", "CHILD") that enables the option when prefs[depends[0]] == depends[1]
        "choices": If type=="choice", a tuple of available choices.
    }
"""



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

    global _PREFS

    # assign key values to module globals so can access with prefs.pref1
    for k, v in prefs.items():
        globals()[k] = v
        _PREFS[k] = v

    # also store as a dictionary so other modules can have one if they want it
    globals()['__dict__'] = prefs

    globals()['_INITIALIZED'] = True

def add(param, value):
    """
    Add a pref after init

    Args:
        param (str): Allcaps parameter name
        value: Value of the pref
    """
    globals()[param] = value

    global _PREFS
    _PREFS[param] = value

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

if not _INITIALIZED:
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

