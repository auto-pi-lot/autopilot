Agents
===================

Agents are the basic runtime elements of Autopilot. At the moment we only have two built into base autopilot,
:class:`.Terminal` - which hosts the GUI and user-facing parts of Autopilot, and :class:`.Pilot` that runs experiments
from a Raspberry Pi!

The Agent structure is, at the moment, a draft, but see the :class:`.Agent` class for more information about
its future development.

.. automodule:: autopilot.agents
    :members:
    :undoc-members:
    :show-inheritance:


.. toctree::
   :maxdepth: 10

   base
   pilot
   terminal

