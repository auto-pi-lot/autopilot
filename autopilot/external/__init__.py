import subprocess
import os
from autopilot import prefs

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
    pigpiod_path = os.path.join(pigpio.__path__._path[0], 'pigpiod')
    proc = subprocess.Popen('sudo ' + pigpiod_path, shell=True)
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
    return proc

