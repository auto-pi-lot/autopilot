import subprocess
import os
from autopilot import prefs
import atexit

PIGPIO = False
try:
    from autopilot.external import pigpio
    PIGPIO = True
except ImportError:
    pass

JACKD = False
try:
    from autopilot.external import jack
    JACKD = True
except ImportError:
    pass

def start_pigpiod():
    if not PIGPIO:
        raise ImportError('pigpio was not found in autopilot.external')
    launch_pigpiod = os.path.join(pigpio.__path__._path[0], 'pigpiod')
    if hasattr(prefs, 'PIGPIOARGS'):
        launch_pigpiod += ' ' + prefs.PIGPIOARGS

    if hasattr(prefs, 'PIGPIOMASK'):
        launch_pigpiod += ' -x ' + prefs.PIGPIOMASK

    proc = subprocess.Popen('sudo ' + launch_pigpiod, shell=True)

    # kill process when session ends
    atexit.register(lambda pigpio_proc=proc: pigpio_proc.kill())

    return proc

def start_jackd():
    if not JACKD:
        raise ImportError('jackd was not found in autopilot.external')
    jackd_path = os.path.join(jack.__path__._path[0])

    # specify location of libraries when starting jackd
    lib_string = "LD_LIBRARY_PATH=" + os.path.join(jackd_path, 'lib')

    # specify location of drivers when starting jackd
    driver_string = "JACK_DRIVER_DIR=" + os.path.join(jackd_path, 'lib', 'jack')

    jackd_bin = os.path.join(jackd_path, 'bin', 'jackd')

    if hasattr(prefs, "JACKDSTRING"):
        jackd_string = prefs.JACKDSTRING.lstrip('jackd')

    else:
        jackd_string = ""

    # combine all the pieces
    launch_jackd = " ".join([lib_string, driver_string, jackd_bin, jackd_string])


    proc = subprocess.Popen(launch_jackd, shell=True)

    # kill process when session ends
    atexit.register(lambda jackd_proc=proc: jackd_proc.kill())

    return proc

