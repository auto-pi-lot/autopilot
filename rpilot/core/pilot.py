#!/usr/bin/python2.7

"""

"""

__version__ = '0.2'
__author__ = 'Jonny Saunders <jsaunder@uoregon.edu>'

import os
import sys
import datetime
import logging
import argparse
import threading
import time
import socket
import json

import tables

# TODO: This is lazy, make the paths work.
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from rpilot import prefs

if __name__ == '__main__':
    # Parse arguments - this should have been called with a .json prefs file passed
    # We'll try to look in the default location first
    parser = argparse.ArgumentParser(description="Run an RPilot")
    parser.add_argument('-f', '--prefs', help="Location of .json prefs file (created during setup_terminal.py)")
    args = parser.parse_args()

    if not args.prefs:
        prefs_file = '/usr/rpilot/prefs.json'

        if not os.path.exists(prefs_file):
            raise Exception("No Prefs file passed, and file not in default location")

        raise Warning('No prefs file passed, loaded from default location. Should pass explicitly with -p')

    else:
        prefs_file = args.prefs

    prefs.init(prefs_file)
    sys.path.append(os.path.dirname(prefs.REPODIR))

    if hasattr(prefs, 'AUDIOSERVER'):
        if prefs.AUDIOSERVER == 'pyo':
            from rpilot.stim.sound import pyoserver
        elif prefs.AUDIOSERVER == 'jack':
            from rpilot.stim.sound import jackclient

from networking import Pilot_Networking, Net_Node
from rpilot import tasks
import hardware


########################################

class RPilot:
    """
    Drives the Raspberry Pi

    Coordinates the hardware and networking objects to run tasks.

    Typically used with a connection to a :class:`.Terminal` object to
    coordinate multiple mice and tasks, but a high priority for future releases
    is to do the (trivial amount of) work to make this class optionally
    standalone.

    Called as a module with the -f flag to give the location of a prefs file, eg::

        python pilot.py -f prefs_file.json

    if the -f flag is not passed, looks in the default location for prefs
    (ie. `/usr/rpilot/prefs.json`)

    Needs the following prefs (typically established by :mod:`.setup.setup_pilot`):

    * **NAME** - The name used by networking objects to address this Pilot
    * **BASEDIR** - The base directory for rpilot files (/usr/rpilot)
    * **PUSHPORT** - Router port used by the Terminal we connect to.
    * **TERMINALIP** - IP Address of our upstream Terminal.
    * **MSGPORT** - Port used by our own networking object
    * **PINS** - Any hardware and its mapping to GPIO pins. No pins are required to be set, instead each
      task defines which pins it needs. Currently the default configuration asks for

        * POKES - :class:`.hardware.Beambreak`
        * LEDS - :class:`.hardware.LED_RGB`
        * PORTS - :class:`.hardware.Solenoid`

    * **AUDIOSERVER** - Which type, if any, audio server to use (`'jack'`, `'pyo'`, or `'none'`)
    * **NCHANNELS** - Number of audio channels
    * **FS** - Sampling rate of audio output
    * **JACKDSTRING** - string used to start the jackd server, see `the jack manpages <https://linux.die.net/man/1/jackd>`_ eg::

        jackd -P75 -p16 -t2000 -dalsa -dhw:sndrpihifiberry -P -rfs -n3 -s &

    * **PIGPIOMASK** - Binary mask of pins for pigpio to control, see `the pigpio docs <http://abyz.me.uk/rpi/pigpio/pigpiod.html>`_ , eg::

        1111110000111111111111110000

    * **PULLUPS** - Pin (board) numbers to pull up on boot
    * **PULLDOWNS** - Pin (board) numbers to pull down on boot.

    Attributes:
        name (str): The name used to identify ourselves in :mod:`.networking`
        task (:class:`.tasks.Task`): The currently instantiated task
        running (:class:`threading.Event`): Flag used to control task running state
        stage_block (:class:`threading.Event`): Flag given to a task to signal when task stages finish
        file_block (:class:`threading.Event`): Flag used to wait for file transfers
        state (str): 'RUNNING', 'STOPPING', 'IDLE' - signals what this pilot is up to
        pulls (list): list of :class:`~.hardware.Pull` objects to keep pins pulled up or down
        server: Either a :func:`~.sound.pyoserver.pyo_server` or :class:`~.jackclient.JackClient` , sound server.
        node (:class:`.networking.Net_Node`): Our Net_Node we use to communicate with our main networking object
        networking (:class:`.networking.Pilot_Networking`): Our networking object to communicate with the outside world
        ip (str): Our IPv4 address
        listens (dict): Dictionary mapping message keys to methods used to process them.
        logger (:class:`logging.Logger`): Used to log messages and network events.
        log_handler (:class:`logging.FileHandler`): Handler for logging
        log_formatter (:class:`logging.Formatter`): Formats log entries as::

            "%(asctime)s %(levelname)s : %(message)s"
    """

    logger = None
    log_handler = None
    log_formatter = None

    # Events for thread handling
    running = None
    stage_block = None
    file_block = None

    # networking - our internal and external messengers
    node = None
    networking = None

    # audio server
    server = None

    def __init__(self):
        self.name = prefs.NAME
        if prefs.LINEAGE == "CHILD":
            self.child = True
            self.parentid = prefs.PARENTID
        else:
            self.child = False
            self.parentid = 'T'

        self.init_logging()

        # Locks, etc. for threading
        self.running = threading.Event() # Are we running a task?
        self.stage_block = threading.Event() # Are we waiting on stage triggers?
        self.file_block = threading.Event() # Are we waiting on file transfer?

        # Init audio server
        if hasattr(prefs, 'AUDIOSERVER'):
            self.init_audio()

        # Init Networking
        # Listen dictionary - what do we do when we receive different messages?
        self.listens = {
            'START': self.l_start, # We are being passed a task and asked to start it
            'STOP' : self.l_stop, # We are being asked to stop running our task
            'PARAM': self.l_param, # A parameter is being changed
            'CALIBRATE_PORT': self.l_cal_port, # Calibrate a water port
            'CALIBRATE_RESULT': self.l_cal_result # Compute curve and store result
        }

        # spawn_network gives us the independent message-handling process
        self.networking = Pilot_Networking()
        self.networking.start()
        self.node = Net_Node(id = "_{}".format(self.name),
                             upstream = self.name,
                             port = prefs.MSGPORT,
                             listens = self.listens,
                             instance=False)

        # if we need to set pins pulled up or down, do that now
        self.pulls = []
        if hasattr(prefs, 'PULLUPS'):
            for pin in prefs.PULLUPS:
                self.pulls.append(hardware.Pull(int(pin), pud='U'))
        if hasattr(prefs, 'PULLDOWNS'):
            for pin in prefs.PULLDOWNS:
                self.pulls.append(hardware.Pull(int(pin), pud='D'))

        # Set and update state
        self.state = 'IDLE' # or 'Running'
        self.update_state()

        # Since we're starting up, handshake to introduce ourselves
        self.ip = self.get_ip()
        self.handshake()

        #self.blank_LEDs()

        # TODO Synchronize system clock w/ time from terminal.

    def init_logging(self):
        """
        Start logging to a timestamped file in `prefs.LOGDIR`
        """

        timestr = datetime.datetime.now().strftime('%y%m%d_%H%M%S')
        log_file = os.path.join(prefs.LOGDIR, 'Pilots_Log_{}.log'.format(timestr))

        self.logger = logging.getLogger('main')
        self.log_handler = logging.FileHandler(log_file)
        self.log_formatter = logging.Formatter("%(asctime)s %(levelname)s : %(message)s")
        self.log_handler.setFormatter(self.log_formatter)
        self.logger.addHandler(self.log_handler)
        self.logger.setLevel(logging.INFO)
        self.logger.info('Pilot Logging Initiated')

    #################################################################
    # Networking
    #################################################################

    def get_ip(self):
        """
        Get our IP
        """

        # shamelessly stolen from https://www.w3resource.com/python-exercises/python-basic-exercise-55.php
        # variables are badly named because this is just a rough unwrapping of what was a monstrous one-liner

        # get ips that aren't the loopback
        unwrap00 = [ip for ip in socket.gethostbyname_ex(socket.gethostname())[2] if not ip.startswith("127.")][:1]
        # ???
        unwrap01 = [[(s.connect(('8.8.8.8', 53)), s.getsockname()[0], s.close()) for s in [socket.socket(socket.AF_INET, socket.SOCK_DGRAM)]][0][1]]

        unwrap2 = [l for l in (unwrap00,unwrap01) if l][0][0]

        return unwrap2

    def handshake(self):
        """
        Send the terminal our name and IP to signal that we are alive
        """
        # send the terminal some information about ourselves

        # TODO: Report any calibrations that we have

        hello = {'pilot':self.name, 'ip':self.ip, 'state':self.state}

        self.node.send(self.parentid, 'HANDSHAKE', value=hello)

    def update_state(self):
        """
        Send our current state to the Terminal,
        our Networking object will cache this and will handle any
        future requests.
        """
        self.node.send(self.parentid, 'STATE', self.state)

    def l_start(self, value):
        """
        Start running a task.

        Get the task object by using `value['task_type']` to select from
        :data:`.tasks.TASK_LIST` , then feed the rest of `value` as kwargs
        into the task object.

        Calls :meth:`.RPilot.run_task` in a new thread

        Args:
            value (dict): A dictionary of task parameters
        """
        # TODO: If any of the sounds are 'file,' make sure we have them. If not, request them.
        # Value should be a dict of protocol params
        # The networking object should have already checked that we have all the files we need

        # Get the task object by its type
        if 'child' in value.keys():
            task_class = tasks.CHILDREN_LIST[value['task_type']]
        else:
            task_class = tasks.TASK_LIST[value['task_type']]
        # Instantiate the task
        self.stage_block.clear()
        self.task = task_class(stage_block=self.stage_block, **value)

        # Make a group for this mouse if we don't already have one
        self.mouse = value['mouse']

        # Run the task and tell the terminal we have
        self.running.set()
        threading.Thread(target=self.run_task).start()

        self.state = 'RUNNING'
        self.update_state()

        # TODO: Send a message back to the terminal with the runtime if there is one so it can handle timed stops

    def l_stop(self, value):
        """
        Stop the task.

        Clear the running event, set the stage block.

        TODO:
            Do a coherence check between our local file and the Terminal's data.

        Args:
            value: ignored
        """
        # Let the terminal know we're stopping
        # (not stopped yet because we'll still have to sync data, etc.)
        self.state = 'STOPPING'
        self.update_state()

        # We just clear the stage block and reset the running flag here
        # and call the cleanup routine from run_task so it can exit cleanly
        self.running.clear()
        self.stage_block.set()


        # TODO: Cohere here before closing file
        if hasattr(self, 'h5f'):
            self.h5f.close()

        self.state = 'IDLE'
        self.update_state()

    def l_param(self, value):
        """
        Change a task parameter mid-run

        Warning:
            Not Implemented

        Args:
            value:
        """
        pass

    def l_cal_port(self, value):
        port = value['port']
        n_clicks = value['n_clicks']
        open_dur = value['dur']
        iti = value['click_iti']

        threading.Thread(target=self.calibrate_port,args=(port, n_clicks, open_dur, iti)).start()

    def calibrate_port(self, port_name, n_clicks, open_dur, iti):
        pin_num = prefs.PINS['PORTS'][port_name]
        port = hardware.Solenoid(pin_num, duration=int(open_dur))
        msg = {'click_num': 0,
               'pilot': self.name,
               'port': port_name
               }

        iti = float(iti)/1000.0

        cal_name = "Cal_{}".format(self.name)

        for i in range(int(n_clicks)):
            port.open()
            msg['click_num'] = i + 1
            self.node.send(to=cal_name, key='CAL_PROGRESS',
                           value= msg)
            time.sleep(iti)

        port.release()

    def l_cal_result(self, value):
        """
        Save the results of a port calibration

        TODO:
            Compute the LUT/curve.

        """

        cal_fn = os.path.join(prefs.BASEDIR, 'port_calibration.json')

        if os.path.exists(cal_fn):
            with open(cal_fn, 'r') as cal_file:
                calibration = json.load(cal_file)
        else:
            calibration = []

        calibration.extend(value)

        with open(cal_fn, 'w+') as cal_file:
            json.dump(calibration, cal_file)




    #################################################################
    # Hardware Init
    #################################################################

    def init_audio(self):
        """
        Initialize an audio server depending on the value of
        `prefs.AUDIOSERVER`

        * 'pyo' = :func:`.pyoserver.pyo_server`
        * 'jack' = :class:`.jackclient.JackClient`
        """
        if prefs.AUDIOSERVER == 'pyo':
            self.server = pyoserver.pyo_server()
            self.logger.info("pyo server started")
        elif prefs.AUDIOSERVER == 'jack':
            self.server = jackclient.JackClient()
            self.server.start()

    def blank_LEDs(self):
        """
        If any 'LEDS' are defined in `prefs.PINS` ,
        instantiate them, set their color to [0,0,0],
        and then release them.
        """
        if 'LEDS' not in prefs.PINS.keys():
            return

        for position, pins in prefs.PINS['LEDS'].items():
            led = hardware.LED_RGB(pins=pins)
            time.sleep(1.)
            led.set_color(col=[0,0,0])
            led.release()

    #################################################################
    # Trial Running and Management
    #################################################################
    def open_file(self):
        """
        Setup a table to store data locally.

        Opens `prefs.DATADIR/local.h5`, creates a group for the current mouse,
        a new table for the current day.

        Returns:
            (:class:`tables.File`, :class:`tables.Table`,
            :class:`tables.tableextension.Row`): The file, table, and row for the local data table
        """
        local_file = os.path.join(prefs.DATADIR, 'local.h5')
        h5f = tables.open_file(local_file, mode='a')


        try:
            h5f.create_group("/", self.mouse, "Local Data for {}".format(self.mouse))
        except tables.NodeError:
            # already made it
            pass
        mouse_group = h5f.get_node('/', self.mouse)

        # Make a table for today's data, appending a conflict-avoidance int if one already exists
        datestring = datetime.date.today().isoformat()
        conflict_avoid = 0
        while datestring in mouse_group:
            conflict_avoid += 1
            datestring = datetime.date.today().isoformat() + '-' + str(conflict_avoid)


        # Get data table descriptor
        if hasattr(self.task, 'TrialData'):
            table_descriptor = self.task.TrialData



            table = h5f.create_table(mouse_group, datestring, table_descriptor,
                                               "Mouse {} on {}".format(self.mouse, datestring))

            # The Row object is what we write data into as it comes in
            row = table.row
            return h5f, table, row

        else:
            return h5f, None, None

    def run_task(self):
        """
        Called in a new thread, run the task.

        Opens a file with :meth:`~.RPilot.open_file` , then
        continually calls `task.stages.next` to process stages.

        Sends data back to the terminal between every stage.

        Waits for the task to clear `stage_block` between stages.
        """
        # TODO: give a net node to the Task class and let the task run itself.
        # Run as a separate thread, just keeps calling next() and shoveling data

        # do we expect TrialData?
        trial_data = False
        if hasattr(self.task, 'TrialData'):
            trial_data = True

        # Open local file for saving
        h5f, table, row = self.open_file()

        # TODO: Init sending continuous data here

        while True:
            # Calculate next stage data and prep triggers
            data = self.task.stages.next()() # Double parens because next just gives us the function, we still have to call it

            if data:
                data['pilot'] = self.name
                data['mouse'] = self.mouse

                # Send data back to terminal (mouse is identified by the networking object)
                self.node.send('T', 'DATA', data)

                # Store a local copy
                # the task class has a class variable DATA that lets us know which data the row is expecting
                if trial_data:
                    for k, v in data.items():
                        if k in self.task.TrialData.columns.keys():
                            row[k] = v

                # If the trial is over (either completed or bailed), flush the row
                if 'TRIAL_END' in data.keys():
                    row.append()
                    table.flush()

            # Wait on the stage lock to clear
            self.stage_block.wait()

            # If the running flag gets set, we're closing.
            if not self.running.is_set():
                self.task.end()
                self.task = None
                row.append()
                table.flush()
                break

        h5f.flush()
        h5f.close()


if __name__ == "__main__":

    a = RPilot()








