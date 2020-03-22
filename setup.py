# preinstall, check system dependencies
import subprocess
subprocess.call('autopilot/setup/setup_environment.sh')

from skbuild import setup
from setuptools import find_packages
import subprocess

# declare defaults
IS_RASPI = False
SCRIPTS = []
PACKAGES = []
CMAKE_ARGS = []
REQUIREMENTS = []


# detect if on raspberry pi
ret = subprocess.call(['grep', '-q', 'BCM', '/proc/cpuinfo'])
if ret == 0:
    IS_RASPI = True


def load_requirements(req_file):
    with open(req_file, 'r') as f:
        requirements = f.read().splitlines()

    # filter commented reqs
    requirements = [r for r in requirements if not r.startswith('#')]

    # filter empty reqs
    requirements = [r for r in requirements if r]

    return requirements

# configure for raspberry pi
if IS_RASPI:
    CMAKE_ARGS = ['-DPIGPIO=ON']
    #SCRIPTS.append('autopilot/external/pigpio/pigpiod')
    PACKAGES.append('autopilot.external.pigpio')
    REQUIREMENTS = load_requirements('requirements_pilot.txt')

else:
    # is a terminal, should have minimum dependencies installed
    # sys.argv.append('--skip-cmake')
    REQUIREMENTS = load_requirements('requirements_terminal.txt')


# add external packages that wouldn't get detected normally
packs = find_packages()
packs.extend(PACKAGES)

setup(
    name="autopilot",
    version="0.3.0",
    description="Distributed behavioral experiments",
    author="Jonny Saunders",
    author_email="JLSaunders987@gmail.com",
    url="https://auto-pi-lot.com",
    license="MPL-2.0",
    scripts = SCRIPTS,
    packages=packs,
    cmake_args=CMAKE_ARGS,
    install_requires = REQUIREMENTS
)