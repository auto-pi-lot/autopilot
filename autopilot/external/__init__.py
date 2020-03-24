import subprocess
import os

PIGPIO = False
try:
    from autopilot.external import pigpio
    PIGPIO = True
except ImportError:
    pass

def start_pigpiod():
    if not PIGPIO:
        raise ImportError('pigpio was not found in autopilot.external')
    pigpiod_path = os.path.join(pigpio.__path__._path[0], 'pigpiod')
    proc = subprocess.Popen('sudo ' + pigpiod_path, shell=True)
    return proc
