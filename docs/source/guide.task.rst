.. _guide_task:

Writing a Task
**************

Some concepts of task design are also discussed in section 3.1 of the `whitepaper <auto-pi-lot.com/autopilot_whitepaper.pdf>`_.



The Nafc Task
=============

The :class:`~autopilot.tasks.Nafc` class serves as an example for new task designs.

To demonstrate the general structure of Autopilot tasks, let's build it from scratch.

The :class:`~autopilot.tasks.Task` class
----------------------------------------

We start by subclassing the :class:`autopilot.tasks.task.Task` class and initializing it.

.. code-block:: python

    from autopilot.tasks import Task

    class Nafc(Task):

        def __init__(self):
            super(Nafc, self).__init__()

This gives our new task some basic attributes and methods,
including the :meth:`~autopilot.tasks.task.Task.init_hardware` method for initializing the ``HARDWARE`` dictionary
and the :meth:`~autopilot.tasks.task.Task.handle_trigger` method for handling GPIO triggers.

Four Task Attributes
--------------------

We then add the four elements of a task description:

1. A **``PARAMS``** dictionary defines what parameters are needed to define the task
2. A **``Data``** (:class:`tables.IsDescription`) descriptor describes what data will be returned from the task
3. A **``PLOT``** dictionary that maps the data output to graphical elements in the GUI.
4. A **``HARDWARE``** dictionary that describes what hardware will be needed to run the task.

PARAMS
~~~~~~~~~~

Each parameter needs a human readable ``tag`` that will be used for GUI elements,
and a ``type``, currently one of:

* ``int``: integers
* ``bool``: boolean (checkboxes in GUI)
* ``list``: list of possible values in {'Name':int} pairs
* ``sounds``: a :class:`autopilot.core.gui.Sound_Widget` to define sounds.

To maintain order when opened by the GUI we use a :class:`~collections.odict` rather than a normal dictionary.

.. code-block:: python
    from collections import odict

    PARAMS = odict()
    PARAMS['reward']         = {'tag':'Reward Duration (ms)',
                                'type':'int'}
    PARAMS['req_reward']     = {'tag':'Request Rewards',
                                'type':'bool'}
    PARAMS['punish_stim']    = {'tag':'White Noise Punishment',
                                'type':'bool'}
    PARAMS['punish_dur']     = {'tag':'Punishment Duration (ms)',
                                'type':'int'}
    PARAMS['correction']     = {'tag':'Correction Trials',
                                'type':'bool'}
    PARAMS['correction_pct'] = {'tag':'% Correction Trials',
                                'type':'int',
                                'depends':{'correction':True}}
    PARAMS['bias_mode']      = {'tag':'Bias Correction Mode',
                                'type':'list',
                                'values':{'None':0,
                                          'Proportional':1,
                                          'Thresholded Proportional':2}}
    PARAMS['bias_threshold'] = {'tag': 'Bias Correction Threshold (%)',
                                'type':'int',
                                'depends':{'bias_mode':2}}
    PARAMS['stim']           = {'tag':'Sounds',
                                'type':'sounds'}


.. note::

    See the :class:`~autopilot.tasks.nafc.Nafc` class for descriptions of the task parameters.

These will be taken as key-value pairs when the task is initialized. ie.::

        PARAMS['correction']     = {'tag':  'Correction Trials',
                                    'type': 'bool'}

will be used to initialize the task like::

        Nafc(correction=True)

Data
~~~~~~~~

There are two types of data,

* ``TrialData`` - where a single value for several variables is returned per 'trial', and
* ``ContinuousData`` - where values and timestamps are taken continuously, without

.. todo:

    Support for saving continuous data is in place, but undocumented. See :ref:`todo`_.
    Specifically, a system for implementing multiple types of continuous data -- one where a single stream of data is collected without fixed interval between observations,
    and another where multiple values are aligned and collected at a fixed or at least synchronized interval.

Both are defined by `pytables <https://www.pytables.org/index.html>`_ :class:`tables.IsDescription` objects.
Specify each variable that will be returned and its type using a :class:`tables.Col` object:

.. note::

    See `the pytables documentation <https://www.pytables.org/usersguide/libref/declarative_classes.html#col-sub-classes>`_ for a list of ``Col`` types

.. code-block:: python

    import tables

    class TrialData(tables.IsDescription):
        trial_num    = tables.Int32Col()
        target       = tables.StringCol(1)
        response     = tables.StringCol(1)
        correct      = tables.Int32Col()
        correction   = tables.Int32Col()
        RQ_timestamp = tables.StringCol(26)
        DC_timestamp = tables.StringCol(26)
        bailed       = tables.Int32Col()

The column types are names with their type and their bit depth except for the :class:`~tables.StringCol`
which takes a string length in characters.

The ``TrialData`` object is used by the :class:`~autopilot.core.subject.Subject` class when a task is assigned to create the data storage table.

PLOT
~~~~
The ``PLOT`` dictionary maps the data returned from the task to graphical elements in the :class:`~autopilot.core.terminal.Terminal`'s :class:`~autopilot.core.plots.Plot`.
Specifically, when the task is started, the :class:`~autopilot.core.plots.Plot` object creates the graphical element (eg. a :class:`~autopilot.core.plots.Point`)
and then calls its ``update`` method with any data that is received through its :class:`~autopilot.core.networking.Node`.

Data is plotted either by trial (default) or by timestamp (if ``PLOT['continuous'] != True``). Numerical data is plotted as-expected, but
further mappings can be defined by extending the graphical element's ``update`` method -- eg. 'L'(eft) maps to 0 and 'R'(ight) maps to 1 by default.


.. code-block:: python

    PLOT = {
        'data': {
            'target'   : 'point',
            'response' : 'segment',
            'correct'  : 'rollmean'
        },
        'chance_bar'  : True, # Draw a red bar at 50%
        'roll_window' : 50 # number of trials to roll window over
    }


.. todo::

    Non-numeric mappings will be supported in the ``PLOT`` specification after parameters are unified into a single structure.




HARDWARE
~~~~~~~~

.. code-block:: python

    from autopilot.core import hardware

    HARDWARE = {
        'POKES':{
            'L': hardware.Beambreak,
            'C': hardware.Beambreak,
            'R': hardware.Beambreak
        },
        'LEDS':{
            'L': hardware.LED_RGB,
            'C': hardware.LED_RGB,
            'R': hardware.LED_RGB
        },
        'PORTS':{
            'L': hardware.Solenoid,
            'C': hardware.Solenoid,
            'R': hardware.Solenoid
        }
    }

Initialization
--------------

Stage Functions
---------------

Request
~~~~~~~

Discrim
~~~~~~~

Reinforcement
~~~~~~~~~~~~~

Additional Methods
------------------



Nafc Wheel - Child Agents
================================

Task Running Styles
-------------------

- pilot calls stages, blocked with event
- task manages advancement, returns data with node








