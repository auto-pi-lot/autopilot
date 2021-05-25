.. _overview:


.. todo::
   This page is still under construction! For a more detailed description, see the whitepaper, particularly "Program Structure"

   https://www.biorxiv.org/content/10.1101/807693v1


Overview
********

Program Structure
=================

.. image:: ../_images/whole_system_black.svg
    :alt: Graphical Overview of Autopilot Modules
    :width: 100%

Autopilot performs experiments by distributing them over a network of desktop computers and Raspberry Pis.
Each Computer or Pi runs an Autopilot **agent**, like the user-facing :class:`~.Terminal` or a Raspberry Pi
:class:`~.Pilot` .

The :class:`.Terminal` agent provides a :mod:`~.core.gui` to operate the system, manage :class:`~.subject.Subject` s and
experimental protocols, and :mod:`~.core.plots` for visualizing data from ongoing experiments.

Each :class:`.Terminal` manages a swarm of :class:`.Pilot` s that actually perform the experiments. Each :class:`.Pilot`
coordinates :mod:`.hardware` and :mod:`.stim` uli in a :class:`.Task`. :class:`.Pilot` s can, in turn, coordinate their
own swarm of networked ``Children`` that can manage additional hardware components -- allowing :class:`.Task` s to
use effectively arbitrary numbers and combinations of hardware.

Tasks
=====

.. image:: ../_images/figure_protocol.png
    :width: 50%
    :align: center
    :alt: Protocol Structure

Behavioral experiments in Autopilot consist of :class:`.Task` s. Tasks define the parameters, coordinate the hardware,
and perform the logic of an experiment.

Tasks may consist of one or multiple **stages**, completion of which
constitutes a **trial**. Stages are analogous to states in a finite-state machine, but don't share their limitations:
Tasks can use arbitrary transitions between stages and have computation or hardware operation persist between stages.

Multiple Tasks can be combined to make **protocols**, in which subjects move between different tasks according to
:mod:`.graduation` criteria like accuracy or number of trials. Protocols can thus be used to automate shaping routines
that introduce a subject to the experimental apparatus and task structure.

For more details on tasks, see :ref:`guide_task`



Module Tour
===============================

.. todo::

    A more comprehensive overview is forthcoming, but the documentation for the most important modules can be found in the
    API documentation. A short tour for now...

* :class:`.Terminal` - user facing agent class used to control and configure program operation. See
  :ref:`setup_terminal` and :mod:`.setup.setup_terminal`
* :mod:`.gui` - GUI classes built with PySide2/Qt5 used by the terminal
* :mod:`.plots` - Classes to plot data from ongoing tasks
* :mod:`.pilot` - Experimental agent that runs tasks on Raspberry Pis
* :mod:`.networking` - Networking modules used for communication between agents, tasks, and hardware objects
* :mod:`.subject` - Data and metadata storage
* :mod:`.hardware` - Hardware objects that can be used in tasks
* :mod:`.tasks` - Customizable and extendable Task templates
* :mod:`.stim` - Stimulus generation & presentation, of which sound is currently the most heavily developed

.. raw:: html
   :file: ../includes/module_map.html
