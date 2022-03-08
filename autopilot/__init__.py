__author__  = 'Jonny Saunders <j@nny.fyi>'
__version__ = '0.4.4'

import sys
if sys.version_info < (3,8):
    from importlib_metadata import version
else:
    from importlib.metadata import version

__version__ = version("auto-pi-lot")


from autopilot.setup import setup_autopilot
from autopilot.utils.registry import get, get_task, get_hardware, get_names
from autopilot.utils.hydration import dehydrate, hydrate