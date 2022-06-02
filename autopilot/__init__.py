__author__  = 'Jonny Saunders <j@nny.fyi>'

import sys
if sys.version_info < (3,8):
    from importlib_metadata import version
    # monkeypatch typing
    import typing
    from typing_extensions import Literal
    typing.Literal = Literal
else:
    from importlib.metadata import version


__version__ = version("auto-pi-lot")

from autopilot.root import Autopilot_Type, Autopilot_Pref


from autopilot.setup import setup_autopilot
from autopilot.utils.registry import get, get_task, get_hardware, get_names
from autopilot.utils.hydration import dehydrate, hydrate