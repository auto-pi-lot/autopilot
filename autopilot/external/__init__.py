import subprocess
import os
import sys
from autopilot import prefs
import atexit
from time import sleep
import threading
import shutil
import signal
import re
import warnings

PIGPIO = False
PIGPIO_DAEMON = None
PIGPIO_LOCK = threading.Lock()
try:
    if shutil.which('pigpiod') is not None:
        PIGPIO = True

except ImportError:
    pass

JACKD = False
# JACKD_MODULE = None # Whether jackd is a module in autopilot.external (True) or use system jackd (False)
JACKD_PROCESS = None
try:
    import jack
    JACKD = True

except (ImportError, OSError):
    pass

def check_open(procname:str) -> bool:
    """
    Check if a process with a given procname is currently running

    Args:
        procname (str): short name of process like 'jack' or 'pigpio'

    Returns:
        bool: ``True`` if process found
    """
    ps = subprocess.run([shutil.which('ps'), '-e'], capture_output=True)
    # do a simple 'in' search for now. if this ends up being unreliable we'll need to parse the output more carefully
    matches = re.findall(procname, ps.stdout.decode('utf-8'))
    if matches:
        return True
    else:
        return False


def start_pigpiod():
    if not PIGPIO:
        raise ImportError('the pigpiod daemon was not found! use autopilot.setup.')

    if check_open('pigpiod'):
        warnings.warn('pigpiod is already running')
        return

    with globals()['PIGPIO_LOCK']:
        if globals()['PIGPIO_DAEMON'] is not None:
            return globals()['PIGPIO_DAEMON']

        launch_pigpiod = shutil.which('pigpiod')
        if launch_pigpiod is None:
            raise RuntimeError('the pigpiod binary was not found!')

        if prefs.get( 'PIGPIOARGS'):
            launch_pigpiod += ' ' + prefs.get('PIGPIOARGS')

        if prefs.get( 'PIGPIOMASK'):
            # if it's been converted to an integer, convert back to a string and zfill any leading zeros that were lost
            if isinstance(prefs.get('PIGPIOMASK'), int):
                prefs.set('PIGPIOMASK', str(prefs.get('PIGPIOMASK')).zfill(28))
            launch_pigpiod += ' -x ' + prefs.get('PIGPIOMASK')

        proc = subprocess.Popen('sudo ' + launch_pigpiod, shell=True)
        globals()['PIGPIO_DAEMON'] = proc

        # kill process when session ends
        def kill_proc(*args):
            proc.kill()
            sys.exit(1)
        atexit.register(kill_proc)
        signal.signal(signal.SIGTERM, kill_proc)

        # sleep to let it boot up
        sleep(1)

        return proc

def start_jackd():
    if not JACKD:
        raise ImportError('jackd was not found in autopilot.external or as a system install')

    if check_open('jackd'):
        warnings.warn('jackd already running')
        return

    # get specific launch string from prefs
    if prefs.get("JACKDSTRING"):
        jackd_string = prefs.get('JACKDSTRING').lstrip('jackd')

    else:
        jackd_string = ""

    # replace string fs with number
    if prefs.get('FS'):
        jackd_string = jackd_string.replace('-rfs', f"-r{prefs.get('FS')}")

    # replace string nperiods with number
    if prefs.get('ALSA_NPERIODS'):
        jackd_string = jackd_string.replace('-nper', f"-n{prefs.get('ALSA_NPERIODS')}")

    jackd_bin = shutil.which('jackd')

    launch_jackd = " ".join([jackd_bin, jackd_string])

    proc = subprocess.Popen(launch_jackd, shell=True)
    globals()['JACKD_PROCESS'] = proc

    # kill process when session ends
    def kill_proc(*args):
        proc.kill()
        sys.exit(1)
    atexit.register(kill_proc)
    signal.signal(signal.SIGTERM, kill_proc)

    # sleep to let it boot
    sleep(2)

    return proc

