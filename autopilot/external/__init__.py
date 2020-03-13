import subprocess
import os

from autopilot.external import pigpio


def start_pigpiod():
    pigpiod_path = os.path.join(pigpio.__path__._path[0], 'pigpiod')
    proc = subprocess.Popen('sudo ' + pigpiod_path, shell=True)
    return proc
