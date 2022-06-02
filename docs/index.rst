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

For a detailed overview of Autopilot's motivation, design, and structure, see our `whitepaper <https://www.biorxiv.org/content/10.1101/807693v2>`_.

.. admonition:: What's New :ref:`v0.5.0a0 - The Data Modeling Edition (2022-06-01) <changelog_v050a>`

    A prerelease as Jonny is finishing their dissertation and doesn't want to break anyone's experiments!

    * Adding the whole :mod:`autopilot.data` module, which starts the process of making everything work with formal data models.
    * Rewriting the :class:`~autopilot.data.subject.Subject` class!
    * A :class:`.ModelWidget` to fill and edit data models that will eventually replace much of the aging GUI
    * Less jitter in :class:`JackClient` by removing calls to ``queue.get``
    * Repackaging autopilot with poetry!
    * :mod:`.log_parsers` and programmatic reading of logs
    * See the :ref:`changelog <changelog_v050a>` for more!


This documentation is very young and is very much a work in progress! Please `submit an issue <https://github.com/auto-pi-lot/autopilot/issues/new>`_ with any incompletenesses, confusion, or errors!


.. toctree::
   :maxdepth: 1
   :caption: User Guide:

   Overview <guide/overview>
   Quickstart <guide/quickstart>
   Installation <guide/installation>
   Configuration <guide/configuration>
   Training a Subject <guide/training>
   Writing a Task <guide/task>
   Using Plugins <guide/plugins>
   Examples <examples/index>
   FAQ <guide/faq>

.. toctree::
   :maxdepth: 1
   :caption: API Documentation:
   :titlesonly:

   Agents <agents/index>
   Data <data/index>
   GUI <gui/index>
   Hardware <hardware/index>
   Networking <networking/index>
   Stimuli <stim/index>
   Tasks <tasks/index>
   Transformations <transform/index>
   Utilities <utils/index>
   Setup <setup/index>
   Prefs <prefs>
   Root <root/index>
   External <external>


.. toctree::
    :maxdepth: 1
    :caption: Meta:

    Wiki <https://wiki.auto-pi-lot.com/>
    Discussion <https://github.com/auto-pi-lot/autopilot/discussions>
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
