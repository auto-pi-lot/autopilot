import platform
import os

from skbuild import setup, constants
from setuptools import find_packages
import subprocess
import sys


# declare defaults
IS_RASPI = False
SCRIPTS = []
PACKAGES = []
CMAKE_ARGS = ['-DCMAKE_BUILD_DIR={}'.format(constants.CMAKE_BUILD_DIR()),
              '-DCMAKE_INSTALL_DIR={}'.format(constants.CMAKE_INSTALL_DIR()),
              '-DSETUPTOOLS_INSTALL_DIR={}'.format(constants.SETUPTOOLS_INSTALL_DIR()),
              '-DSKBUILD_DIR={}'.format(constants.SKBUILD_DIR()),
              '-DCMAKE_BUILD_RPATH_USE_ORIGIN=1', # use relative paths in Rpaths
              '-DCMAKE_INSTALL_RPATH=$ORIGIN/lib;$ORIGIN/../lib'
              ]

REQUIREMENTS = []



# detect if on raspberry pi
try:
    ret = subprocess.call(['grep', '-q', 'BCM', '/proc/cpuinfo'])
    if ret == 0:
        IS_RASPI = True
except:
    pass


# detect architecture
_ARCH = platform.uname().machine
ARCH = None
if _ARCH in ('armv7l',):
    ARCH = "ARM32"
elif _ARCH in ('aarch64',):
    ARCH = 'ARM64'
elif _ARCH in ('x86_64',):
    ARCH = "x86"


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
    # install raspi dependencies
    # subprocess.call(['autopilot/setup/setup_environment_pi.sh'])


    CMAKE_ARGS.extend(['-DPIGPIO=ON', '-DJACK=ON'])
    # FIXME: Need to get jack build in egg working, continue the CMakelists work on integrating during build. for now just adding to env dependencies

    # CMAKE_ARGS = ['-DPIGPIO=ON']
    #SCRIPTS.append('autopilot/external/pigpio/pigpiod')
    PACKAGES.append('autopilot.external.pigpio')
    REQUIREMENTS = load_requirements('requirements/requirements_pilot.txt')

elif ARCH == 'x86':
    # is a terminal,
    # install dependencies
    # subprocess.call(['autopilot/setup/setup_environment_terminal.sh'])

    # sys.argv.append('--skip-cmake')
    REQUIREMENTS = load_requirements('requirements/requirements_terminal.txt')

else:
    REQUIREMENTS = load_requirements('requirements.txt')

# add external packages that wouldn't get detected normally
packs = find_packages()
packs.extend(PACKAGES)

# load readme
with open(os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        'README.md'), 'r') as readme_f:
    readme = readme_f.read()

setup(
    name="auto-pi-lot",
    version="0.3.1",
    description="Distributed behavioral experiments",
    long_description = readme,
    long_description_content_type='text/markdown',
    author="Jonny Saunders",
    author_email="sneakers-the-rat@protonmail.com",
    url="https://auto-pi-lot.com",
    license="MPL-2.0",
    scripts = SCRIPTS,
    packages=packs,
    cmake_args=CMAKE_ARGS,
    install_requires = REQUIREMENTS,
    classifiers=[
        "Programming Language :: Python :: 3.7",
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Intended Audience :: Education",
        "Intended Audience :: End Users/Desktop",
        "Intended Audience :: Science/Research",
        "License :: OSI Approved :: Mozilla Public License 2.0 (MPL 2.0)",
        "Natural Language :: English",
        "Operating System :: POSIX :: Linux",
        "Operating System :: MacOS",
        "Topic :: Scientific/Engineering"
    ],
)