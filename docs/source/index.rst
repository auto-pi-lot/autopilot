.. autopilot documentation master file, created by
   sphinx-quickstart on Mon Jan 21 15:35:11 2019.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

Autopilot - Distributed Behavior
*********************************

Autopilot is a Python framework to perform behavioral experiments with one or many `Raspberry Pis <https://www.raspberrypi.org/>`_.

For an overview of Autopilot's motivation, design, and structure, see our `whitepaper <https://www.biorxiv.org/content/10.1101/807693v1>`_.

This documentation is very young and is very much a work in progress! Please `submit an issue <https://github.com/wehr-lab/autopilot/issues/new>`_ with any incompletenesses, confusion, or errors!


.. toctree::
   :maxdepth: 1
   :caption: User Guide:

   Overview <guide.overview>
   Installation <guide.installation>
   Training a Subject <guide.training>
   Writing a Task <guide.task>
   Writing a Hardware Class <guide.hardware>


.. toctree::
   :maxdepth: 1
   :caption: API Documentation:

   Core Modules <autopilot.core>
   Hardware <autopilot.hardware>
   Tasks <autopilot.tasks>
   Stimuli <autopilot.stim>
   Visualization Tools <autopilot.viz>
   Setup <autopilot.setup>
   Prefs <autopilot.prefs>
   External <autopilot.external>


.. toctree::
    :maxdepth: 1
    :caption: Meta:

    To-Do <todo>
    Changelog <changelog/index>



Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
