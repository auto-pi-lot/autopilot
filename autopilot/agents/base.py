"""
Base Agent class.

Currently a stub just to get them in the object hierarchy
"""

from autopilot.root import Autopilot_Object


class Agent(Autopilot_Object):
    """
    Metaclass for agent types.

    Currently a stub, but will provide hooks for basic lifecycle methods of agents:

    * ``pre_init`` - to be run before any other standard initialization
    * ``init`` - main initialization hook
    * ``init_external`` - initialize external processes
    * ``post_init`` - to be run after other initialization
    * ... to be continued

    And core class and instance attributes:

    * ``prefs`` - prefs that are needed to configure this agent
    * ``processes`` - processes spawned by this agent
    * ``listens`` - methods to handle messages sent to this agent
    * ``dependencies`` - additional optional python packages or system configurations that this agent depends on.
    """