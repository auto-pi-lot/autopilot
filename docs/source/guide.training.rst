.. _training:

Training a Subject
******************

After you have set up a `Terminal <setup_terminal>`_ and a `Pilot <setup_pilot>`_, launch the Terminal.

.. todo::
    Screenshot of terminal

Connecting the Pilot
--------------------

If the ``TERMINAL_IP`` and port information is correctly set in the ``prefs.json`` file of the Pilot, it should automatically attempt to connect to the Terminal when it starts.
It will send a ``handshake`` message that lets the Terminal know of its existence, its IP address, and its state.
Once the Terminal receives its initial message, it will refresh, adding an entry to its ``pilot_db.json`` file and displaying a control panel for the pilot.

.. todo::
    Screenshot of terminal with pilot

If the Pilot is not automatically detected, a pilot can be manually added with its name and IP using the "New Pilot" command in the file menu.

Creating a Protocol
-------------------

A Protocol is one or a collection of tasks which the subject can 'graduate' through based on configurable graduation criteria.
Protocols are stored as ``.json`` files in the ``protocols`` directory within ``prefs.BASEDIR``.

.. code-block:: json


Creating a Subject
------------------

Running the Task
----------------

close w/ a view of the data.