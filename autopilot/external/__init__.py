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

    jackd_string = "LD_LIBRARY_PATH={libpath} {jpath}".format(
        libpath=os.path.join(jackd_path,'lib'),
        jpath=jackd_path
    )

    if hasattr(prefs, 'JACKDSTRING'):
        jackd_string += prefs.JACKDSTRING.lstrip('jackd')

    proc = subprocess.Popen(jackd_string, shell=True)
    return proc

