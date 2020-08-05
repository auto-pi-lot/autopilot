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
import base64
import subprocess
import numpy as np
import pandas as pd
from scipy.stats import linregress

import tables

from autopilot import prefs

if __name__ == '__main__':
    # Parse arguments - this should have been called with a .json prefs file passed
    # We'll try to look in the default location first
    parser = argparse.ArgumentParser(description="Run an autopilot")
    parser.add_argument('-f', '--prefs', help="Location of .json prefs file (created during setup_autopilot.py)")
    args = parser.parse_args()

    if not args.prefs:
        prefs_file = '/usr/autopilot/prefs.json'

        if not os.path.exists(prefs_file):
            raise Exception("No Prefs file passed, and file not in default location")

        raise Warning('No prefs file passed, loaded from default location. Should pass explicitly with -p')

    else:
        prefs_file = args.prefs

    prefs.init(prefs_file)

    if hasattr(prefs, 'AUDIOSERVER') and 'AUDIO' in prefs.CONFIG:
        if prefs.AUDIOSERVER == 'pyo':
            from autopilot.stim.sound import pyoserver
        elif prefs.AUDIOSERVER == 'jack':
            from autopilot.stim.sound import jackclient

from autopilot.core.networking import Pilot_Station, Net_Node, Message
from autopilot import external
from autopilot import tasks
from autopilot.hardware import gpio


########################################

class Pilot:
    """
    Drives the Raspberry Pi

    Coordinates the hardware and networking objects to run tasks.

    Typically used with a connection to a :class:`.Terminal` object to
    coordinate multiple subjects and tasks, but a high priority for future releases
    is to do the (trivial amount of) work to make this class optionally
    standalone.

    Called as a module with the -f flag to give the location of a prefs file, eg::

        python pilot.py -f prefs_file.json

    if the -f flag is not passed, looks in the default location for prefs
    (ie. `/usr/autopilot/prefs.json`)

    Needs the following prefs (typically established by :mod:`.setup.setup_pilot`):

    * **NAME** - The name used by networking objects to address this Pilot
    * **BASEDIR** - The base directory for autopilot files (/usr/autopilot)
    * **PUSHPORT** - Router port used by the Terminal we connect to.
    * **TERMINALIP** - IP Address of our upstream Terminal.
    * **MSGPORT** - Port used by our own networking object
    * **HARDWARE** - Any hardware and its mapping to GPIO pins. No pins are required to be set, instead each
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
        networking (:class:`.networking.Pilot_Station`): Our networking object to communicate with the outside world
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

    def __init__(self, splash=True):

        if splash:
            with open(os.path.join(os.path.dirname(os.path.dirname(__file__)), 'setup', 'welcome_msg.txt'), 'r') as welcome_f:
                welcome = welcome_f.read()
                print('')
                for line in welcome.split('\n'):
                    print(line)
                print('')
                sys.stdout.flush()

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

        # init pigpiod process
        self.init_pigpio()

        # Init audio server
        if hasattr(prefs, 'AUDIOSERVER') and 'AUDIO' in prefs.CONFIG:
            self.init_audio()

        # Init Station
        # Listen dictionary - what do we do when we receive different messages?
        self.listens = {
            'START': self.l_start, # We are being passed a task and asked to start it
            'STOP' : self.l_stop, # We are being asked to stop running our task
            'PARAM': self.l_param, # A parameter is being changed
            'CALIBRATE_PORT': self.l_cal_port, # Calibrate a water port
            'CALIBRATE_RESULT': self.l_cal_result, # Compute curve and store result
            'BANDWIDTH': self.l_bandwidth # test our bandwidth
        }

        # spawn_network gives us the independent message-handling process
        self.networking = Pilot_Station()
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
                self.pulls.append(gpio.Digital_Out(int(pin), pull='U'))
        if hasattr(prefs, 'PULLDOWNS'):
            for pin in prefs.PULLDOWNS:
                self.pulls.append(gpio.Digital_Out(int(pin), pull='D'))

        # check if the calibration file needs to be updated


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
    # Station
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
        our Station object will cache this and will handle any
        future requests.
        """
        self.node.send(self.parentid, 'STATE', self.state, flags={'NOLOG':True})

    def l_start(self, value):
        """
        Start running a task.

        Get the task object by using `value['task_type']` to select from
        :data:`.tasks.TASK_LIST` , then feed the rest of `value` as kwargs
        into the task object.

        Calls :meth:`.autopilot.run_task` in a new thread

        Args:
            value (dict): A dictionary of task parameters
        """
        # TODO: If any of the sounds are 'file,' make sure we have them. If not, request them.
        # Value should be a dict of protocol params
        # The networking object should have already checked that we have all the files we need

        if self.state == "RUNNING" or self.running.is_set():
            self.logger.warning("Asked to a run a task when already running")
            return

        self.state = 'RUNNING'
        self.running.set()
        try:
            # Get the task object by its type
            if 'child' in value.keys():
                task_class = tasks.CHILDREN_LIST[value['task_type']]
            else:
                task_class = tasks.TASK_LIST[value['task_type']]
            # Instantiate the task
            self.stage_block.clear()

            # Make a group for this subject if we don't already have one
            self.subject = value['subject']
            prefs.add('SUBJECT', self.subject)



            # Run the task and tell the terminal we have
            # self.running.set()
            threading.Thread(target=self.run_task, args=(task_class, value)).start()


            self.update_state()
        except Exception as e:
            self.state = "IDLE"
            self.logger.exception("couldn't start task: {}".format(e))

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
        """
        Initiate the :meth:`.calibrate_port` routine.

        Args:
            value (dict): Dictionary of values defining the port calibration to be run, including
                - ``port`` - which port to calibrate
                - ``n_clicks`` - how many openings should be performed
                - ``open_dur`` - how long the valve should be open
                - ``iti`` - 'inter-trial interval`, or how long should we wait between valve openings.

        """
        port = value['port']
        n_clicks = value['n_clicks']
        open_dur = value['dur']
        iti = value['click_iti']

        threading.Thread(target=self.calibrate_port,args=(port, n_clicks, open_dur, iti)).start()

    def calibrate_port(self, port_name, n_clicks, open_dur, iti):
        """
        Run port calibration routine

        Open a :class:`.hardware.gpio.Solenoid` repeatedly,
        measure volume of water dispersed, compute lookup table mapping
        valve open times to volume.

        Continuously sends progress of test with ``CAL_PROGRESS`` messages

        Args:
            port_name (str): Port name as specified in ``prefs``
            n_clicks (int): number of times the valve should be opened
            open_dur (int, float): how long the valve should be opened for in ms
            iti (int, float): how long we should :func:`~time.sleep` between openings

        """
        pin_num = prefs.HARDWARE['PORTS'][port_name]
        port = gpio.Solenoid(pin_num, duration=int(open_dur))
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

        """

        # files for storing raw and fit calibration results
        cal_fn = os.path.join(prefs.BASEDIR, 'port_calibration.json')

        if os.path.exists(cal_fn):
            try:
                with open(cal_fn, 'r') as cal_file:
                    calibration = json.load(cal_file)
            except ValueError:
                # usually no json can be decoded, that's fine calibrations aren't expensive
                calibration = {}
        else:
            calibration = {}

        for port, results in value.items():
            if port in calibration.keys():
                calibration[port].extend(results)
            else:
                calibration[port] = results

        with open(cal_fn, 'w+') as cal_file:
            json.dump(calibration, cal_file)

    def l_bandwidth(self, value):
        """
        Send messages with a poissonian process according to the settings in value
        """
        #turn off logging for now
        self.networking.logger.setLevel(logging.ERROR)
        self.node.logger.setLevel(logging.ERROR)

        n_msg = int(value['n_msg'])
        rate = float(value['rate'])
        payload = int(value['payload'])
        confirm = bool(value['confirm'])

        payload = np.zeros(payload*1024, dtype=np.bool)
        payload_size = sys.getsizeof(payload)

        message = {
            'pilot': self.name,
            'payload': payload,
        }

        # make a fake message to test how large the serialized message is
        test_msg = Message(to='bandwith', key='BANDWIDTH_MSG', value=message, repeat=confirm, flags={'MINPRINT':True},
                           id="test_message", sender="test_sender")
        msg_size = sys.getsizeof(test_msg.serialize())

        message['message_size'] = msg_size
        message['payload_size'] = payload_size

        if rate > 0:
            spacing = 1.0/rate
        else:
            spacing = 0

        # wait for half a second to let the terminal get messages out
        time.sleep(0.25)

        if spacing > 0:
            last_message = time.perf_counter()
            for i in range(n_msg):
                message['n_msg'] = i
                message['timestamp'] = datetime.datetime.now().isoformat()
                self.node.send(to='bandwidth',key='BANDWIDTH_MSG',
                               value=message, repeat=confirm, flags={'MINPRINT':True})
                this_message = time.perf_counter()
                waitfor = np.clip(spacing-(this_message-last_message), 0, spacing)

                #time.sleep(np.random.exponential(1.0/rate))
                # just do linear spacing lol.

                time.sleep(waitfor)
                last_message = time.perf_counter()
        else:
            for i in range(n_msg):
                message['n_msg'] = i
                message['timestamp'] = datetime.datetime.now().isoformat()
                self.node.send(to='bandwidth',key='BANDWIDTH_MSG',
                               value=message, repeat=confirm, flags={'MINPRINT':True})

        self.node.send(to='bandwidth',key='BANDWIDTH_MSG', value={'pilot':self.name, 'test_end':True,
                                                                  'rate': rate, 'payload':payload,
                                                                  'n_msg':n_msg, 'confirm':confirm},
                       flags={'MINPRINT':True})

        #self.networking.set_logging(True)
        #self.node.do_logging.set()



    def calibration_curve(self, path=None, calibration=None):
        """
        # compute curve to compute duration from desired volume

        Args:
            calibration:
            path: If present, use calibration file specified, otherwise use default.
        """

        lut_fn = os.path.join(prefs.BASEDIR, 'port_calibration_fit.json')

        if not calibration:
            # if we weren't given calibration results, load them
            if path:
                open_fn = path
            else:
                open_fn = os.path.join(prefs.BASEDIR, "port_calibration.json")

            with open(open_fn, 'r') as open_f:
                calibration = json.load(open_f)

        luts = {}
        for port, samples in calibration.items():
            sample_df = pd.DataFrame(samples)
            # TODO: Filter for only most recent timestamps

            # volumes are saved in mL because of how they are measured, durations are stored in ms
            # but reward volumes are typically in the uL range, so we make the conversion
            # by multiplying by 1000
            line_fit = linregress((sample_df['vol']/sample_df['n_clicks'])*1000., sample_df['dur'])
            luts[port] = {'intercept': line_fit.intercept,
                          'slope': line_fit.slope}

        # write to file, overwriting any previous
        with open(lut_fn, 'w') as lutf:
            json.dump(luts, lutf)











    #################################################################
    # Hardware Init
    #################################################################

    def init_pigpio(self):
        try:
            self.pigpiod = external.start_pigpiod()
        except ImportError as e:
            self.pigpiod = None
            self.logger.exception(e)

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
            self.jackd = external.start_jackd()
            self.server = jackclient.JackClient()
            self.server.start()
            self.logger.info('Started jack audio server')


    def blank_LEDs(self):
        """
        If any 'LEDS' are defined in `prefs.HARDWARE` ,
        instantiate them, set their color to [0,0,0],
        and then release them.
        """
        if 'LEDS' not in prefs.HARDWARE.keys():
            return

        for position, pins in prefs.HARDWARE['LEDS'].items():
            led = gpio.LED_RGB(pins=pins)
            time.sleep(1.)
            led.set_color(col=[0,0,0])
            led.release()

    #################################################################
    # Trial Running and Management
    #################################################################
    def open_file(self):
        """
        Setup a table to store data locally.

        Opens `prefs.DATADIR/local.h5`, creates a group for the current subject,
        a new table for the current day.

        Returns:
            (:class:`tables.File`, :class:`tables.Table`,
            :class:`tables.tableextension.Row`): The file, table, and row for the local data table
        """
        local_file = os.path.join(prefs.DATADIR, 'local.h5')
        try:
            h5f = tables.open_file(local_file, mode='a')
        except IOError as e:
            self.logger.warning("local file was broken, making new")
            self.logger.warning(e)
            os.remove(local_file)
            h5f = tables.open_file(local_file, mode='w')
            os.chmod(local_file, 0o777)


        try:
            h5f.create_group("/", self.subject, "Local Data for {}".format(self.subject))
        except tables.NodeError:
            # already made it
            pass
        subject_group = h5f.get_node('/', self.subject)

        # Make a table for today's data, appending a conflict-avoidance int if one already exists
        datestring = datetime.date.today().isoformat()
        conflict_avoid = 0
        while datestring in subject_group:
            conflict_avoid += 1
            datestring = datetime.date.today().isoformat() + '-' + str(conflict_avoid)


        # Get data table descriptor
        if hasattr(self.task, 'TrialData'):
            table_descriptor = self.task.TrialData



            table = h5f.create_table(subject_group, datestring, table_descriptor,
                                               "Subject {} on {}".format(self.subject, datestring))

            # The Row object is what we write data into as it comes in
            row = table.row
            return h5f, table, row

        else:
            return h5f, None, None

    def run_task(self, task_class, task_params):
        """
        Called in a new thread, run the task.

        Opens a file with :meth:`~.autopilot.open_file` , then
        continually calls `task.stages.next` to process stages.

        Sends data back to the terminal between every stage.

        Waits for the task to clear `stage_block` between stages.
        """
        # TODO: give a net node to the Task class and let the task run itself.
        # Run as a separate thread, just keeps calling next() and shoveling data
        self.task = task_class(stage_block=self.stage_block, **task_params)

        # do we expect TrialData?
        trial_data = False
        if hasattr(self.task, 'TrialData'):
            trial_data = True

        # Open local file for saving
        h5f, table, row = self.open_file()

        # TODO: Init sending continuous data here

        while True:
            # Calculate next stage data and prep triggers
            data = next(self.task.stages)() # Double parens because next just gives us the function, we still have to call it

            if data:
                data['pilot'] = self.name
                data['subject'] = self.subject

                # Send data back to terminal (subject is identified by the networking object)
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


    a = Pilot()








