import platform
import os
import codecs

#from skbuild import setup, constants
from setuptools import find_packages, setup
import subprocess
import sys

# fix user install issue
import site
site.ENABLE_USER_SITE = "--user" in sys.argv[1:]

# declare defaults
IS_RASPI = False
SCRIPTS = []
PACKAGES = []
# CMAKE_ARGS = ['-DCMAKE_BUILD_DIR={}'.format(constants.CMAKE_BUILD_DIR()),
#               '-DCMAKE_INSTALL_DIR={}'.format(constants.CMAKE_INSTALL_DIR()),
#               '-DSETUPTOOLS_INSTALL_DIR={}'.format(constants.SETUPTOOLS_INSTALL_DIR()),
#               '-DSKBUILD_DIR={}'.format(constants.SKBUILD_DIR()),
#               '-DCMAKE_BUILD_RPATH_USE_ORIGIN=1', # use relative paths in Rpaths
#               '-DCMAKE_INSTALL_RPATH=$ORIGIN/lib;$ORIGIN/../lib'
#               ]

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
    REQUIREMENTS = load_requirements('requirements/requirements_pilot.txt')

elif ARCH == 'x86':
    # is a terminal,
    REQUIREMENTS = load_requirements('requirements/requirements_terminal.txt')

elif os.environ.get('TRAVIS', False):
    REQUIREMENTS = load_requirements('requirements/requirements_tests.txt')

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


# get package version
def read(rel_path):
    """
    https://packaging.python.org/guides/single-sourcing-package-version/
    """
    here = os.path.abspath(os.path.dirname(__file__))
    with codecs.open(os.path.join(here, rel_path), 'r') as fp:
        return fp.read()


def get_version(rel_path):
    """
    https://packaging.python.org/guides/single-sourcing-package-version/
    """
    for line in read(rel_path).splitlines():
        if line.startswith('__version__'):
            delim = '"' if '"' in line else "'"
            return line.split(delim)[1]
    else:
        raise RuntimeError("Unable to find version string.")

setup(
    name="auto-pi-lot",
    version=get_version('autopilot/__init__.py'),
    description="Distributed behavioral experiments",
    long_description = readme,
    long_description_content_type='text/markdown',
    author="Jonny Saunders",
    author_email="j@nny.fyi",
    url="https://auto-pi-lot.com",
    license="MPL-2.0",
    scripts = SCRIPTS,
    packages=packs,
    #cmake_args=CMAKE_ARGS,
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
    python_requires=">=3.7.*"
)
