"""
Module to hold module-global variables as preferences.

Upon import, prefs attempts to import a ``prefs.json`` file from the default location (see :func:`.prefs.init` ).

Prefs are then accessed with :func:`.prefs.get` and :func:`.prefs.set` functions. After initialization, if a pref if ``set``,
it is stored in the ``prefs.json`` file -- prefs are semi-durable and persist across sessions.

When attempting to get a pref that is not set, :func:`.prefs.get` will first try to find a default value (set in
:data:`._PREFS` , and if none is found return ``None`` -- accordingly
no prefs should be intentionally set to None, as it signifies that the pref is not set.

Prefs are thread- and process-safe, as they are stored and served by a :class:`multiprocessing.Manager` object.

``prefs.json`` is typically generated by running :mod:`autopilot.setup.setup_autopilot` , though you can freestyle it
if you are so daring.

The **``HARDWARE``** pref is a little special. It specifies how each of the :mod:`.hardware` components connected to the system
is configured. It is a dictionary with this general structure::

    'HARDWARE': {
        'GROUP': {
            'ID': {
                'hardware_arg': 'val'
            }
        }
    }

where there are user-named ``'GROUPS'`` of hardware objects, like ``'LEDS'`` , etc. Within a group, each object has its
``'ID'`` (passed as the ``name`` argument to the hardware initialization method) which allows it to be identified from
the other components in the group. The intention of this structure is to allow multiple categories of hardware objects
to be parameterized and used separately, even though they might be the same object type. Eg. we may have three LEDs
in our nosepokes, but also have an LED that serves at the arena light. If we wanted to write a command that turns off all
LEDs, we would have to explicitly specify their IDs, making it difficult to re-use very common hardware command patterns
within tasks. There are obvious drawbacks to this scheme -- clunky, ambiguous, etc. and will be deprecated as parameterization
continues to congeal across the library.

The class that each element is used with is determined by the :attr:`.Task.HARDWARE`
dictionary. Specifically, the :meth:`.Task.init_hardware` method does something like::

    self.hardware['GROUP']['ID'] = self.HARDWARE['GROUP']['ID'](**prefs.get('HARDWARE')['GROUP']['ID'])


Warning:
    These are **not** hard coded prefs. :data:`_DEFAULTS` populates the *default* values for prefs, but local prefs are
    always restored from and saved to ``prefs.json`` . If you're editing this file and things aren't changing,
    you're in the wrong place!

This iteration of prefs with respect to work done on the `People's Ventilator Project <https://www.peoplesvent.org/en/latest/pvp.common.prefs.html>`_

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
import sys
import types
from pathlib import Path
from ctypes import c_bool
from enum import Enum, auto
import warnings

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
    COMMON = auto() #: All agents
    TERMINAL = auto() #: Prefs specific to Terminal Agents
    PILOT = auto() #: Prefs specific to Pilot Agents
    DIRECTORY = auto() #: Directory structure
    LINEAGE = auto() #: Prefs for coordinating network between pilots and children
    AUDIO = auto() #: Audio prefs...




_PREF_MANAGER = mp.Manager() # type: mp.managers.SyncManager
"""
The :class:`multiprocessing.Manager` that stores prefs during system operation and makes them available
and consistent across processes.
"""

_PREFS = _PREF_MANAGER.dict() # type: mp.managers.SyncManager.dict
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

_LOCK = mp.Lock() # type: mp.Lock
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
    'VENV': {
        'type': 'str',
        'text': 'Location of virtual environment, if used.',
        "scope": Scopes.COMMON,
        "default": sys.prefix if hasattr(sys, 'real_prefix') or (sys.base_prefix != sys.prefix) else False
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
    'REPODIR': {
       'type': 'str',
       'text': 'Location of Autopilot repo/library',
        'default': Path(__file__).resolve().parents[1],
        "scope": Scopes.DIRECTORY
    },
    'CALIBRATIONDIR': {
        'type': 'str',
        'text': 'Location of calibration files for solenoids, etc.',
        'default': str(_basedir / 'calibration'),
        'scope': Scopes.DIRECTORY
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
    'PING_INTERVAL': {
        'type': 'float',
        'text': 'How many seconds should pilots wait in between pinging the Terminal?',
        'default': 5,
        'scope': Scopes.PILOT
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
    'TERMINAL_SETTINGS_FN':{
        'type': 'str',
        'text': 'filename to store QSettings file for Terminal',
        'default': str(_basedir / "terminal.conf"),
        "scope": Scopes.TERMINAL
    },
    'TERMINAL_WINSIZE_BEHAVIOR': {
        'type': 'choice',
        'text': 'Strategy for resizing terminal window on opening',
        "choices": ('remember', 'moderate', 'maximum', 'custom'),
        "default": "remember",
        "scope": Scopes.TERMINAL    
    },
    'TERMINAL_CUSTOM_SIZE': {
        'type': 'list',
        'text': 'Custom size for window, specified as [px from left, px from top, width, height]',
        'default': [0, 0, 1000, 400],
        'depends': ('TERMINAL_WINSIZE_BEHAVIOR', 'custom'),
        'scope': Scopes.TERMINAL
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


def get(key: typing.Union[str, None] = None):
    """
    Get a pref!

    If a value for the given ``key`` can't be found, prefs will attempt to

    Args:
        key (str, None): get pref of specific ``key``, if ``None``, return all prefs

    Returns:
        value of pref (type variable!), or ``None`` if no pref of passed ``key``
    """

    # if nothing is requested of us, return everything
    if key is None:
        return globals()['_PREFS']._getvalue()

    else:
        # try to get the value from the prefs manager
        try:
            return globals()['_PREFS'][key]

        # if none exists...
        except KeyError:
            # try to get a default value
            try:
                default_val = globals()['_DEFAULTS'][key]['default']
                warnings.warn(f'Returning default prefs value {key} : {default_val} (ideally this shouldnt happen and everything should be specified in prefs', UserWarning)
                return default_val

            # if you still can't find a value, None is an unambiguous signal for pref not set
            # (no pref is ever None)
            except KeyError:
                return None

def set(key: str, val):
    """
    Set a pref!

    Note:
        Whenever a pref is set, the prefs file is automatically updated -- prefs are system-durable!!

        (specifically, whenever the module-level ``_INITIALIZED`` value is set to True, prefs are saved to file to
        avoid overwriting before loading)

    Args:
        key (str): Name of pref to set
        val: Value of pref to set (prefs are not type validated against default types)
    """
    globals()['_PREFS'][key] = val
    if globals()['_INITIALIZED'].value and 'pytest' not in sys.modules:
        save_prefs()


def save_prefs(prefs_fn: str = None):
    """
    Dump prefs into the ``prefs_fn`` .json file

    Args:
        prefs_fn (str, None): if provided, pathname to ``prefs.json`` otherwise resolve ``prefs.json`` according the
        to the normal methods....
    """
    if prefs_fn is None:
        try:
            prefs_fn = str(Path(get('BASEDIR')) / 'prefs.json')
        except KeyError:
            raise RuntimeError('Asked to save prefs without BASEDIR being set -- indicative of prefs being saved '
                               'before initialized')

    # take lock for access to prefs file
    with globals()['_LOCK']:
        with open(prefs_fn, 'w') as prefs_f:
            json.dump(globals()['_PREFS']._getvalue(), prefs_f,
                      indent=4, separators=(',', ': '))



def init(fn=None):
    """
    Initialize prefs on autopilot start.

    If passed dict of prefs or location of prefs.json, load and use that

    Otherwise

    - Look for the autopilot wayfinder ``~/.autopilot`` file that tells us where the user directory is
    - look in default location ``~/autopilot/prefs.json``

    Todo:

        This function may be deprecated in the future -- in its current form it serves to allow the sorta janky launch
        methods in the headers/footers of autopilot/core/pilot.py and autopilot/core/terminal.py that will eventually
        be transformed into a unified agent framework to make launching easier. Ideally one would be able to just
        import prefs without having to explicitly initialize it, but we need to formalize the full launch process
        before we make the full lurch to that model.

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

    # Get the current git hash
    if prefs.get('REPODIR', False):
        try:
            prefs['HASH'] = git_version(prefs.get('REPODIR'))
        except Exception as e:
            prefs['HASH'] = ''
            warnings.warn(f'git hash for repo could not be found! will not be able to keep good provenance! got exception: \n{e}')
    else:
        warnings.warn('REPODIR is not set in prefs.json, cant get git hash!!!')

    # FIXME: This 100% should not happen here and should happen in the relevant hardware classes.
    # Load any calibration data
    if prefs.get('BASEDIR', False):
        cal_path = os.path.join(prefs['BASEDIR'], 'port_calibration_fit.json')
        cal_raw = os.path.join(prefs['BASEDIR'], 'port_calibration.json')

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

    for k, v in prefs.items():
        # globals()[k] = v
        _PREFS[k] = v

    # also store as a dictionary so other modules can have one if they want it
    # globals()['__dict__'] = prefs

    globals()['_INITIALIZED'].value = True

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

    out = _minimal_ext_cmd(['git','-C',repo_dir, 'rev-parse', 'HEAD'])
    GIT_REVISION = out.strip().decode('ascii')

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

def clear():
    """
    Mostly for use in testing, clear loaded prefs (without deleting prefs.json)

    (though you will probably overwrite prefs.json if you clear and then set another pref so don't use this except in testing probably)
    """
    global _PREFS
    global _PREF_MANAGER
    _PREFS = _PREF_MANAGER.dict()

#
# class _Prefs(types.ModuleType):
#     """
#     Hidden class that replaces the module so that prefs can be subscripted
#
#     with respect to: https://sohliloquies.blogspot.com/2017/07/how-to-make-subscriptable-module-in.html
#     """
#
#     def __init__(self, *args, **kwargs):
#         super(_Prefs, self).__init__(*args, **kwargs)
#
#         # assign globals as attributes
#         for key, val in globals().items():
#             if key == "get":
#                 continue
#             self.__setattr__(key, val)
#
#     def __getitem__(self, item):
#         return self.get(item)
#
#     def __setitem__(self, key, value):
#         set(key, value)
#
#     def __getattr__(self, key):
#         """
#         get global (module) values first, then prefs
#         """
#
#         # if key in globals().keys():
#         #     return globals()[key]
#         try:
#             return object.__getattribute__(self, key)
#         except AttributeError:
#             return self.get(key)
#
#     def get(self, key: typing.Union[str, None] = None):
#         """
#         Get a pref!
#
#         If a value for the given ``key`` can't be found, prefs will attempt to
#
#         Args:
#             key (str, None): get pref of specific ``key``, if ``None``, return all prefs
#
#         Returns:
#             value of pref (type variable!), or ``None`` if no pref of passed ``key``
#         """
#
#         # if nothing is requested of us, return everything
#         if key is None:
#             return self._PREFS._getvalue()
#
#         else:
#             # try to get the value from the prefs manager
#             try:
#                 return self._PREFS[key]
#
#             # if none exists...
#             except KeyError:
#                 # try to get a default value
#                 try:
#                     default_val = globals()['_DEFAULTS'][key]['default']
#                     warnings.warn(f'Returning default prefs value {key} : {default_val} (ideally this shouldnt '
#                                   f'happen and everything should be specified in prefs')
#                     return default_val
#
#                 # if you still can't find a value, None is an unambiguous signal for pref not set
#                 # (no pref is ever None)
#                 except KeyError:
#                     return None
#
#     # def __setattr__(self, key, val):
#     #     object.__setattr__(self, key, val)
#     #     set(key, val)
#
#


#######################3

if not _INITIALIZED.value:
    init()

    # replace module
    # sys.modules[__name__] = _Prefs(__name__)


