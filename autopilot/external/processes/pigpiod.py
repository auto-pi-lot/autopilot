import atexit
import shutil
import signal
import subprocess
import sys
import threading
from time import sleep

from autopilot import prefs

PIGPIO = False
try:
    if shutil.which('pigpiod') is not None:
        PIGPIO = True
except ImportError:
    pass

PIGPIO_DAEMON = None
PIGPIO_LOCK = threading.Lock()


def start_pigpiod():
    if not PIGPIO:
        raise ImportError('the pigpiod daemon was not found! use autopilot.setup.')

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