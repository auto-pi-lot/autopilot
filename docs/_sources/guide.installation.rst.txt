.. _installation:

.. todo::

    The formalization of Agent classes and smoothing the install process is a major development goal
    for Autopilot! See :ref:`todo` !

Installation
************

Each runtime of Autopilot is called an "Agent,"
each of which performs different roles within a system,
and thus have different requirements.

Each Agent should have its own setup routine, currently in two parts:

- A **presetup** script that prepares the environment, and installs prerequisites -- essentially does all the things to prepare us to invoke Autopilot
- A **setup** routine that creates the prefs.json file that governs Agent operation, creates any launch scripts and system services as needed.

We will be incorporating these into a unified agent system that makes setting up and switching between agents easier in future version (See :ref:`todo`).

Note:
    These instructions, like everything in Autopilot, is Linux and unix only. They have only been tested on macOS and Ubuntu Linux.


.. toctree::

   Pilot Setup <guide.installation.pilot>
   Terminal Setup <guide.installation.terminal>
