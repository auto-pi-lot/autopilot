__author__  = 'Jonny Saunders <j@nny.fyi>'

import sys
from importlib.metadata import version
import multiprocessing
multiprocessing.set_start_method('fork')

__version__ = version("auto-pi-lot")

from autopilot.root import Autopilot_Type, Autopilot_Pref

from autopilot.utils.registry import get, get_task, get_hardware, get_names
from autopilot.utils.hydration import dehydrate, hydrate