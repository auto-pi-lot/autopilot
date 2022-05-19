# Configuration

```{admonition} idea
Also see the {mod}`.prefs` API documentation page!
```

## Guided Configuration

After installation, set Autopilot up! Autopilot comes with a "guided installation" process where you can select the 
actions you want and they will be run for you. The setup routine will:

* install needed system packages
* prepare your operating system and environment
* set system preferences
* create a user directory (default `~/autopilot`) to store prefs, logs, data, etc.
* create a launch script

To start the guided process, run the following line.

```
python3 -m autopilot.setup
```

### Select Agent

Each runtime of Autopilot is called an "Agent", each of which performs different roles within a system, and thus have different requirements.
If you're running the setup script on the Pi, select "Pilot". If you're running the setup script on a desktop computer, select "Terminal".
If you're configuring multiple Pis, then select "Child" on the child Pis. Then hit "OK".

You can navigate this interface with the arrow keys, tab key, and enter key.

```{image} ../_images/setup_agent_selection.png
:alt: Select an autopilot agent
:width: 100%
```

### Select scripts
Now you will see a menu of potential scripts that can be run.
Select the scripts you want to run, and then hit "OK". Note that even the simplest task ("free water") requires pigpio,
so you may want to include that one. You can see the commands that will be run in each of these scripts with {mod}`.setup.run_script`
in the {data}`.setup.scripts.SCRIPTS` dictionary.


```{image} ../_images/setup_scripts.png
    :alt: Select scripts to setup environment
    :width: 100%
```

```{note}
Autopilot uses a slightly modified version of pigpio (https://github.com/sneakers-the-rat/pigpio) that allows it to
get absolute timestamps (rather than system ticks) from gpio callbacks, increases the max number of scripts, etc. so
if you have a different version of pigpio installed you will need to remove it and replace it with this one (you can
do so with ``python -m autopilot.setup.run_script pigpiod``
```

### Configure Agent

Each agent has a set of systemwide preferences stored in ``<AUTOPILOT_DIR>/prefs.json`` and accessible from {mod}`autopilot.prefs`.

```{image} ../_images/setup_agent.png
:alt: Set systemwide prefs
:width: 100%
```

### Configure Hardware

If configuring a Pilot, you'll be asked to configure your hardware.

Press ``ctrl+x`` to add Hardware, and fill in the relevant parameters (most are optional and can be left blank).
Consult the relevant page on the docs to see which arguments are relevant and how to use them.

```{image}  ../_images/setup_hardware.gif
:alt: Configure Hardware
:width: 100%
```

After completing this step, the file `prefs.json` will be created if necessary and populated with the information you just provided.
If it already exists, it will modified with the new information while preserving the previous preferences.

You can also manually edit the prefs.json file if you prefer.
an [example prefs file](https://github.com/auto-pi-lot/autopilot/blob/main/examples/prefs/pilot_prefs.json) for the Pilot is available
that defines the ports, LEDs, and solenoids that are necessary for the "free water" task, which may be a useful way to get started.

### Testing the Installation

A launch script should have been created by {mod}`~autopilot.setup.setup_autopilot` at ``<AUTOPILOT_DIR>/launch_autopilot.sh`` --
this is the primary entrypoint to autopilot, as it allows certain system-level commands to precede launch (eg.
activating virtual environments, enlarging shared memory, killing conflicting processes, launching an x server, etc.).

To launch autopilot::

    ~/autopilot/launch_autopilot.sh

```{note}
Selecting the script ``alias`` in {mod}`~autopilot.setup.setup_autopilot` allows you to call the launch script by just typing ``autopilot``
```

The actual launch call to autopilot resembles:

```
python3 -m autopilot.agents.<AGENT_NAME> -f ~/autopilot/prefs.json
```

## Networking

```{note}
Networking is a point of major future development, particularly how agents discover one another and how ports are assigned.
Getting networking to work is still a bit cumbersome, but you can track progress or contribute to improving networking
at [issue #48](https://github.com/auto-pi-lot/autopilot/issues/48)
```

### IP Addresses

Pilots connect to a terminal whose IP address is specified as ``TERMINALIP`` in ``prefs.json``

The Pilot and Terminal devices must be on the same network and capable of reaching one another.
You can get your local IP with `ifconfig -a` or `ip addr`

Let's say your Terminal is at 192.168.1.42 and your Pilot is at 192.168.1.200. Replace these values with whatever you actually found before.

Then, you can test that each device can see the other with ping. On the Terminal, run::

    ping 192.168.1.200

And on the Pilot, run::

    ping 192.168.1.42

If that doesn't work, there is something preventing the computers from communicating from one another, typically this is the
case if the computers are on university/etc. internet that makes it difficult for devices to connect to one another. We
recommend networking agents together using a local router or switch (though some have reported being able to
[use their smartphone's hotspot in a pinch](https://groups.google.com/g/autopilot-users/c/JvWIPpYY0TI/m/fzSBET8PAAAJ).

### Ports

Agents use two prefs to configure their ports

* ``MSGPORT`` is the port that the agent receives messages on
* ``PUSHPORT`` is the port of the 'upstream' agent that it connects to.

So, if connecting a Pilot to a Terminal, the ``PUSHPORT`` of the Pilot should match the ``MSGPORT`` of the Terminal.

Ports need to be "open," but the central operation of a firewall is to "close" them. To open a port if, for example,
you are using ``ufw`` on ubuntu (replacing with whatever port you're trying to open to whatever ip address)::

    sudo ufw allow from 192.168.1.200 to any port 5560


