.. _guide_task:

.. important::

    This guide and :ref:`guide_hardware` are lightly out of date with v0.4.0 of autopilot, but still largely reflect the
    program design and its operation. For a simpler task, see :ref:`example_blink` .

    Many of these things can be done more elegantly, more simply, etc. now but we
    are a very small team and can only do so much work between releases! We'd be happy to get
    `documentation requests <https://github.com/wehr-lab/autopilot/issues/32>`_ or even a pull request or two to help
    us out until we can get to it :)

Writing a Task
**************

Some concepts of task design are also discussed in section 3.1 of the `whitepaper <https://www.biorxiv.org/content/10.1101/807693v1>`_.



The Nafc Task
=============

The :class:`~autopilot.tasks.Nafc` class serves as an example for new task designs.

To demonstrate the general structure of Autopilot tasks, let's build it from scratch.

The :class:`~autopilot.tasks.Task` class
----------------------------------------

We start by subclassing the :class:`~autopilot.tasks.task.Task` class and initializing it.

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

1. A **PARAMS** dictionary defines what parameters are needed to define the task
2. A **Data** (:class:`tables.IsDescription`) descriptor describes what data will be returned from the task
3. A **PLOT** dictionary that maps the data output to graphical elements in the GUI.
4. A **HARDWARE** dictionary that describes what hardware will be needed to run the task.

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

        PARAMS['correction'] = {'tag':  'Correction Trials',
                                'type': 'bool'}

will be used to initialize the task like::

        Nafc(correction=True) # or False

Data
~~~~~~~~

There are two types of data,

* ``TrialData`` - where a single value for several variables is returned per 'trial', and
* ``ContinuousData`` - where values and timestamps are taken continuously, with either a fixed or variable interval

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

The ``TrialData`` object is used by the :class:`~autopilot.data.subject.Subject` class when a task is assigned to create the data storage table.

PLOT
~~~~
The ``PLOT`` dictionary maps the data returned from the task to graphical elements in the :class:`~autopilot.core.terminal.Terminal`'s :class:`~autopilot.core.plots.Plot`.
Specifically, when the task is started, the :class:`~autopilot.core.plots.Plot` object creates the graphical element (eg. a :class:`~autopilot.core.plots.Point`)
and then calls its ``update`` method with any data that is received through its :class:`~autopilot.core.networking.Node`.

Data-to-graphical mappings are defined in a ``data`` subdictionary, and additional parameters can be passed to the plot -- in the below example, for example,
a ``chance_bar`` is drawn as a horizontal line across the plot. By default it is drawn at 0.5, but its height can be set with an additional parameter ``chance_level``.
Available graphical primitives are registered in the :attr:`.plots.PLOT_LIST`, and additional parameters are documented in the :class:`~.plots.Plot` class.

Data is plotted either by trial (default) or by timestamp (if ``PLOT['continuous'] != True``). Numerical data is plotted (on the y-axis) as expected, but
further mappings can be defined by extending the graphical element's ``update`` method -- eg. 'L'(eft) maps to 0 and 'R'(ight) maps to 1 by default.

.. code-block:: python

    PLOT = {
        'data': {
            'target'   : 'point',
            'response' : 'segment',
            'correct'  : 'rollmean'
        },
        'chance_bar'  : True, # Draw a red bar at 50%
        'roll_window' : 50    # n trials to take rolling mean over
    }

The above ``PLOT`` dictionary produces this pretty little plot:

.. todo::
    screenshot of default nafc plot


HARDWARE
~~~~~~~~

The ``HARDWARE`` dictionary maps a hardware type (eg. ``POKES``) and identifier (eg. ``'L'``)
to a :class:`~autopilot.core.hardware.Hardware` object. The task uses the hardware parameterization in the
:mod:`~autopilot.prefs` file (also see :ref:`setup_pilot`) to instantiate each of the hardware objects, so their naming
system must match (ie. there must be a ``prefs.PINS['POKES']['L']`` entry in ``prefs`` for a task that has a
``task.HARDWARE['POKES']['L']`` object).

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

First, the parameters that are given to the task when it is initialized are stored as attributes, either by unpacking ``**kwargs``...

.. code-block:: python

    class Nafc(Task):

        def __init__(**kwargs):
            for key, value in kwargs.items():
                setattr(self, key, value)


Or explicitly, which is recommended as it is more transparent:

.. code-block:: python

    class Nafc(Task):

        def __init__(self, stage_block=None, stim=None, reward=50, req_reward=False,
                     punish_stim=False, punish_dur=100, correction=False, correction_pct=50.,
                     bias_mode=False, bias_threshold=20, current_trial=0, **kwargs):

            self.req_reward     = bool(req_reward)
            self.punish_stim    = bool(punish_stim)
            self.punish_dur     = float(punish_dur)
            self.correction     = bool(correction)
            self.correction_pct = float(correction_pct)/100
            self.bias_mode      = bias_mode
            self.bias_threshold = float(bias_threshold)/100

            # etc...

Then the hardware is instantiated using a method inherited from the :class:`~autopilot.tasks.task.Task` class:

.. code-block:: python

    self.init_hardware()

Stimulus managers need to be instantiated separately. Currently, stimulus management details like
correction trial percentage or bias correction are given as separate parameters, but will be included in the
``stim`` parameter in the future:

.. code-block:: python

    # use the init_manager wrapper to choose the correct stimulus manager
    self.stim_manager = init_manager(stim)

    # give the sounds a function to call when they end
    self.stim_manager.set_triggers(self.stim_end)

    if self.correction:
        self.stim_manager.do_correction(self.correction_pct)

    if self.bias_mode:
        self.stim_manager.do_bias(mode=self.bias_mode,
                                  thresh=self.bias_threshold)


There are a few attributes that can be set at initialization that are unique:

* **stage_block** - if the task is structured such that the :class:`~autopilot.core.pilot.Pilot` calls each stage method and returns the resulting data, this :class:`threading.Event` is used to wait between stages -- an example will be shown below.
* **stages** - an iterator or generator that yields stage methods.

In this example we have structured the task such that its stages (described below) are called in an endless cycle:

.. code-block:: python

    # This allows us to cycle through the task by just repeatedly calling self.stages.next()
    stage_list = [self.request, self.discrim, self.reinforcement]
    self.stages = itertools.cycle(stage_list)


Stage Methods
---------------

The logic of a task is implemented in one or several **stages**. This example Nafc class uses three:

1. ``request`` - precomputes the target and distractor ports, caches the stimulus, and sets the stimulus to play when the center port is entered
2. ``discrim`` - sets the reward and punishment triggers for the target and distractor ports
3. ``reinforcement`` - computes the trial result and readies the task for the next trial.

This task does not call its own stage methods, as we will see in the Wheel task example,
but allows the :class:`~autopilot.core.pilot.Pilot` to control them, and advances through stages using a
``stage_block`` that allows passage whenever a GPIO trigger is activated. Data is returned from each of the stage methods and is then
returned to the :class:`~autopilot.core.terminal.Terminal` by the :class:`~autopilot.core.pilot.Pilot`.

Request
~~~~~~~

First, the ``stage_block`` is cleared so that the task will not advance until one of the triggers is called.
The target and distractor ports are yielded by the ``stim_manager`` along with the stimulus object.

.. code-block:: python


    def request(self, *args, **kwargs):
        # Set the event block
        self.stage_block.clear()

        # get next stim
        self.target, self.distractor, self.stim = self.stim_manager.next_stim()
        # buffer it
        self.stim.buffer()

Then triggers are stored under the name of the trigger (eg. `'C'` for a trigger that comes from the center poke).
All triggers need to be callable, and can be set either individually or as a series, as in this example.
A ``lambda`` function is used to set a trigger with arguments -- the center LED is set from green to blue when the stimulus starts playing.

A single task class can support multiple operating modes depending on its parameters. If the task has been asked to give
request rewards (see :ref:`training`), it adds an additional trigger to open the center solenoid.

.. code-block:: python

        # set the center light to green before the stimulus is played.
        self.set_leds({'C': [0, 255, 0]})

        # Set sound trigger and LEDs
        # We make two triggers to play the sound and change the light color
        change_to_blue = lambda: self.pins['LEDS']['C'].set_color([0,0,255])

        # set triggers
        if self.req_reward is True:
            self.triggers['C'] = [self.stim.play,
                                  self.stim_start,
                                  change_to_blue,
                                  self.pins['PORTS']['C'].open]
        else:
            self.triggers['C'] = [self.stim.play,
                                  self.stim_start,
                                  change_to_blue]

Finally, the data for this stage of the trial is gathered and returned to the Pilot.
Since stimuli have variable numbers and names of parameters, both the table set up by the :class:`~autopilot.data.subject.Subject` and
the data returning routine here extract stimulus parameters programmatically.

.. code-block:: python

        self.current_trial = self.trial_counter.next()
        data = {
            'target'     : self.target,
            'trial_num'  : self.current_trial,
            'correction' : self.correction_trial
        }
        # get stim info and add to data dict
        sound_info = {k:getattr(self.stim, k) for k in self.stim.PARAMS}
        data.update(sound_info)
        data.update({'type':self.stim.type})

        return data

At the end of this function, the center LED is green, and if the subject pokes the center port the stimulus will play and then the next stage method will be called.

The center LED also turns from green to blue when the stimulus begins to play and then turns off when it is finished. This relies on
additional methods that will be explained below.


Discrim
~~~~~~~

The discrim method simply sets the next round of triggers and returns the request timestamp from the current trial.
If either the ``target`` or ``distractor`` ports are triggered, the appropriate solenoid is opened or the ``punish`` method is called.

The ``trial_num`` is returned each stage for an additional layer of redundancy in data alignment.

.. code-block:: python


    def discrim(self,*args,**kwargs):
        # clear stage block to wait for triggers
        self.stage_block.clear()

        # set triggers
        self.triggers[self.target]     = [lambda: self.respond(self.target),
                                          self.pins['PORTS'][self.target].open]
        self.triggers[self.distractor] = [lambda: self.respond(self.distractor),
                                          self.punish]

        # Only data is the timestamp
        data = {'RQ_timestamp' : datetime.datetime.now().isoformat(),
                'trial_num'    : self.current_trial}
        return data


.. todo::

    pigpio can give us 5 microsecond measurement precision for triggers, currently we just use :meth:`datetime.datetime.now()`
    for timestamps, but highly accurate timestamps can be had by stashing the ``ticks`` argument given by pigpio to the
    :meth:`~autopilot.tasks.task.Task.handle_trigger` method. We will implement this if you don't first :)


Reinforcement
~~~~~~~~~~~~~

This method computes the results of the tasks and returns them with another timestamp.
This stage doesn't clear the ``stage_block`` because we want the next trial to be started immediately after
this stage completes.

The results of the current trial are given to the stimulus manager's :meth:`~autopilot.stim.managers.Stimulus_Manager.update` method
so that it can keep track of trial history and do things like bias correction, etc.

The ``TRIAL_END`` flag in the data signals to the :class:`~autopilot.data.subject.Subject` class that the trial is finished
and its row of data should be written to disk. This, along with providing the ``trial_num`` on each stage,
ensure that data is not misaligned between trials.

.. code-block:: python

    def reinforcement(self,*args,**kwargs):

        if self.response == self.target:
            self.correct = 1
        else:
            self.correct = 0

        # update stim manager
        self.stim_manager.update(self.response, self.correct)

        data = {
            'DC_timestamp' : datetime.datetime.now().isoformat(),
            'response'     : self.response,
            'correct'      : self.correct,
            'trial_num'    : self.current_trial,
            'TRIAL_END'    : True
        }
        return data



Additional Methods
------------------

Autopilot doesn't confine the logic of a task to its stage methods, instead users can use additional methods
to give their task additional functionality.

These can range from trivial methods that just store values, such as the ``respond`` and ``stim_start`` methods:

.. code-block:: python


    def respond(self, pin):
        self.response = pin

    def stim_start(self):
        self.discrim_playing = True

To more complex methods that operate effectively like stages, like the ``punish`` method, which flashes the LEDs and plays
a punishment stimulus like white noise if it has been configured to do so:

.. code-block:: python


    def punish(self):
        # clear the punish block to the task doesn't advance while
        # punishment is delivered
        self.punish_block.clear()

        # if there is some punishment stimulus, play it
        if self.punish_stim:
            self.stim_manager.play_punishment()

        # flash LEDs and then clear the block once they are finished.
        self.flash_leds()
        threading.Timer(self.punish_dur / 1000.,
                        self.punish_block.set).start()

Additionally, since we gave the stimulus manager a trigger method that is called
when the stimulus ends, we can turn the light blue when a stimulus is playing, and
turn it off when it finishes

.. code-block:: python

    def stim_end(self):
        """
        called by stimulus callback

        set outside lights blue
        """
        # Called by the discrim sound's table trigger when playback is finished
        # Used in punishing leaving early
        self.discrim_playing = False
        #if not self.bailed and self.current_stage == 1:
        self.set_leds({'L':[0,255,0], 'R':[0,255,0]})



Distributed Go/No-Go - Using Child Agents
=========================================

.. figure:: ../_images/gonogo.png
   :align: right

To demonstrate the use of Child agents, we'll build the distributed Go/No-Go task described in section 4.3 of the Autopilot whitepaper.

In short, a subject runs on a circular running wheel whose velocity is measured by a laser computer mouse.
When the subject 'fixates' by slowing below a threshold velocity, an drifting Gabor grating is presented.
If the grating changes angles, the subject is rewarded if they lick in an IR beambreak sensor.
If the grating doesn't change angles, the subject is rewarded if they refrain from licking until the stimulus has ended.


Additional Prefs
----------------

To use a Child with this task, we will need to have a second Raspberry Pi setup with the same routine as a Pilot, except it needs the following values in its ``prefs.json`` file:

**Child Prefs**

.. code-block:: json

    {
        "NAME" : "wheel_child",
        "LINEAGE" : "CHILD",
        "PARENTID" : "parent_pilot",
        "PARENTIP" : "ip.of.parent.pilot",
        "PARENTPORT": "<MSGPORT of parent>",
    }

And the parent pilot needs to have

**Parent Prefs**

.. code-block:: json

    {
        "NAME": "parent_pilot",
        "CHILDID": "wheel_child",
        "LINEAGE": "PARENT"
    }

Go/No-Go Parameterization
-------------------------

The parameterization for this task is similar to that of the Nafc task above with a few extensions...

.. code-block:: python

    from autopilot.tasks import Task

    class GoNoGo(Task):


        # Task parameterization
        PARAMS = odict()
        PARAMS['reward'] = {'tag': 'Reward Duration (ms)',
                            'type': 'int'}
        PARAMS['timeout']        = {'tag':'Delay Timeout (ms)',
                                    'type':'int'}
        PARAMS['stim'] = {'tag':  'Visuals',
                          'type': 'visuals'}

        # Plot parameterization
        PLOT = {
            'data': {
                'x': 'shaded',
                'target': 'point',
                'response': 'segment'
            },
            # our plot will use time as its x-axis rather than the trial number
            'continuous': True
        }

        # TrialData descriptor
        class TrialData(tables.IsDescription):
            trial_num    = tables.Int32Col()
            target       = tables.BoolCol()
            response     = tables.StringCol(1)
            correct      = tables.Int32Col()
            RQ_timestamp = tables.StringCol(26)
            DC_timestamp = tables.StringCol(26)
            shift        = tables.Float32Col()
            angle        = tables.Float32Col()
            delay        = tables.Float32Col()

We add one additional data descriptor that describes the continuous data that will be sent from the :class:`~autopilot.core.hardware.Wheel` object:

.. code-block:: python

        class ContinuousData(tables.IsDescription):
            x = tables.Float64Col()
            y = tables.Float64Col()
            t = tables.Float64Col()

The hardware specification is also similar, with one additional :class:`~autopilot.core.hardware.Flag` object which
behaves identically to the :class:`~autopilot.core.hardware.Beambreak` object with reversed logic (triggered by 0->1 rather than 1->0).

.. code-block:: python

        HARDWARE = {
            'POKES': {
                'C': hardware.Beambreak,
            },
            'LEDS': {
                'C': hardware.LED_RGB,
            },
            'PORTS': {
                'C': hardware.Solenoid,
            },
            'FLAGS': {
                'F': hardware.Flag
            }
        }

Finally, we add an additional ``CHILDREN`` dictionary to specify the type of Child
that we need to run the task, as well as any additional parameters needed to configure it.

The ``task_type`` must refer to some key in the :data:`autopilot.tasks.CHILDREN_LIST`.

.. note::

    The ``Child`` agent is a subconfiguration of the ``Pilot`` agent, they will be delineated more
    explicitly as the agent framework is solidified.

.. code-block:: python


        CHILDREN = {
            'WHEEL': {
                'task_type': "Wheel Child",
            }
        }

Initialization
--------------

When initializing this task, we need to make our own :class:`~autopilot.core.networking.Net_Node` object
as well as initialize our child. Assuming that the child is
connected to the parent and appropriately configured (see the
additional params above), then things should go smoothly.

.. warning::

    Some of the parameters -- most egregiously the Grating stimulus -- are
    hardcoded in the initialization routine. **This is bad practice** but
    an unfortunately necessary evil because the visual stimulus infrastructure is not well developed yet.

.. code-block:: python

    from autopilot.stim.visual.visuals import Grating

    def __init__(self, stim=None, reward = 50., timeout = 1000., stage_block = None,
                 punish_dur = 500., **kwargs):
        super(GoNoGo, self).__init__()

        # we receive a stage_block from the pilot as usual, we won't use it
        # for task operation though.
        self.stage_block = stage_block
        self.trial_counter = itertools.count()

        # save parameters passed to us as arguments
        self.punish_dur = punish_dur
        self.reward = reward
        self.timeout = timeout
        self.subject = kwargs['subject']


        # init hardware and set reward as before
        self.init_hardware()
        self.set_reward(self.reward)

        # hardcoding stimulus while visual stim still immature
        self.stim = Grating(angle=0, freq=(4,0), rate=1, size=(1,1), debug=True)

        self.stages = itertools.cycle([self.request, self.discrim, self.reinforce])


**Initializing the Net Node.**

The :class:`~autopilot.core.networking.Net_Node` gets the following arguments:

* ``id``: The name that is used to identify the task's networking object so other networking objects can send it messages. We prefix the pilot's ``prefs.NAME`` with ``T_`` because it is a task, though this is not required.
* ``upstream``: The name of the network node that is directly upstream from us, we will be sending our messages to the :class:`~autopilot.core.pilot.Pilot` that is running us -- and thus address it by its name
* ``port``: The port of our upstream mode, most commonly the ``prefs.MSGPORT``
* ``listens``: A dictionary that maps messages with different ``KEY``s to specific handling methods. Since we don't need to receive any data for this task, this is blank,
* ``instance``: Optional, denotes whether this node shouldn't be the only node that exists within the Agent -- ie. it uses the same instance of the ``tornado`` IOLoop as other nodes.

.. code-block:: python

        self.node = Net_Node(id="T_{}".format(prefs.NAME),
                             upstream=prefs.NAME,
                             port=prefs.MSGPORT,
                             listens={},
                             instance=True)

And then to initialize our Child we construct a message to send along to it.

Note that we send the message to ``prefs.NAME`` -- we don't want to have to know the IP address/etc.
for our child because it connects to us -- so the :class:`~autopilot.core.networking.Station` object handles
sending it along with its :meth:`.Pilot_Station.l_child` ``listen``.

.. code-block:: python

        # construct a message to send to the child
        value = {
            'child': {'parent': prefs.NAME, 'subject': self.subject},
            'task_type': self.CHILDREN['WHEEL']['task_type'],
            'subject': self.subject
        }

        # send to the station object with a 'CHILD' key
        self.node.send(to=prefs.NAME, key='CHILD', value=value)

The Child Task
--------------

The :class:`~autopilot.tasks.children.Wheel_Child` task is a very thin
wrapper around a :class:`~autopilot.core.hardware.Wheel` object, which does most of the work.

It creates a ``stages`` iterator with a function that returns nothing to fit in with the general task structure.

.. code-block:: python

    class Wheel_Child(object):
        STAGE_NAMES = ['collect']

        PARAMS = odict()
        PARAMS['fs'] = {'tag': 'Velocity Reporting Rate (Hz)',
                        'type': 'int'}
        PARAMS['thresh'] = {'tag': 'Distance Threshold',
                            'type': 'int'}

        HARDWARE = {
            "OUTPUT": Digital_Out,
            "WHEEL":  Wheel
        }



        def __init__(self, stage_block=None, fs=10, thresh=100, **kwargs):
            self.fs = fs
            self.thresh = thresh

            self.hardware = {}
            self.hardware['OUTPUT'] = Digital_Out(prefs.PINS['OUTPUT'])
            self.hardware['WHEEL'] = Wheel(digi_out = self.hardware['OUTPUT'],
                                           fs       = self.fs,
                                           thresh   = self.thresh,
                                           mode     = "steady")
            self.stages = cycle([self.noop])
            self.stage_block = stage_block

        def noop(self):
            # just fitting in with the task structure.
            self.stage_block.clear()
            return {}

        def end(self):
            self.hardware['WHEEL'].release()
            self.stage_block.set()

.. _wheel_guide_one:

A Very Smart Wheel
------------------


Most of the Child's contribution to the task is performed by the :class:`~autopilot.core.hardware.Wheel` object.

The Wheel accesses a USB mouse connected to the Pilot,
continuously collects its movements, and reports them back to the
Terminal with a specified frequency (``fs``) with an internal :class:`~autopilot.core.networking.Net_Node`

An abbreviated version...

.. code-block:: python

    from inputs import devices

    class Wheel(Hardware):

        def __init__(self, mouse_idx=0, fs=10, thresh=100, thresh_type='dist', start=True,
                     digi_out = False, mode='vel_total', integrate_dur=5):

            self.mouse = devices.mice[mouse_idx]
            self.fs = fs
            self.thresh = thresh
            # time between updates
            self.update_dur = 1./float(self.fs)

The Wheel has three message types,

* ``'MEASURE'`` - the main task is telling us to monitor for a threshold crossing, ie. previous trial is over and it's ready for another one.
* ``'CLEAR'`` - stop measuring for a threshold crossing event!
* ``'STOP'`` - the task is over, clear resources and shut down.

.. code-block:: python

            # initialize networking
            self.listens = {'MEASURE': self.l_measure,
                            'CLEAR'  : self.l_clear,
                            'STOP'   : self.l_stop}

            self.node = Net_Node('wheel_{}'.format(mouse_idx),
                                 upstream=prefs.NAME,
                                 port=prefs.MSGPORT,
                                 listens=self.listens,
                                 )

            # if we are being used in a child object,
            # we send our trigger via a GPIO pin
            self.digi_out = digi_out

            self.thread = None

            if start:
                self.start()

        def start(self):
            self.thread = threading.Thread(target=self._record)
            self.thread.daemon = True
            self.thread.start()

The wheel starts two threads, one that captures mouse movement events and
puts them in a queue, and another that processes movements, transmits them
to the Terminal, and handles the threshold triggers when the subject falls
below a certain velocity.

.. code-block:: python

        def _mouse(self):
            # read mouse movements and put them in a queue
            while self.quit_evt:
                events = self.mouse.read()
                self.q.put(events)

        def _record(self):

            threading.Thread(target=self._mouse).start()

            # a threading.Event is used to terminate the wheel's operation
            while not self.quit_evt.is_set():

            # ... mouse movements are collected into a 2d numpy array ...

            # if the main task has told us to measure for a velocity threshold
            # we check if our recent movements (move) trigger the threshold
            if self.measure_evt.is_set():
                do_trigger = self.check_thresh(move)
                if do_trigger:
                    self.thresh_trig()
                    self.measure_evt.clear()

            # and we report recent movements back to the Terminal
            # the recent velocities and timestamp have been calculated as
            # x_vel, y_vel, and nowtime
            self.node.send(key='CONTINUOUS',
                           value={
                               'x':x_vel,
                               'y':y_vel,
                               't':nowtime
                           })

If the threshold is triggered, a method (...``thresh_trig``...) is called that
sends a voltage pulse through the :class:`~autopilot.core.hardware.Digital_Out`
given to it by the Child task.

.. code-block:: python

        def thresh_trig(self):
            if self.digi_out:
                self.digi_out.pulse()



Go/No-Go Stage Methods
----------------------

After the child is initialized, the Parent pilot begins to call the three stage
functions for the task in a cycle

Very similar to the Nafc task above...

* ``request`` - Tell the Child to begin measuring for a velocity threshold crossing, prepare the stimulus for delivery
* ``discrim`` - Present the stimulus
* ``reinforce`` - Reward the subject if they were correct

The code here has been abbreviated for the purpose of the example:

.. code-block:: python


    def request(self):
        # Set the event lock
        self.stage_block.clear()
        # wait on any ongoing punishment stimulus
        self.punish_block.wait()



        # set triggers
        self.triggers['F'] = [
            lambda: self.stim.play('shift', self.shift )
        ]

        # tell our wheel to start measuring
        self.node.send(to=[prefs.NAME, prefs.CHILDID, 'wheel_0'],
                       key="MEASURE",
                       value={'mode':'steady',
                              'thresh':100})

        # return data from current stage
        self.current_trial = self.trial_counter.next()
        data = {
            'target': self.target, # whether to 'go' or 'not go'
            'shift': self.shift,   # how much to shift the
                                   # angle of the stimulus
            'trial_num': self.current_trial
        }

        return data


    def discrim(self):
        # if the subject licks on a good trial, reward.
        # set a trigger to respond false if delay time elapses
        if self.target:
            self.triggers['C'] = [lambda: self.respond(True), self.pins['PORTS']['C'].open]
            self.triggers['T'] = [lambda: self.respond(False), self.punish]
        # otherwise punish
        else:
            self.triggers['C'] = [lambda: self.respond(True), self.punish]
            self.triggers['T'] = [lambda: self.respond(False), self.pins['PORTS']['C'].open]

        # the stimulus has just started playing, wait a bit and then shift it (if we're gonna
        # choose a random delay
        delay = 0.0
        if self.shift != 0:
            delay = (random()*3000.0)+1000.0
            # a delay timer is set that shifts the stimulus after
            # <delay> milliseconds
            self.delayed_set(delay, 'shift', self.shift)

        # trigger the timeout in 5 seconds
        self.timer = threading.Timer(5.0, self.handle_trigger, args=('T', True, None)).start()

        # return data to the pilot
        data = {
            'delay': delay,
            'RQ_timestamp': datetime.datetime.now().isoformat(),
            'trial_num': self.current_trial
        }

        return data


    def reinforce(self):

        # stop timer if it's still going
        try:
            self.timer.cancel()
        except AttributeError:
            pass
        self.timer = None

        data = {
            'DC_timestamp': datetime.datetime.now().isoformat(),
            'response': self.response,
            'correct': self.correct,
            'trial_num': self.current_trial,
            'TRIAL_END': True
        }
        return data

Viola.
