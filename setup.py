# preinstall, check system dependencies
import subprocess
subprocess.call('autopilot/setup/setup_environment.sh')

import sys
from skbuild import setup
from setuptools import find_packages
import subprocess

# declare defaults
IS_RASPI = False
SCRIPTS = []
PACKAGES = []
CMAKE_ARGS = []
REQUIREMENTS = []
REQUIREMENTS_LINKS = []
CMAKE_INSTALL_DIR = ''


# detect if on raspberry pi
ret = subprocess.call(['grep', '-q', 'BCM', '/proc/cpuinfo'])
if ret == 0:
    IS_RASPI = True


# configure for raspberry pi
if IS_RASPI:
    CMAKE_ARGS = ['-DPIGPIO=ON']
    #CMAKE_INSTALL_DIR = '/usr/local'
    #SCRIPTS.append('autopilot/external/pigpio/pigpiod')
    PACKAGES.append('autopilot.external.pigpio')
    with open('requirements_pilot.txt', 'r') as f:
        REQUIREMENTS = f.read().splitlines()
else:
    # is a terminal, should have minimum dependencies installed
    # sys.argv.append('--skip-cmake')
    with open('requirements_terminal.txt', 'r') as f:
        REQUIREMENTS = f.read().splitlines()

for req in REQUIREMENTS:
    if req.startswith('git+'):
        REQUIREMENTS_LINKS.append(req)
        REQUIREMENTS.remove(req)
        # REQUIREMENTS.append(req.split('/')[-1].rstrip('.git'))


print(REQUIREMENTS)

packs = find_packages()
packs.extend(PACKAGES)

setup(
    name="autopilot",
    version="0.3.0",
    description="Distributed behavioral experiments",
    author="Jonny Saunders",
    author_email="JLSaunders987@gmail.com",
    url="https://auto-pi-lot.com",
    license="MPL2",
    scripts = SCRIPTS,
    # dependency_links=['src/pigpio/'],
    packages=packs,
    cmake_args=CMAKE_ARGS,
    cmake_install_dir = CMAKE_INSTALL_DIR,
    install_requires = REQUIREMENTS,
    dependency_links = REQUIREMENTS_LINKS
)