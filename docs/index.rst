.. title::
   Autopilot - Distributed Behavior


.. raw:: html
   :file: includes/autopilot_logo_banner.html

Autopilot is a Python framework to perform behavioral experiments with one or many `Raspberry Pis <https://www.raspberrypi.org/>`_.

Its distributed structure allows arbitrary numbers and combinations of hardware components to be used in an experiment,
allowing users to perform complex, hardware-intensive experiments at scale.

Autopilot integrates every part of your experiment,
including hardware operation, task logic, stimulus delivery, data management, and visualization of task progress --
making experiments in behavioral neuroscience replicable from a single file.

Instead of rigid programming requirements, Autopilot attempts to be a flexible framework with many different modalities of use
in order to adapt to the way you do and think about your science rather than the other way around. Use only the parts of the
framework that are useful to you, build on top of it with its plugin system as you would normally, while also maintaining
the provenance and system integration that more rigid systems offer.

For developers of other tools, Autopilot provides a skeleton with minimal assumptions to integrate their work with its
broader collection of tools, for example our integration of `DeepLabCut-live <https://github.com/DeepLabCut/DeepLabCut-live>`_
as the :class:`~.transform.image.DLC` transform (:cite:`kaneRealtimeLowlatencyClosedloop2020`).

Our long-range vision is to build a tool that lowers barriers to tool use and contribution, from code to contextual technical
knowledge, so our broad and scattered work can be cumulatively combined without needing a centralized consortium or
adoption of a singular standard.

For a detailed overview of Autopilot's motivation, design, and structure, see our `whitepaper <https://www.biorxiv.org/content/10.1101/807693v1>`_.

.. admonition:: What's New :ref:`v0.4.0 - Become Multifarious (21-08-03) <changelog_v040>`

    * The `Autopilot Wiki <https://wiki.auto-pi-lot.com>`_ is live!!!! The wiki will be the means of gathering and sharing knowledge about using Autopilot, but
      it will also serve as an additional tool for building interfaces and decentralizing control over its development. Head to the :ref:`changelog <changelog_v040>`
      or the :ref:`guide_plugins` page to learn more
    * Autopilot :mod:`~.utils.plugins` are now live!!! Anything in your plugin directory is a plugin, extend most types of autopilot classes to implement
      your own custom hardware and tasks and anything else without modifying autopilot itself, then `submit it to the wiki <https://wiki.auto-pi-lot.com/index.php/Autopilot_Plugins>`_
      to make it immediately available to everyone who uses the system! Link it to all the rest of your work, the parts it uses, let's make a knowledge graph!!!
    * Tests and Continuous Integration are finally here!!! if there has been anything I have learned over the past few projects is that tests are god.
      Ours are hosted on `travis <https://app.travis-ci.com/github/wehr-lab/autopilot>`_ and we are currently on the board with a stunning `27% coverage <https://coveralls.io/github/wehr-lab/autopilot>`_
      at coveralls.io
    * Lots of new hardware and transform classes! Take a look! :class:`.cameras.PiCamera`, :class:`.timeseries.Kalman`, :class:`.geometry.IMU_Orientation`,
      :class:`.timeseries.Filter_IIR`, :class:`.timeseries.Integrate`, :class:`.geometry.Rotate`, :class:`.geometry.Spheroid`
    * Major improvements like stereo sound (Thanks `Chris Rodgers <https://github.com/cxrodgers/>`_ !), multihop messages, direct messaging, programmatic setup... see more in the :ref:`changelog <changelog_v040`
    * Continued work on deconvoluting and remodularating all the code structure!
    * Removed limits on python version, now testing on 3.7, 3.8, and 3.9


This documentation is very young and is very much a work in progress! Please `submit an issue <https://github.com/wehr-lab/autopilot/issues/new>`_ with any incompletenesses, confusion, or errors!


.. toctree::
   :maxdepth: 1
   :caption: User Guide:

   Overview <guide/overview>
   Quickstart <guide/quickstart>
   Installation <guide/installation>
   Training a Subject <guide/training>
   Writing a Task <guide/task>
   Writing a Hardware Class <guide/hardware>
   Using Plugins <guide/plugins>
   Examples <examples>

.. toctree::
   :maxdepth: 1
   :caption: API Documentation:

   Core Modules <core/index>
   Hardware <hardware/index>
   Networking <networking/index>
   Stimuli <stim/index>
   Tasks <tasks/index>
   Transformations <transform/index>
   Visualization Tools <viz/index>
   Utilities <utils/index>
   Setup <setup/index>
   Prefs <prefs>
   External <external>


.. toctree::
    :maxdepth: 1
    :caption: Meta:

    Wiki <https://wiki.auto-pi-lot.com/>
    Discussion <https://github.com/wehr-lab/autopilot/discussions>
    Changelog <changelog/index>
    To-Do <todo>
    References <references>

.. toctree::
    :caption: Tests:

    tests/index



Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
