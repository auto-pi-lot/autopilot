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

For a detailed overview of Autopilot's motivation, design, and structure, see our `whitepaper <https://www.biorxiv.org/content/10.1101/807693v1>`_.

.. admonition:: What's New :ref:`(v0.3.0) <changelog_v030>`

    * Autopilot has moved to Python 3.8!!
    * Capturing video with OpenCV and the Spinnaker SDK is now supported (See :mod:`autopilot.hardware.cameras`)
    * An :class:`~hardware.i2c.I2C_9DOF` motion sensor and the :class:`~hardware.i2c.MLX90640` temperature sensor
      are now supported.
    * Timestamps from GPIO events are now microsecond-precise thanks to some modifications to the ``pigpio`` library
    * GPIO output timing is also microsecond-precise thanks to the use of ``pigpio`` scripts, so you can deliver
      exactly the reward volumes you intend <3
    * Hardware modules have been refactored into their own module, and have been almost wholly rebuilt to have sensible
      inheritance structure.
    * Networking modules are more efficient and automatically compress arrays (like video frames!) on transmission.
      Streaming is also easier now, check out :meth:`.Net_Node.get_stream` !
    * We now have a detailed :ref:`development roadmap <todo>` , so you can see the magnificent future we have planned.
    * We have created the `autopilot-users <https://groups.google.com/forum/#!forum/autopilot-users>`_ discussion board
      for troubleshooting & coordinating community development :)

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

    Discussion <https://groups.google.com/forum/#!forum/autopilot-users>
    To-Do <todo>
    Changelog <changelog/index>



Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
