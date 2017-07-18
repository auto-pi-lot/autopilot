
TASKontrol
==========

TASKontrol is an open source framework for developing behavioral experiments.

It consists of modules written in `Python`_ and `PySide`_ (Qt for Python) for designing behavioral paradigms and providing a graphical user interface to control the experiments. It also includes software that runs in an `Arduino Due`_ to provide an interface for detecting external events and triggering stimuli.

TASKontrol was originally developed by Santiago Jaramillo and it is maintained by the `Jaramillo Lab`_ at the University of Oregon. The source code can be found in `GitHub`_.

.. _Python: https://www.python.org/
.. _PySide: http://www.pyside.org
.. _Arduino Due: https://www.arduino.cc/en/Main/ArduinoBoardDue
.. _Jaramillo Lab: http://jaralab.uoregon.edu/
.. _Github: https://github.com/sjara/taskontrol


Below is an example of a graphical user interface created with TASKontrol.

.. image:: images/taskontrol_screenshot_20160528.png
   :scale: 50 %
   :alt: Example of a graphical interface
   :align: center


**NOTE:** This documentation is a work in progress. Many modules are still missing.

Contents:
^^^^^^^^^
.. toctree::
   :maxdepth: 2

   getting_started
   state_transitions
   advanced_topics
     statematrix
     sound
   reference

..   settings
..   core
.. plugins


Indices and tables
------------------

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`

Help
----

* `reStructuredText Primer <http://www.sphinx-doc.org/en/stable/rest.html>`_. 


.. taskontrol documentation master file, created by
   sphinx-quickstart on Sun Sep  1 20:20:42 2013.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

.. this is a test comment.
