Development Roadmap, Minor To-dos, and all future plans :)

.. _todo:

To-Do
=====

Visions
-----------

*The long view: design, ux, and major functionality projects roughly corresponding to minor semantic versions*

Integrations
~~~~~~~~~~~~

Make autopilot work with...

.. roadmap::
    :title: Open Ephys Integration
    :priority: high
    :dblink: https://groups.google.com/forum/#!topic/autopilot-users/FzcyTWVqRwU

    * write a C extension to the Rhythm API similar to that used by the OpenEphys
      `Rhythm Node <https://github.com/open-ephys/plugin-GUI/tree/master/Plugins/RhythmNode>`_.
    * Enable existing OE configuration files to be loaded and used to configure plugin,
      so ephys data can be collected natively alongside behavioral data.

.. roadmap::
    :title: Multiphoton & High-performance Image Integration
    :priority: high
    :dblink: https://groups.google.com/forum/#!topic/autopilot-users/1kdhNHMp-DI

    * Integrate the Thorlabs multiphoton imaging SDK to allow 2p image acquisition during behavior
    * Integrate the Aravis camera drivers to get away from the closed-source spinnaker SDK


.. roadmap::
    :title: Bonsai Integration
    :priority: low
    :dblink: https://groups.google.com/forum/#!topic/autopilot-users/4DlE9ot9S2Q

    * Write source and sink modules so `Bonsai <https://bonsai-rx.org/>`_ pipelines can be
      used within Autopilot for image processing, acquisition etc.

Closed-Loop Behavior & Processing Pipelines
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    * design a signal/slot architecture like Qt so that hardware devices
    and data streams can be connected with low latency. Ideally something like::

        # directly connecting acceleration in x direction
        # to an LED's brightness
        accelerometer.acceleration.connect('x', LED.brightness)

        # process some video frame and use it to control task stage logic
        camera.frame.transform(
            DLC, **kwargs
        ).connect(
            task.subject_position
        )

    * The pipelining framework should be concurrent, but shouldn't rely on
      :class:`multiprocessing.Queue` s and the like for performance, as transferring data
      between processes requires it to be pickled/unpickled. Instead it should use shared memory, like
      :class:`multiprocessing.shared_memory` available in Python 3.8
    * The pipelining framework should be evented, such that changes in the source parameter are automatically pushed
      through the pipeline without polling. This could be done with a decorator around the ``setter`` method for the sender,
    * The pipelining framework need not be written from scratch, and could use one of Python's existing pipelining frameworks, like

        * `Joblib <https://joblib.readthedocs.io/en/latest/>`_
        * `Luigi <https://luigi.readthedocs.io/en/stable/index.html>`_
        * `pyperator <https://github.com/baffelli/pyperator>`_
        * `streamz <https://streamz.readthedocs.io/en/latest/core.html>`_ (love the ux of this but doesn't seem v mature)

* **Agents**

    * The Agent infrastructure is still immature—the terminal, pilot, and child agents are written as independent classes, rather than with a shared inheritance structure.
      The first step is to build a metaclass for autopilot agents that includes the different prefs setups they need and
      their runtime requirements. Many of the further improvements are discussed in the setup section
    * Child agents need to be easier to spawn and configure, and child tasks lack any formalization at all.

* **Parameters**

    * Autopilot has a lot of types of parameters, and at the moment they all have their own styles. This makes a number of things difficult,
      but primarily it makes it hard to predict which style is needed at any particular time. Instead Autopilot needs a
      generalized ``Param``eter class. It should be able to represent the human readable name of that parameter, the parameter's
      value, the expected data type, whether that parameter is optional, and so on.
    * The parameter class should also be recursive, so parameter sets are not treated distinctly from an
      individual parameter -- eg. a task needs a set of parameters, one of which is a list of hardware. one hardware object
      in that list will have its own list of parameters, and so forth.
    * The parameter class should operate in both directions -- ie. it should be able to represent *set* parameters, as well as
      be able to be used as a specifier of parameters that *need to be set*
    * The parameter class should be cascading, where parameters apply to lower 'levels' of parameterization unless specified otherwise.
      For example, one may want to set ``correction_trials`` on for all stimuli in a task, but be able to turn them off for one
      stimulus in particular. To avoid needing to manually implement layered logic for all objects, handlers should be able to
      assume that a parameter will be passed from parent objects to their children.
    * GUI elements should be automatically populating -- some GUI elements are, like the protocol wizard is capable of populating a list of
      parameters from a task description, but it is incapable of choosing different types of stimulus managers, reading all their parameters,
      and so on. Instead it should be possible to descend through all levels of parameters for all objects in all GUI windows without
      duplicating the effort of implementing the parameterization logic every time.

* **Configuration & Setup**

    * Setup routines and configuration options are currently hard-coded into `npyscreen <https://npyscreen.readthedocs.io/>`_
      forms (see :class:`~.setup.setup_pilot.PilotSetupForm`). ``prefs`` setup needs to be separated into a model-view-controller
      type design where the available prefs and values are made separate from their form.
    * Setup routines should include both the ability to install necessary resources and the ability to check if those
      resources have been installed so that hardware objects can be instantiated freely without setup and configuration
      becoming cumbersome.
    * Currently, Autopilot creates a crude bash script with ``setup_pilot.sh`` to start external processes before Autopilot.
      This makes handling multiple environment types difficult -- ie. one needs to close the program entirely, edit
      the startup script, and restart in order to switch from a primarily auditory to primarily visual experiment.
      Management of external processes should be brought into Autopilot, potentially by using `<sarge https://sarge.readthedocs.io/en/latest/index.html>`_
      or some other process management tool.
    * Autopilot should both install to a virtual environment by default and should have docker containers built for it.
      Further it should be possible to package up your environment for the purposes of experimental replication.

* **UI/UX**

    * The GUI code is now the oldest in the entire library. It needs to be generally overhauled to make use of the tools
      that have been developed since it was written (eg. use of networking modules rather than passing sets of variables around).
    * It should be much easier to read the status of, interact with, and reconfigure agents that are connected to the terminal.
      Currently control of Pilots is relatively opaque and limited, and often requires the user to go read the logs stored on each
      individual pilot to determine what is happening with it. Instead Autopilot should have an additional window that can be used
      to set the parameters, reconfigure, and test each individual Pilot.
    * There are some data -> graphical object mappings available to tasks, but Autopilot needs a fuller grammar of graphics.
      It should be possible to reconfigure plotting in the terminal GUI, and it should be possible to modify short-term
      parameters like bin widths for rolling means.
    * Autopilot shouldn't sprawl into a data visualization library, but it should have some basic post-experiment
      plotting features like plotting task performance and stages over time.
    * Autopilot should have a web interface for browsing data. We are undecided about building a web interface for controlling tasks,
      but it should be possible to download data, do basic visualization, and observe the status of the system
      from a web portal.

* **Tasks**

    * Task design is a bit *too* open at the moment. Tasks need to feel like they have more 'guarantees' on their operation.
      eg. there should be a generalized callback api for triggering events. the existing :meth:`~.Task.handle_trigger` is
      quite limited. There should be an obvious way for users to implement saving/reporting data from
      their tasks.

        * Relatedly, the creation of triggers is pretty awkward and not strictly threadsafe, it should be possible to identify
          triggers in subclasses (eg. a superclass creates some trigger, a subclass should be able to unambiguously identify it
          without having to parse method names, etc)

    * It's possible already to use a python generator to have more complex ordering of task stages,
      eg. instead of using an :class:`itertools.cycle` one could write a generator function that yields task
      stages based on some parameters of the task. There should be an additional manager type, the ``Trial_Manager``, that
      implements some common stage schemes -- cycles, yes, but also DAGs, timed switches, etc. This way tasks could blend
      some intuitive features of finite-state machines while also not being beholden by them.


* **Mesh Networking**

    * Autopilot's networking system at the moment risks either a) being bottlenecked by having to route all data through
      a hierarchical network tree, or b) being indicipherable and impossible to program with  as individual objects and
      streams are capable of setting up arbitrary connections that need to potentially be manually configured. This
      goal is very abstract, but Autopilot should have a mesh-networking protocol.
    * It should be possible for any object to communicate with any other object in the network without name collisions
    * It should be possible to stream data efficiently both point-to-point but also from one producer to many consumers.
    * It should be possible for networking connections to be recovered automatically in the case a node temporarily becomes unavailable.
    * Accordingly, Autopilot should adapt `Zyre <https://github.com/zeromq/zyre>`_ for general communications, and improve
      its file transfer capabilities so that it resembles something like bittorrent.

* **Data**

    * Autopilot's data format shouldn't be yet another standard incompatible with all the others that exist. Autopilot
      should at least implement data translators for, if not adopt outright the Neurodata Without Borders standard.
    * For distributed data acquisition, it makes sense to use a distributed database, so we should consider switching
      data collection infrastructure from .hdf5 files to a database system like PostgreSQL.

* **Hardware Library**

    * Populate `<https://auto-pi-lot.com/hardware>`_ with hardware designs, CAD files, BOMs, and assembly instructions
    * Make a 'thingiverse for experimental hardware' that allows users to browse hardware based on application, materials, etc.


Improvements
------------

*The shorter view: smaller, specific tweaks to improve functionality of existing features roughly corresponding to patches in semantic versioning.*

* **Logging**

    * ensure that all events worth logging are logged across all objects.
    * ensure that the structure of logfiles is intuitive -- one logfile per object type
      (networking, hardware rather than one per each hardware device)
    * logging of experimental conditions is incomplete -- only the git hash of the pilot is stored,
      but the git hash of *all* relevant agents should be stored, and logging should be expanded
      to include ``params`` and system configuration (like ``pip freeze``)
    * logs should also be made both human and machine readable -- use prettyprint for python objects,
      and standardize fields present in logger messages.
    * File and Console log handlers should be split so that users can configure what they want to *see* vs. what they
      want *stored* separately (See `<https://docs.python.org/3/howto/logging-cookbook.html#multiple-handlers-and-formatters>`_)

* **UI/UX**

    * Batch subject creation.
    * Double-clicking a subject should open a window to edit and view task parameters.
    * Drag-and-drop subjects between pilots.
    * Plot parameters should be editable - window roll size, etc.
    * Make a messaging routine where a pilot can display some message on the terminal. this should be used to
      alert the user about any errors in task operation rather than having to inspect the logs on the pilot.
    * The :class:`~gui.Subject_List` remains selectable/editable once a subject has started running, making it unclear
      which subject is running. It should become fixed once a subject is running, or otherwise unambiguously indicate which
      subject is running.
    * Plot elements should have tooltips that give their value -- eg. when hovering over a rolling mean, a tooltip
      should display the current value of the rolling mean as well as other configuration params like how many trials
      it is being computed over.
    * Elements in the GUI should be smarter about resizing, particularly the main window should be able to use a scroll
      bar once the number of subjects forces them off the screen.

* **Hardware**

    * Sound calibration - implement a calibration algorithm that allows speakers to be flattened
    * Implement OpenCL for image processing, specifically decoding on acquisition with OpenCV,
      with VC4CL. See

        * `<https://github.com/doe300/VC4CL/issues/29>`_
        * `<https://github.com/thortex/rpi3-opencv/>`_
        * `<https://github.com/thortex/rpi3-vc4cl/>`_

    * Have hardware objects sense if they are configured on instantiation -- eg. when an audio device is configured,
      check if the system has been configured as well as the hifiberry is in ``setup/presetup_pilot.sh``

* **Synchronization**

    * Autopilot needs a unified system to generate timestamps and synchronize events across pilots.
      Currently we rely on implicit NTP-based synchronization across Pilots, which has ~ms jitter
      when configured optimally, but is ultimately not ideal for precise alignment of data streams,
      eg. ephys sampled at 30kHz. ``pigpio`` should be extended such that a Pilot can generate a
      clock signal that its children synchronize to. With the recent addition of timestamp generation
      within pigpio, that would be one parsimonious way of
    * In order to synchronize audio events with behavioral events, the :class:`~.jackclient.JackClient`
      needs to add a call to ``jack_last_frame_time`` in order to get an accurate time of when sound
      stimuli start and stop (See `<https://jackaudio.org/api/group__TimeFunctions.html>`_)
    * Time synchronization between Terminal and Pilot agents is less important, but having them synchronized
      as much as possible is good. The Terminal should be set up to be an NTP server that Pilots follow.

* **Networking**

    * Multihop messages (eg. send to ``C`` through ``A`` and ``B``) are clumsy. This may be
      irrelevant if Autopilot's network infrastructure is converted a true meshnet, but in the meantime
      networking modules should be better at tracking and using trees of connected nodes.
    * The system of zmq routers and dealers is somewhat cumbersome, and the new radio/dish pattern in zmq
      might be better suited. Previously, we had chosen not to use pub/sub as the publisher is relatively
      inefficient -- it sends every message to every recipient, who filter messages based on their id, but
      the radio/dish method may be more efficient.
    * Network modules should use a thread pool for handling messages, as spawning a new thread for each message
      is needlessly costly

* **Data**

    * Data specification needs to be formalized further -- currently data for a task is described with
      ``tables`` specifiers, ``TrialData`` and ``ContinuousData``, but there are always additional fields --
      particularly from stimuli. The :class:`.Subject` class should be able to create columns and tables for

        * Task data as specified in the task description
        * Stimulus data as specified by a stimulus manager that initializes them. eg. the stimulus manager
          initializes all stimuli for a task, and then is able to yield a description of all columns needed for
          all initialized stimuli. So, for a task that uses

* **Tests** - Currently Autopilot has *no unit tests* (shocked ghasps, monocles falling into brandy glasses).
  We need to implement an automated test suite and continuous integration system in order to make
  community development of Autopilot manageable.

* **Configuration**

    * Rather than require all tasks be developed within the directory structure of Autopilot, Tasks and hardware
      objects should be able to be added to the system in a way that mimcs
      `tensor2tensor <https://github.com/tensorflow/tensor2tensor>`_'s
      `registry <https://github.com/tensorflow/tensor2tensor/blob/master/tensor2tensor/utils/registry.py>`_
      For example, users could specify a list of user directories in ``prefs``, and user-created Hardware/Tasks
      could be decorated with a ``@registry.register_task``.

        * This would additionally solve the awkward :data:`.tasks.TASK_LIST` method of making tasks available by
          name that is used now by having a more formal task registry.

* **Cleanliness & Beauty**

    * Intra-autopilot imports are a bit messy. They should be streamlined so that importing one class from one module
      doesn't spiral out of control and import literally everything in the package.
    * Replace ``getter``- and ``setter``-type methods throughout with ``@properties`` when it would improve the object,
      eg. in the :class:`.JackClient`, the storage/retrieval of all the global module variables could be made much neater
      with ``@property`` methods.
    * Like the :class:`~autopilot.hardware.Hardware` class, top-level metaclasses should be moved to the ``__init__``
      file for the module to avoid awkward imports and extra files like :class:`autopilot.tasks.task.Task`
    * Use :class:`enum.Enum` s all over! eg. things like :data:`autopilot.hardware.gpio.TRIGGER_MAP` etc.

* **Concurrency**

    * Autopilot could be a lot smarter about the way it manages threads and processes!
      It should have a centralized registry of threads and processes to keep track on their status
    * Networking modules and other thread-creating modules should probably create thread pools to avoid
      the overhead of constantly spawning them

* **Decorators** - specific improvements to make autopilot objects magic!

    * :mod:`.hardware.gpio` - try/catch release decorator so don't have to check for attribute error in every subclass!


Bugs
----

*Known bugs that have eluded us thus far*

* The :class:`~.gui.Pilot_Button` doesn't always reflect the availability/unavailability of
  connected pilots. The button model as well as the general heartbeating/status indication
  routines need to be made robust.
* The ``pilot_db.json`` and :class:`~.gui.Subject_List` doesn't check for duplicate subjects
  across Pilots. That shouldn't be a problem generally, but if a subject is switched between
  Pilots that may not be reflected in the generated metadata. Pilot ID needs to be more intimately
  linked to the :class:`~.subject.Subject`.
* If Autopilot needs to be quit harshly, some pigpio-based hardware objects don't quit nicely,
  and the pigpiod service can remain stuck on. Resource release needs to be made more robust
* Network connectivity can be lost if the network hardware is disturbed (in our case the router gets kicked
  from the network it is connected to) and is only reliably recovered by restarting the system. Network connections
  should be able to recover disturbance.
* The use of `off` and `on` is inconsistent between :class:`.Digital_Out` and :class:`.PWM` -- since the PWM
  cleans values (inverts logic, expands range),
* There is ambiguity in setting PWM ranges: using :meth:`.PWM.set` with 0-1 uses the whole range off to on, but
  numbers from 0-:attr:`.PWM.range` can be used as well -- 0-1 is the preferred behavior, but should using
  0-range still be supported as well?


Completed
---------------

*good god we did it*

* :ref:`changelog_v030` - Integrate DeepLabCut
* :ref:`changelog_v030` - Unify installation
* :ref:`changelog_v030` - Upgrade to Python 3
* :ref:`changelog_v030` - Upgrade to PySide 2 & Qt5
* :ref:`changelog_v030` - Generate full timestamps from pigpio rather than ticks
* :ref:`changelog_v030` - Continuous data handling
* :ref:`changelog_v030` - GPIO uses pigpio functions rather than python timing
* :ref:`changelog_v030` - networking modules compress arrays before transfer
* :ref:`changelog_v030` - Images can be acquired from cameras


Lowest Priority
------------------

*Improvements that are very unimportant or strictly for unproductive joy*

* **Classic Mode** - in honor of an ancient piece of software that Autopilot may have descended from,
    add a hidden key that when pressed causes the entire terminal screen to flicker whenever any subject in any pilot
    gets a trial incorrect.

