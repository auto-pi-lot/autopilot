"""
These classes implement the GUI used by the Terminal.

The GUI is built using `PySide2 <https://doc.qt.io/qtforpython/>`_, a Python wrapper around Qt5.

These classes are all currently used only by the :class:`~.autopilot.core.terminal.Terminal`.

If performing any GUI operations in another thread (eg. as a callback from a networking object),
the method must be decorated with `@gui_event` which will call perform the update in the main thread as required by Qt.

.. note::

    Currently, the GUI code is some of the oldest code in the library --
    in particular much of it was developed before the network infrastructure was mature.
    As a result, a lot of modules are interdependent (eg. pass objects between each other).
    This will be corrected before v1.0

"""
import typing
import os
import json
import copy
import datetime
import time
from collections import OrderedDict as odict
import numpy as np
import ast
from PySide2 import QtGui, QtWidgets
import pyqtgraph as pg
import pandas as pd
import itertools
import threading
import multiprocessing as mp
from operator import ior
from functools import reduce

# adding autopilot parent directory to path
from autopilot.core.subject import Subject
from autopilot import prefs
from autopilot.gui import _MAPS
from autopilot.gui.gui import gui_event
from autopilot.networking import Net_Node
from autopilot.core.plots import Video
from autopilot.core.loggers import init_logger
from autopilot.utils import plugins, registry

"""
Maps of shorthand names for objects to the objects themselves.

Grouped by a rough use case, intended for internal (rather than user-facing) use.
"""


####################################
# Control Panel Widgets
###################################


##################################
# Wizard Widgets
################################3#

# TODO: Change these classes to use the update params windows


###################################3
# Tools
######################################

class Bandwidth_Test(QtWidgets.QDialog):
    """
    Test the limits of the rate of messaging from the connected Pilots.

    Asks pilots to send messages at varying rates and with varying payload sizes, and with messages with/without receipts.

    Measures drop rates and message latency

    Attributes:
        rate_list (list): List of rates (Hz) to test
        payload_list (list): List of payload sizes (KB) to test
        messages (list): list of messages received during test
    """

    def __init__(self, pilots):
        super(Bandwidth_Test, self).__init__()

        self.pilots = pilots

        self.rate_list = []
        self.payload_list = []
        self.test_pilots = []
        self.finished_pilots = []
        self.messages = []

        self.results = []
        self.delays = []
        self.drops = []
        self.speeds = []
        self.rates =[]


        self.end_test = threading.Event()
        self.end_test.clear()

        self.listens = {
            'BANDWIDTH_MSG': self.register_msg
        }


        self.node = Net_Node(id="bandwidth",
                             upstream='T',
                             port = prefs.get('MSGPORT'),
                             listens=self.listens)

        self.init_ui()

    def init_ui(self):
        """
        Look we're just making the stuff in the window over here alright? relax.
        """

        # two panes: left selects the pilots and sets params of the test,
        # right plots outcomes

        # main layout l/r
        self.layout = QtWidgets.QHBoxLayout()

        # left layout for settings
        self.settings = QtWidgets.QFormLayout()

        self.n_messages = QtWidgets.QLineEdit('1000')
        self.n_messages.setValidator(QtGui.QIntValidator())

        self.receipts = QtWidgets.QCheckBox('Get receipts?')
        self.receipts.setChecked(True)

        self.rates = QtWidgets.QLineEdit('50')
        self.rates.setObjectName('rates')
        self.rates.editingFinished.connect(self.validate_list)
        self.rate_list = [50]

        self.payloads = QtWidgets.QLineEdit('0')
        self.payloads.setObjectName('payloads')
        self.payloads.editingFinished.connect(self.validate_list)
        self.payload_list = [0]

        # checkboxes for which pis to include in test
        self.pilot_box = QtWidgets.QGroupBox('Pilots')
        self.pilot_checks = {}
        self.pilot_layout = QtWidgets.QVBoxLayout()

        for p in self.pilots.keys():
            cb = QtWidgets.QCheckBox(p)
            cb.setChecked(True)
            self.pilot_checks[p] = cb
            self.pilot_layout.addWidget(cb)

        # gotta have progress bars
        self.all_pbar = QtWidgets.QProgressBar()
        self.this_pbar = QtWidgets.QProgressBar()

        # buttons to start test/save results
        self.start_btn = QtWidgets.QPushButton('Start Test')
        self.start_btn.clicked.connect(self.start)
        self.save_btn = QtWidgets.QPushButton('Save Results')
        self.save_btn.setEnabled(False)
        self.save_btn.clicked.connect(self.save)


        # combine settings
        self.settings.addRow('N messages per test', self.n_messages)
        self.settings.addRow('Confirm sent messages?', self.receipts)
        self.settings.addRow('Message Rates per Pilot \n(in Hz, list of integers like "[1, 2, 3]")',
                             self.rates)
        self.settings.addRow('Payload sizes per message \n(in KB, list of integers like "[32, 64, 128]")',
                             self.payloads)
        self.settings.addRow('Which Pilots to include in test',
                             self.pilot_layout)
        self.settings.addRow('Progress: All tests', self.all_pbar)
        self.settings.addRow('Progress: This test', self.this_pbar)

        self.settings.addRow(self.start_btn, self.save_btn)

        ###########
        # plotting widget
        self.drop_plot = pg.PlotWidget(title='Message Drop Rate')
        self.delay_plot = pg.PlotWidget(title='Mean Delay')
        self.speed_plot = pg.PlotWidget(title='Requested vs. Actual speed')


        # the actual graphical objects that draw stuff for us
        self.drop_line = self.drop_plot.plot(symbol='t', symbolBrush=(100, 100, 255, 50))
        self.delay_line = self.delay_plot.plot(symbol='t', symbolBrush=(100, 100, 255, 50))
        self.speed_line = self.speed_plot.plot(symbol='t', symbolBrush=(100, 100, 255, 50))
        self.drop_line.setPen((255,0,0))
        self.delay_line.setPen((255,0,0))
        self.speed_line.setPen((255,0,0))



        self.plot_layout = QtWidgets.QVBoxLayout()
        self.plot_layout.addWidget(self.drop_plot)
        self.plot_layout.addWidget(self.delay_plot)
        self.plot_layout.addWidget(self.speed_plot)



        # add panes
        self.layout.addLayout(self.settings, 1)
        self.layout.addLayout(self.plot_layout, 1)

        self.setLayout(self.layout)

    def start(self):
        """
        Start the test!!!
        """

        # lists to store our results for plotting and etc.
        self.results = []
        self.delays = []
        self.drops = []
        self.speeds = []
        self.rates =[]

        # first make sure we got everything we need
        if len(self.rate_list) == 0:
            warning_msg = QtWidgets.QMessageBox(QtWidgets.QMessageBox.Warning,
                                            "No rates to test!",
                                            "Couldn't find a list of rates to test, did you enter one?")
            warning_msg.exec_()
            return
        if len(self.payload_list) ==0 :
            warning_msg = QtWidgets.QMessageBox(QtWidgets.QMessageBox.Warning,
                                            "No payloads to test!",
                                            "Couldn't find a list of payloads to test, did you enter one?")
            warning_msg.exec_()
            return

        # get list of checked pis
        test_pilots = []
        for pilot, p_box in self.pilot_checks.items():
            if p_box.isChecked():
                test_pilots.append(pilot)
        self.test_pilots = test_pilots


        # stash some run parameters
        get_receipts = self.receipts.isChecked()
        n_messages = self.n_messages.text()
        # 'n messages for this test' in case user changes it during run
        self.n_messages_test = int(n_messages)



        self.save_btn.setEnabled(False)
        self.start_btn.setEnabled(False)

        # set pbars
        if len(self.payload_list) == 0:
            payload_len = 1
        else:
            payload_len = len(self.payload_list)
        self.all_pbar.setMaximum(len(self.rate_list)*payload_len)
        self.this_pbar.setMaximum(self.n_messages_test*len(test_pilots))
        self.all_pbar.reset()

        # save tests to do, disable play button, and get to doing it
        self.tests_todo = [x for x in itertools.product(self.rate_list, self.payload_list, [self.n_messages_test], [get_receipts])]




        # used to update pbar
        self.test_counter = itertools.count()


        self.current_test = self.tests_todo.pop()
        self.send_test(*self.current_test)
        # # start a timer that continues the test if messages are dropped
        # try:
        #     self.repeat_timer.cancel()
        # except:
        #     pass
        #
        # self.repeat_timer = threading.Timer(self.current_test[0] * self.current_test[2] * 20,
        #                                     self.process_test, args=self.current_test)
        # self.repeat_timer.daemon = True
        # self.repeat_timer.start()



    def send_test(self, rate, payload, n_msg, confirm):
        """
        Send a message describing the test to each of the pilots in :attr:`Bandwidth_Test.test_pilots`

        Args:
            rate (int): Rate of message sending in Hz
            payload (int): Size of message payload in bytes
            n_msg (int): Number of messages to send
            confirm (bool): If True, use message confirmation, if False no confirmation.

        Returns:

        """
        self.finished_pilots = []
        self.messages = []


        msg = {'rate': rate,
               'payload': payload,
               'n_msg': n_msg,
               'confirm': confirm}

        self.end_test.clear()
        self.this_pbar.reset()
        self.msg_counter = itertools.count()

        for p in self.test_pilots:
            self.node.send(to=p, key="BANDWIDTH", value=msg)

    @gui_event
    def process_test(self, rate, n_msg, confirm):
        """
        Process the results of the test and update the plot window.

        Reads message results from :attr:`~Bandwidth_Test.messages`, appends computed results to
        :attr:`~Bandwidth_Test.results`, and starts the next test if any remain.

        Args:
            rate (int): Rate of current test in Hz
            n_msg (int): Number of expected messages in this test
            confirm (bool): Whether message confirmations were enabled for this test.
        """

        # start a timer that continues the test if messages are dropped
        try:
            self.repeat_timer.cancel()
        except:
            pass

        # process messages
        msg_df = pd.DataFrame.from_records(self.messages,
                                           columns=['pilot', 'n_msg', 'timestamp_sent', 'timestamp_rcvd', 'payload_size', 'message_size'])
        msg_df = msg_df.astype({'timestamp_sent':'datetime64', 'timestamp_rcvd':'datetime64'})

        # compute summary
        try:
            mean_delay = np.mean(msg_df['timestamp_rcvd'] - msg_df['timestamp_sent']).total_seconds()
        except AttributeError:
            mean_delay = np.mean(msg_df['timestamp_rcvd'] - msg_df['timestamp_sent'])

        try:
            send_jitter = np.std(msg_df.groupby('pilot').timestamp_sent.diff()).total_seconds()
        except AttributeError:
            print(np.std(msg_df.groupby('pilot').timestamp_sent.diff()))
            send_jitter = np.std(msg_df.groupby('pilot').timestamp_sent.diff())

        try:
            delay_jitter = np.std(msg_df['timestamp_rcvd'] - msg_df['timestamp_sent']).total_seconds()
        except AttributeError:
            delay_jitter = np.std(msg_df['timestamp_rcvd'] - msg_df['timestamp_sent'])

        drop_rate = np.mean(1.0-(msg_df.groupby('pilot').n_msg.count() / float(n_msg)))

        try:
            mean_speed = 1.0/msg_df.groupby('pilot').timestamp_rcvd.diff().mean().total_seconds()
        except AttributeError:
            mean_speed = 1.0/msg_df.groupby('pilot').timestamp_rcvd.diff().mean()

        mean_payload = msg_df.payload_size.mean()
        mean_message = msg_df.message_size.mean()

        #print(msg_df.groupby('pilot').timestamp_rcvd.diff())

        # plot
        self.rates.append(rate)
        self.drops.append(drop_rate)
        self.delays.append(mean_delay)
        self.speeds.append(mean_speed)


        self.results.append((rate, mean_payload, mean_message, n_msg, confirm, len(self.test_pilots), mean_delay, drop_rate, mean_speed, send_jitter, delay_jitter))

        self.delay_line.setData(x=self.rates, y=self.delays)
        self.drop_line.setData(x=self.rates, y=self.drops)
        self.speed_line.setData(x=self.rates, y=self.speeds)
        # self.drop_plot.setYRange(np.min(self.drops), np.max(self.drops),
        #                          padding=(np.max(self.drops) - np.min(self.drops)) * .1)
        # self.delay_plot.setYRange(np.min(self.delays), np.max(self.delays),
        #                           padding=(np.max(self.delays) - np.min(self.delays)) * .1)
        # self.speed_plot.setYRange(np.min(self.speeds), np.max(self.speeds))

        self.all_pbar.setValue(next(self.test_counter) + 1)



        if len(self.tests_todo) == 0:
            self.save_btn.setEnabled(True)
            self.start_btn.setEnabled(True)
        else:
            time.sleep(2.5)
            self.current_test = self.tests_todo.pop()
            self.send_test(*self.current_test)

            # self.repeat_timer = threading.Timer(self.current_test[0]*self.current_test[2]*10,
            #                                     self.process_test, args=self.current_test)
            # self.repeat_timer.daemon = True
            # self.repeat_timer.start()
        self.repaint()



    @gui_event
    def save(self):
        """
        Select save file location for test results (csv) and then save them there

        """

        fileName, filtr = QtWidgets.QFileDialog.getSaveFileName(self,
                "Where should we save these results?",
                prefs.get('DATADIR'),
                "CSV files (*.csv)", "")

        # make and save results df
        try:
            res_df = pd.DataFrame.from_records(self.results,
                                               columns=['rate', 'payload_size', 'message_size', 'n_messages', 'confirm',
                                                        'n_pilots', 'mean_delay', 'drop_rate',
                                                        'actual_rate', 'send_jitter', 'delay_jitter'])

            res_df.to_csv(fileName)
            reply = QtWidgets.QMessageBox.information(self,
                                                  "Results saved!", "Results saved to {}".format(fileName))

        except Exception as e:
            reply = QtWidgets.QMessageBox.critical(self, "Error saving",
                                               "Error while saving your results:\n{}".format(e))




    def register_msg(self, value):
        """
        Receive message from pilot, stash timestamp, number and pilot


        Args:
            value (dict): Value should contain

                * Pilot
                * Timestamp
                * Message number
                * Payload
        """
        # have to iterate over contents to get true size,
        # and then add size of container itself.
        # payload size is distinct from the serialized message size, this is the end size
        # as it ends up on the disk of the receiver
        # pdb.set_trace()
        # payload_size = np.sum([sys.getsizeof(v) for k, v in value.items()]) + sys.getsizeof(value)
        if 'test_end' in value.keys():
            self.finished_pilots.append(value['pilot'])

            if len(self.finished_pilots) == len(self.test_pilots):
                self.process_test(value['rate'], value['n_msg'], value['confirm'])

            return

        payload_size = value['payload_size']




        #payload_size = np.frombuffer(base64.b64decode(value['payload']),dtype=np.bool).nbytes

        self.messages.append((value['pilot'],
                              int(value['n_msg']),
                              value['timestamp'],
                              datetime.datetime.now().isoformat(),
                              payload_size,
                              value['message_size']))

        msgs_rcvd = next(self.msg_counter)
        if msgs_rcvd % float(round(self.n_messages_test/100.0)) < 1.0:
             self.update_pbar(msgs_rcvd+1)



    @gui_event
    def update_pbar(self, val):
        self.this_pbar.setValue(val+1)



    def validate_list(self):
        """
        Checks that the entries in :py:attr:`Bandwidth_Test.rates` and :py:attr:`Bandwidth_Test.payloads` are well formed.

        ie. that they are of the form 'integer, integer, integer'...

        pops a window that warns about ill formed entry and clears line edit if badly formed

        If the list validates, stored as either :py:attr:`Bandwidth_Test.rate_list` or :py:attr:`Bandwidth_Test.payload_list`


        """
        # pdb.set_trace()
        sender = self.sender()

        text = sender.text()

        # user doesn't have to add open/close brackets in input, make sure
        if not text.startswith('['):
            text = '[ ' + text
        if not text.endswith(']'):
            text = text + ' ]'

        # validate form of string
        try:
            a_list = ast.literal_eval(text)
        except SyntaxError:
            warning_msg = QtWidgets.QMessageBox(QtWidgets.QMessageBox.Warning,
                                            "Improperly formatted list!",
                                            "The input received wasn't a properly formatted list of integers. Make sure your input is of the form '1, 2, 3' or '[ 1, 2, 3 ]'\ninstead got : {}".format(text))
            sender.setText('')
            warning_msg.exec_()

            return

        # validate integers
        for i in a_list:
            if not isinstance (i, int):
                warning_msg = QtWidgets.QMessageBox(QtWidgets.QMessageBox.Warning,
                                                "Improperly formatted list!",
                                                "The input received wasn't a properly formatted list of integers. Make sure your input is of the form '1, 2, 3' or '[ 1, 2, 3 ]'\ninstead got : {}".format(
                                                    text))
                sender.setText('')
                warning_msg.exec_()

                return

        # if passes our validation, set list
        if sender.objectName() == 'rates':
            self.rate_list = a_list
        elif sender.objectName() == 'payloads':
            self.payload_list = a_list
        else:
            Warning('Not sure what list this is, object name is: {}'.format(sender.objectName()))











class Calibrate_Water(QtWidgets.QDialog):
    """
    A window to calibrate the volume of water dispensed per ms.
    """
    def __init__(self, pilots):
        """
        Args:
            pilots (:py:attr:`.Terminal.pilots`): A dictionary of pilots
            message_fn (:py:meth:`.Net_Node.send`): The method the Terminal uses to send messages via its net node.
        """
        super(Calibrate_Water, self).__init__()

        self.pilots = pilots
        self.pilot_widgets = {}

        self.init_ui()

    def init_ui(self):
        self.layout = QtWidgets.QVBoxLayout()

        # Container Widget
        self.container = QtWidgets.QWidget()
        # Layout of Container Widget
        self.container_layout = QtWidgets.QVBoxLayout(self)

        self.container.setLayout(self.container_layout)


        screen_geom = QtWidgets.QDesktopWidget().availableGeometry()
        # get max pixel value for each subwidget
        widget_height = np.floor(screen_geom.height()-50/float(len(self.pilots)))


        for p in self.pilots:
            self.pilot_widgets[p] = Pilot_Ports(p)
            self.pilot_widgets[p].setMaximumHeight(widget_height)
            self.pilot_widgets[p].setMaximumWidth(screen_geom.width())
            self.pilot_widgets[p].setSizePolicy(QtWidgets.QSizePolicy.Maximum, QtWidgets.QSizePolicy.Maximum)
            self.container_layout.addWidget(self.pilot_widgets[p])

        # Scroll Area Properties
        self.scroll = QtWidgets.QScrollArea()
        self.scroll.setWidgetResizable(False)
        self.scroll.setWidget(self.container)
        self.layout.addWidget(self.scroll)

        # ok/cancel buttons
        buttonBox = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        buttonBox.accepted.connect(self.accept)
        buttonBox.rejected.connect(self.reject)
        self.layout.addWidget(buttonBox)



        self.setLayout(self.layout)

        # prevent from expanding
        # set max size to screen size

        self.setMaximumHeight(screen_geom.height())
        self.setMaximumWidth(screen_geom.width())
        self.setSizePolicy(QtWidgets.QSizePolicy.Maximum, QtWidgets.QSizePolicy.Maximum)

        self.scrollArea = QtWidgets.QScrollArea(self)
        self.scrollArea.setWidgetResizable(True)



class Pilot_Ports(QtWidgets.QWidget):
    """
    Created by :class:`.Calibrate_Water`, Each pilot's ports and buttons to control repeated release.
    """

    def __init__(self, pilot, n_clicks=1000, click_dur=30):
        """
        Args:
            pilot (str): name of pilot to calibrate
            n_clicks (int): number of times to open the port during calibration
            click_dur (int): how long to open the port (in ms)
        """
        super(Pilot_Ports, self).__init__()

        self.pilot = pilot

        # when starting, stash the duration sent to the pi in case it's changed during.
        self.open_params = {}

        # store volumes per dispense here.
        self.volumes = {}

        self.listens = {
            'CAL_PROGRESS': self.l_progress
        }

        self.node = Net_Node(id="Cal_{}".format(self.pilot),
                             upstream="T",
                             port=prefs.get('MSGPORT'),
                             listens=self.listens)

        self.init_ui()

    def init_ui(self):
        """
        Init the layout for one pilot's ports:

        * pilot name
        * port buttons
        * 3 times and vol dispersed

        :return:
        """

        layout = QtWidgets.QHBoxLayout()
        pilot_lab = QtWidgets.QLabel(self.pilot)
        pilot_font = QtGui.QFont()
        pilot_font.setBold(True)
        pilot_font.setPointSize(14)
        pilot_lab.setFont(pilot_font)
        pilot_lab.setStyleSheet('border: 1px solid black')
        layout.addWidget(pilot_lab)

        # make param setting boxes
        param_layout = QtWidgets.QFormLayout()
        self.n_clicks = QtWidgets.QLineEdit(str(1000))
        self.n_clicks.setSizePolicy(QtWidgets.QSizePolicy.Fixed,QtWidgets.QSizePolicy.Fixed)
        self.n_clicks.setValidator(QtGui.QIntValidator())
        self.interclick_interval = QtWidgets.QLineEdit(str(50))
        self.interclick_interval.setSizePolicy(QtWidgets.QSizePolicy.Fixed,QtWidgets.QSizePolicy.Fixed)
        self.interclick_interval.setValidator(QtGui.QIntValidator())

        param_layout.addRow("n clicks", self.n_clicks)
        param_layout.addRow("interclick (ms)", self.interclick_interval)

        layout.addLayout(param_layout)

        # buttons and fields for each port

        #button_layout = QtWidgets.QVBoxLayout()
        vol_layout = QtWidgets.QGridLayout()

        self.dur_boxes = {}
        self.vol_boxes = {}
        self.pbars = {}
        self.flowrates = {}

        for i, port in enumerate(['L', 'C', 'R']):
            # init empty dict to store volumes and params later
            self.volumes[port] = {}

            # button to start calibration
            port_button = QtWidgets.QPushButton(port)
            port_button.setObjectName(port)
            port_button.clicked.connect(self.start_calibration)
            vol_layout.addWidget(port_button, i, 0)

            # set click duration
            dur_label = QtWidgets.QLabel("Click dur (ms)")
            self.dur_boxes[port] = QtWidgets.QLineEdit(str(20))
            self.dur_boxes[port].setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
            self.dur_boxes[port].setValidator(QtGui.QIntValidator())
            vol_layout.addWidget(dur_label, i, 1)
            vol_layout.addWidget(self.dur_boxes[port], i, 2)

            # Divider
            divider = QtWidgets.QFrame()
            divider.setFrameShape(QtWidgets.QFrame.VLine)
            vol_layout.addWidget(divider, i, 3)

            # input dispensed volume
            vol_label = QtWidgets.QLabel("Dispensed volume (mL)")
            self.vol_boxes[port] = QtWidgets.QLineEdit()
            self.vol_boxes[port].setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
            self.vol_boxes[port].setObjectName(port)
            self.vol_boxes[port].setValidator(QtGui.QDoubleValidator())
            self.vol_boxes[port].textEdited.connect(self.update_volumes)
            vol_layout.addWidget(vol_label, i, 4)
            vol_layout.addWidget(self.vol_boxes[port], i, 5)

            self.pbars[port] = QtWidgets.QProgressBar()
            vol_layout.addWidget(self.pbars[port], i, 6)

            # display flow rate

            #self.flowrates[port] = QtWidgets.QLabel('?uL/ms')
            #self.flowrates[port].setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
            #vol_layout.addWidget(self.flowrates[port], i, 7)

        layout.addLayout(vol_layout)


        self.setLayout(layout)




    def update_volumes(self):
        """
        Store the result of a volume calibration test in :attr:`~Pilot_Ports.volumes`
        """
        port = self.sender().objectName()

        if port in self.open_params.keys():
            open_dur = self.open_params[port]['dur']
            n_clicks = self.open_params[port]['n_clicks']
            click_iti = self.open_params[port]['click_iti']
        else:
            Warning('Volume can only be updated after a calibration has been run')
            return

        vol = float(self.vol_boxes[port].text())

        self.volumes[port][open_dur] = {
            'vol': vol,
            'n_clicks': n_clicks,
            'click_iti': click_iti,
            'timestamp': datetime.datetime.now().isoformat()
        }

        # set flowrate label
        #flowrate = ((vol * 1000.0) / n_clicks) / open_dur
        #frame_geom = self.flowrates[port].frameGeometry()
        #self.flowrates[port].setMaximumHeight(frame_geom.height())


        #self.flowrates[port].setText("{} uL/ms".format(flowrate))

    def start_calibration(self):
        """
        Send the calibration test parameters to the :class:`.Pilot`

        Sends a message with a ``'CALIBRATE_PORT'`` key, which is handled by
        :meth:`.Pilot.l_cal_port`
        """
        port = self.sender().objectName()

        # stash params at the time of starting calibration
        self.open_params[port] = {
            'dur':int(self.dur_boxes[port].text()),
            'n_clicks': int(self.n_clicks.text()),
            'click_iti': int(self.interclick_interval.text())
        }

        self.pbars[port].setMaximum(self.open_params[port]['n_clicks'])
        self.pbars[port].setValue(0)

        msg = self.open_params[port]
        msg.update({'port':port})

        self.node.send(to=self.pilot, key="CALIBRATE_PORT",
                       value=msg)

    @gui_event
    def l_progress(self, value):
        """
        Value should contain

        * Pilot
        * Port
        * Current Click (click_num)

        :param value:
        :return:
        """
        self.pbars[value['port']].setValue(int(value['click_num']))





class Reassign(QtWidgets.QDialog):
    """
    A dialog that lets subjects be batch reassigned to new protocols or steps.
    """
    def __init__(self, subjects, protocols):
        """
        Args:
            subjects (dict): A dictionary that contains each subject's protocol and step, ie.::

                    {'subject_id':['protocol_name', step_int], ... }

            protocols (list): list of protocol files in the `prefs.get('PROTOCOLDIR')`.
                Not entirely sure why we don't just list them ourselves here.
        """
        super(Reassign, self).__init__()

        # FIXME: get logger in a superclass, good god.
        self.logger = init_logger(self)

        self.subjects = subjects
        self.protocols = protocols
        self.protocol_dir = prefs.get('PROTOCOLDIR')
        self.init_ui()

    def init_ui(self):
        """
        Initializes graphical elements.

        Makes a row for each subject where its protocol and step can be changed.
        """
        self.grid = QtWidgets.QGridLayout()

        self.subject_objects = {}

        for i, (subject, protocol) in enumerate(self.subjects.items()):
            subject_name = copy.deepcopy(subject)
            step = protocol[1]
            protocol = protocol[0]

            # subject label
            subject_lab = QtWidgets.QLabel(subject)

            self.subject_objects[subject] = [QtWidgets.QComboBox(), QtWidgets.QComboBox()]
            protocol_box = self.subject_objects[subject][0]
            protocol_box.setObjectName(subject_name)
            protocol_box.insertItems(0, self.protocols)
            # add blank at the end
            # protocol_box.addItem(text='')

            # set current item if subject has matching protocol
            protocol_bool = [protocol == p for p in self.protocols]
            if any(protocol_bool):
                protocol_ind = np.where(protocol_bool)[0][0]
                protocol_box.setCurrentIndex(protocol_ind)
            else:
                # set to blank
                protocol_box.setCurrentIndex(protocol_box.count()-1)

            protocol_box.currentIndexChanged.connect(self.set_protocol)

            # create & populate step box
            step_box = self.subject_objects[subject][1]
            step_box.setObjectName(subject_name)

            self.populate_steps(subject_name)

            if step:
                step_box.setCurrentIndex(step)
            step_box.currentIndexChanged.connect(self.set_step)

            # add to layout
            self.grid.addWidget(subject_lab, i%25, 0+(np.floor(i/25))*3)
            self.grid.addWidget(protocol_box, i%25, 1+(np.floor(i/25))*3)
            self.grid.addWidget(step_box, i%25, 2+(np.floor(i/25))*3)



        buttonBox = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        buttonBox.accepted.connect(self.accept)
        buttonBox.rejected.connect(self.reject)
        main_layout = QtWidgets.QVBoxLayout()
        main_layout.addLayout(self.grid)
        main_layout.addWidget(buttonBox)

        self.setLayout(main_layout)

    def populate_steps(self, subject):
        """
        When a protocol is selected, populate the selection box with the steps that can be chosen.

        Args:
            subject (str): ID of subject whose steps are being populated
        """
        protocol_box = self.subject_objects[subject][0]
        step_box = self.subject_objects[subject][1]

        while step_box.count():
            step_box.removeItem(0)

        # Load the protocol and parse its steps
        protocol_str = protocol_box.currentText()

        # if unassigned, will be the blank string (which evals False here)
        # so do nothing in that case
        if protocol_str:
            protocol_file = os.path.join(self.protocol_dir, protocol_str + '.json')
            try:
                with open(protocol_file) as protocol_file_open:
                    protocol = json.load(protocol_file_open)
            except json.decoder.JSONDecodeError:
                self.logger.exception(f'Steps could not be populated because task could not be loaded due to malformed JSON in protocol file {protocol_file}')
                return
            except Exception:
                self.logger.exception(f'Steps could not be populated due to an unknown error loading {protocol_file}. Catching and continuing to populate window')
                return


            step_list = []
            for i, s in enumerate(protocol):
                step_list.append(s['step_name'])

            step_box.insertItems(0, step_list)



    def set_protocol(self):
        """
        When the protocol is changed, stash that and call :py:meth:`.Reassign.populate_steps` .
        Returns:

        """
        subject = self.sender().objectName()
        protocol_box = self.subject_objects[subject][0]
        step_box = self.subject_objects[subject][1]

        self.subjects[subject][0] = protocol_box.currentText()
        self.subjects[subject][1] = 0

        self.populate_steps(subject)


    def set_step(self):
        """
        When the step is changed, stash that.
        """
        subject = self.sender().objectName()
        protocol_box = self.subject_objects[subject][0]
        step_box = self.subject_objects[subject][1]

        self.subjects[subject][1] = step_box.currentIndex()





class Weights(QtWidgets.QTableWidget):
    """
    A table for viewing and editing the most recent subject weights.
    """
    def __init__(self, subject_weights, subjects):
        """
        Args:
            subject_weights (list): a list of weights of the format returned by
                :py:meth:`.Subject.get_weight(baseline=True)`.
            subjects (dict): the Terminal's :py:attr:`.Terminal.subjects` dictionary of :class:`.Subject` objects.
        """
        super(Weights, self).__init__()

        self.subject_weights = subject_weights
        self.subjects = subjects # subject objects from terminal

        self.colnames = odict()
        self.colnames['subject'] = "Subject"
        self.colnames['date'] = "Date"
        self.colnames['baseline_mass'] = "Baseline"
        self.colnames['minimum_mass'] = "Minimum"
        self.colnames['start'] = 'Starting Mass'
        self.colnames['stop'] = 'Stopping Mass'

        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)

        self.init_ui()

        self.cellChanged.connect(self.set_weight)
        self.changed_cells = [] # if we change cells, store the row, column and value so terminal can update


    def init_ui(self):
        """
        Initialized graphical elements. Literally just filling a table.
        """
        # set shape (rows by cols
        self.shape = (len(self.subject_weights), len(self.colnames.keys()))
        self.setRowCount(self.shape[0])
        self.setColumnCount(self.shape[1])


        for row in range(self.shape[0]):
            for j, col in enumerate(self.colnames.keys()):
                try:
                    if col == "date":
                        format_date = datetime.datetime.strptime(self.subject_weights[row][col], '%y%m%d-%H%M%S')
                        format_date = format_date.strftime('%b %d')
                        item = QtWidgets.QTableWidgetItem(format_date)
                    elif col == "stop":
                        stop_wt = str(self.subject_weights[row][col])
                        minimum = float(self.subject_weights[row]['minimum_mass'])
                        item = QtWidgets.QTableWidgetItem(stop_wt)
                        if float(stop_wt) < minimum:
                            item.setBackground(QtGui.QColor(255,0,0))

                    else:
                        item = QtWidgets.QTableWidgetItem(str(self.subject_weights[row][col]))
                except:
                    item = QtWidgets.QTableWidgetItem(str(self.subject_weights[row][col]))
                self.setItem(row, j, item)

        # make headers
        self.setHorizontalHeaderLabels(list(self.colnames.values()))
        self.resizeColumnsToContents()
        self.updateGeometry()
        self.adjustSize()
        self.sortItems(0)


    def set_weight(self, row, column):
        """
        Updates the most recent weights in :attr:`.gui.Weights.subjects` objects.

        Note:
            Only the daily weight measurements can be changed this way - not subject name, baseline weight, etc.

        Args:
            row (int): row of table
            column (int): column of table
        """

        if column > 3: # if this is one of the daily weights
            new_val = self.item(row, column).text()
            try:
                new_val = float(new_val)
            except ValueError:
                ValueError("New value must be able to be coerced to a float! input: {}".format(new_val))
                return

            # get subject, date and column name
            subject_name = self.item(row, 0).text()
            date = self.subject_weights[row]['date']
            column_name = self.colnames.keys()[column] # recall colnames is an ordered dictionary
            self.subjects[subject_name].set_weight(date, column_name, new_val)

class Plugins(QtWidgets.QDialog):
    """
    Dialog window that allows plugins to be viewed and installed.

    Works by querying the `wiki <https://wiki.auto-pi-lot.com>`_ ,
    find anything in the category ``Autopilot Plugins`` , clone the
    related repo, and reload plugins.

    At the moment this widget is a proof of concept and will be made functional
    asap :)
    """

    def __init__(self):
        super(Plugins, self).__init__()

        self.logger = init_logger(self)
        self.plugins = {}

        self.init_ui()
        self.list_plugins()

    def init_ui(self):
        self.layout = QtWidgets.QGridLayout()

        # top combobox for selecting plugin type
        self.plugin_type = QtWidgets.QComboBox()
        self.plugin_type.addItem("Plugin Type")
        self.plugin_type.addItem('All')
        for ptype in registry.REGISTRIES:
            self.plugin_type.addItem(str(ptype.name).capitalize())
        self.plugin_type.currentIndexChanged.connect(self.select_plugin_type)

        # left panel for listing plugins
        self.plugin_list = QtWidgets.QListWidget()
        self.plugin_list.currentItemChanged.connect(self.select_plugin)
        self.plugin_details = QtWidgets.QFormLayout()

        self.plugin_list.setMinimumWidth(200)
        self.plugin_list.setMinimumHeight(600)

        self.status = QtWidgets.QLabel()
        self.download_button = QtWidgets.QPushButton('Download')
        self.download_button.setDisabled(True)

        # --------------------------------------------------
        # layout

        self.layout.addWidget(self.plugin_type, 0, 0, 1, 2)
        self.layout.addWidget(self.plugin_list, 1, 0, 1, 1)
        self.layout.addLayout(self.plugin_details, 1, 1, 1, 1)
        self.layout.addWidget(self.status, 2, 0, 1, 1)
        self.layout.addWidget(self.download_button, 2, 1, 1, 1)

        self.layout.setRowStretch(0, 1)
        self.layout.setRowStretch(1, 10)
        self.layout.setRowStretch(2, 1)

        self.setLayout(self.layout)

    def list_plugins(self):
        self.status.setText('Querying wiki for plugin list...')

        self.plugins = plugins.list_wiki_plugins()
        self.logger.info(f'got plugins: {self.plugins}')

        self.status.setText(f'Got {len(self.plugins)} plugins')

    def download_plugin(self):
        pass

    def select_plugin_type(self):
        nowtype = self.plugin_type.currentText()


        if nowtype == "Plugin Type":
            return
        elif nowtype == "All":
            plugins = self.plugins.copy()
        else:
            plugins = [plug for plug in self.plugins if plug['Is Autopilot Plugin Type'] == nowtype]

        self.logger.debug(f'showing plugin type {nowtype}, matched {plugins}')

        self.plugin_list.clear()
        for plugin in plugins:
            self.plugin_list.addItem(plugin['name'])

    def select_plugin(self):
        if self.plugin_list.currentItem() is None:
            self.download_button.setDisabled(True)
        else:
            self.download_button.setDisabled(False)

        plugin_name = self.plugin_list.currentItem().text()
        plugin = [p for p in self.plugins if p['name'] == plugin_name][0]

        while self.plugin_details.rowCount() > 0:
            self.plugin_details.removeRow(0)

        for k, v in plugin.items():
            if k == 'name':
                continue
            if isinstance(v, list):
                v = ", ".join(v)
            self.plugin_details.addRow(k, QtWidgets.QLabel(v))






#####################################################
# Custom Autopilot Qt Style
#
# class Autopilot_Style(QtGui.QPlastiqueStyle):
#
#     def __init__(self):
#         super(Autopilot_Style, self).__init__()

class Psychometric(QtWidgets.QDialog):
    """
    A Dialog to select subjects, steps, and variables to use in a psychometric curve plot.

    See :meth:`.Terminal.plot_psychometric`

    Args:
        subjects_protocols (dict): The Terminals :attr:`.Terminal.subjects_protocols` dict

    Attributes:
        plot_params (list): A list of tuples, each consisting of (subject_id, step, variable) to be given to :func:`.viz.plot_psychometric`
    """

    def __init__(self, subjects_protocols):
        super(Psychometric, self).__init__()

        self.subjects = subjects_protocols
        # self.protocols = protocols
        # self.protocol_dir = prefs.get('PROTOCOLDIR')
        self.subject_objects = {}

        self.init_ui()


    def init_ui(self):
        self.grid = QtWidgets.QGridLayout()

        # top row just has checkbox for select all
        check_all = QtWidgets.QCheckBox()
        check_all.stateChanged.connect(self.check_all)

        self.grid.addWidget(check_all, 0,0)
        self.grid.addWidget(QtWidgets.QLabel('Check All'), 0, 1)

        # identical to Reassign, above
        for i, (subject, protocol) in zip(range(len(self.subjects)), self.subjects.items()):
            subject_name = copy.deepcopy(subject)
            step = protocol[1]

            # container for each subject's GUI object
            # checkbox, step, variable
            self.subject_objects[subject] = [QtWidgets.QCheckBox(),  QtWidgets.QComboBox(), QtWidgets.QComboBox(), QtWidgets.QLineEdit()]

            # include checkbox
            checkbox = self.subject_objects[subject][0]
            checkbox.setObjectName(subject_name)
            # checkbox.stateChanged.connect(self.select_subject)
            # self.checks.append(this_checkbox)

            # subject label
            subject_lab = QtWidgets.QLabel(subject_name)

            # protocol_box = self.subject_objects[subject][0]
            # protocol_box.setObjectName(subject_name)
            # protocol_box.insertItems(0, self.protocols)
            # # set current item if subject has matching protocol
            # protocol_bool = [protocol == p for p in self.protocols]
            # if any(protocol_bool):
            #     protocol_ind = np.where(protocol_bool)[0][0]
            #     protocol_box.setCurrentIndex(protocol_ind)
            # protocol_box.currentIndexChanged.connect(self.set_protocol)
            self.populate_steps(subject_name)
            step_box = self.subject_objects[subject][1]
            step_box.setObjectName(subject_name)
            step_box.currentIndexChanged.connect(self.populate_variables)



            # variable box
            var_box = self.subject_objects[subject][2]
            var_box.setObjectName(subject_name)

            # n most recent trials
            n_trials_box = self.subject_objects[subject][3]
            # verify that an int is given
            n_trials_box.setValidator(QtGui.QIntValidator())
            n_trials_box.setText("-1")

            # set index of current step to populate variables
            step_box.setCurrentIndex(step)

            # add layout
            self.grid.addWidget(checkbox, i+1, 0)
            self.grid.addWidget(subject_lab, i+1, 1)
            self.grid.addWidget(step_box, i+1, 2)
            self.grid.addWidget(var_box, i+1, 3)
            self.grid.addWidget(n_trials_box, i+1, 4)

        # finish layout
        buttonBox = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        buttonBox.accepted.connect(self.accept)
        buttonBox.rejected.connect(self.reject)
        main_layout = QtWidgets.QVBoxLayout()
        main_layout.addLayout(self.grid)
        main_layout.addWidget(buttonBox)

        self.setLayout(main_layout)





    def populate_steps(self, subject):
        """
        When a protocol is selected, populate the selection box with the steps that can be chosen.

        Args:
            subject (str): ID of subject whose steps are being populated
        """
        # protocol_str = self.subjects[subject][0]
        step_box = self.subject_objects[subject][1]

        while step_box.count():
            step_box.removeItem(0)

        # open the subject file and use 'current' to get step names
        asub = Subject(subject)

        step_list = []
        for s in asub.current:
            step_list.append(s['step_name'])

        step_box.insertItems(0, step_list)

    def populate_variables(self):
        """
        Fill selection boxes with step and variable names
        """
        # get step number from step box

        subject = self.sender().objectName()
        step_ind = self.subject_objects[subject][1].currentIndex()

        # the variables box
        var_box = self.subject_objects[subject][2]
        while var_box.count():
            var_box.removeItem(0)

        # open the subjet's file and get a description of the data for this
        this_subject = Subject(subject)
        step_data = this_subject.get_trial_data(step=step_ind, what="variables")
        # should only have one step, so denest
        step_data = step_data[step_data.keys()[0]]

        # iterate through variables, only keeping numerics
        add_vars = []
        for col_name, col_type in step_data.items():
            if issubclass(col_type.dtype.type, np.integer) or issubclass(col_type.dtype.type, np.floating):
                add_vars.append(col_name)

        var_box.insertItems(0, add_vars)



    def check_all(self):
        """
        Toggle all checkboxes on or off
        """
        # check states to know if we're toggling everything on or off
        check_states = [objs[0].checkState() for objs in self.subject_objects.values()]

        toggle_on = True
        if all(check_states):
            toggle_on = False


        for objs in self.subject_objects.values():
            if toggle_on:
                objs[0].setCheckState(True)
            else:
                objs[0].setCheckState(False)

    @property
    def plot_params(self):
        """
        Generate parameters for plot to be passed to :func:`.viz.plot_psychometric`

        Returns:
            tuple: (subject_name, step_name, x_var_name, n_trials_back)
        """
        _plot_params = []

        for sub_name, objs in self.subject_objects.items():
            if objs[0].checkState():
                _plot_params.append((
                    sub_name,
                    objs[1].currentText(),
                    objs[2].currentText(),
                    int(objs[3].text())
                ))
        return _plot_params

class Stream_Video(QtWidgets.QDialog):
    """
    Dialogue to stream, display, and save video.

    """

    def __init__(self, pilots:dict, *args, **kwargs):
        """
        Args:
            pilots (dict): The :attr:`.Terminal.pilot_db` with the ``prefs`` of each pilot
                (given by :meth:`.Pilot.handshake`)
        """
        super(Stream_Video, self).__init__(*args, **kwargs)

        self.writer = None # type: typing.Optional['Video_Writer']
        self.writer_q = mp.Queue()
        self.writer_file = ""
        self.writing = threading.Event()
        self.writing.clear()

        self.logger = init_logger(self)

        self.pilots = pilots

        # --------------------------------------------------
        # Parse hardware devices
        # --------------------------------------------------
        self.cameras = {}
        for pilot, pilot_params in self.pilots.items():
            pilot_prefs = pilot_params.get('prefs', None)
            if pilot_prefs is None:
                self.logger.exception(f'pilot {pilot} had no prefs in its pilots_db entry')
                continue

            self.cameras[pilot] = {}

            # iterate through nested hardware dictionary, lookin for cameras
            hardware = pilot_prefs.get('HARDWARE', {'':{}})
            for hw_group, hw_items in hardware.items():
                for hw_id, hw_params in hw_items.items():
                    # if it has cameras in its type (eg. 'cameras.PiCamera')
                    # or a group that starts with cam...
                    if 'cameras' in hw_params.get('type', '') or hw_group.lower().startswith('cam'):
                        # store an abbreviated version of the name and its params for the comboboxes
                        self.cameras[pilot]['.'.join((hw_group, hw_id))] = hw_params


        self.id = f'{prefs.get("NAME")}_video'

        self.video = Video(('stream',))

        self.node = Net_Node(id=self.id,
                             upstream="T",
                             port=prefs.get('MSGPORT'),
                             listens={'CONTINUOUS':self.l_frame},
                             instance=True)

        self.layout = None # type: typing.Optional[QtWidgets.QHBoxLayout]
        self.comboboxes = {} # type: typing.Dict[str, QtWidgets.QComboBox]
        self.buttons = {} # type: typing.Dict[str, QtWidgets.QPushButton]
        self.cam_info = {} # type: typing.Dict[str, typing.Union[QtWidgets.QFormLayout, QtWidgets.QLabel]]

        self._streaming_pilot = '' # keep reference to ID of pilot that was started if combobox values change while streaming
        self._streaming_cam_id = ''

        self.init_ui()
        self.show()

    def init_ui(self):
        self.layout = QtWidgets.QHBoxLayout()

        self.layout.addWidget(self.video,3)

        # --------------------------------------------------
        # Controls layout on right - comboboxes and buttons
        # --------------------------------------------------
        self.button_layout = QtWidgets.QVBoxLayout()

        # combobox to select pilot
        self.comboboxes['pilot'] = QtWidgets.QComboBox()
        self.comboboxes['pilot'].addItem('Select Pilot...')
        for pilot in sorted(self.pilots.keys()):
            self.comboboxes['pilot'].addItem(pilot)
        self.comboboxes['pilot'].currentIndexChanged.connect(self.populate_cameras)

        # and to select camera device
        self.comboboxes['camera'] = QtWidgets.QComboBox()
        self.comboboxes['camera'].addItem('Select Camera...')
        self.comboboxes['camera'].currentIndexChanged.connect(self.camera_selected)

        # buttons to control video
        self.buttons['start'] = QtWidgets.QPushButton('Start Streaming')
        self.buttons['start'].setCheckable(True)
        self.buttons['start'].setChecked(False)
        self.buttons['start'].setDisabled(True)
        self.buttons['start'].toggled.connect(self.toggle_start)

        # save button to start saving frames
        self.buttons['write'] = QtWidgets.QPushButton('Write Video...')
        self.buttons['write'].setCheckable(True)
        self.buttons['write'].setChecked(False)
        self.buttons['write'].setDisabled(True)
        self.buttons['write'].toggled.connect(self.write_video)

        # Infobox to display camera params
        self.cam_info['label'] = QtWidgets.QLabel()
        self.cam_info['form'] = QtWidgets.QFormLayout()

        # --------------------------------------------------
        # add to button layout
        self.button_layout.addWidget(self.comboboxes['pilot'])
        self.button_layout.addWidget(self.comboboxes['camera'])
        self.button_layout.addWidget(self.buttons['start'])
        self.button_layout.addWidget(self.buttons['write'])
        self.button_layout.addWidget(self.cam_info['label'])
        self.button_layout.addLayout(self.cam_info['form'])
        self.button_layout.addStretch(1)

        self.layout.addLayout(self.button_layout, 1)
        self.setLayout(self.layout)

    @property
    def current_pilot(self) -> str:
        return self.comboboxes['pilot'].currentText()

    @property
    def current_camera(self) -> str:
        return self.comboboxes['camera'].currentText()

    def populate_cameras(self):
        current_pilot = self.current_pilot
        self.comboboxes['camera'].clear()
        self._clear_info()
        self.buttons['start'].setChecked(False)
        self.buttons['start'].setDisabled(True)
        self.buttons['write'].setChecked(False)
        self.buttons['write'].setDisabled(True)


        # ignore placeholder text
        if current_pilot in self.cameras.keys():
            self.comboboxes['camera'].addItem('Select Camera...')
            for cam_name in sorted(self.cameras[current_pilot].keys()):
                self.comboboxes['camera'].addItem(cam_name)
        else:
            self.comboboxes['camera'].addItem('No Camera Configured!')



    def camera_selected(self):
        current_pilot = self.current_pilot
        current_camera = self.current_camera

        if current_pilot in self.cameras.keys() and \
                current_camera in self.cameras[current_pilot].keys():
            self.cam_info['label'].setText(current_camera)
            for param_name, param_val in self.cameras[current_pilot][current_camera].items():
                self.cam_info['form'].addRow(param_name, QtWidgets.QLabel(str(param_val)))

            self.buttons['start'].setDisabled(False)

    def toggle_start(self):
        if self.buttons['start'].isChecked():
            # starting!!
            self.comboboxes['pilot'].setDisabled(True)
            self.comboboxes['camera'].setDisabled(True)
            self.buttons['write'].setDisabled(False)
            self._streaming_cam_id = self.current_camera.split('.')[-1]
            self.buttons['start'].setText('Streaming...')
            self.node.send(to=self.current_pilot, key="STREAM_VIDEO",
                           value={
                               'starting': True,
                               'camera': self.current_camera,
                               'stream_to': self.id
                           })
        else:
            self.node.send(to=self.current_pilot, key="STREAM_VIDEO",
                           value={
                               'starting': False,
                               'camera': self.current_camera,
                               'stream_to': self.id
                           })

            if self.buttons['write'].isChecked():
                self.buttons['start'].setDisabled(True)
                self.buttons['write'].toggle()
                while not self.buttons['write'].isEnabled():
                    time.sleep(0.001)
                self.buttons['start'].setDisabled(False)

            self.comboboxes['pilot'].setDisabled(False)
            self.comboboxes['camera'].setDisabled(False)
            self.buttons['write'].setDisabled(True)
            self.buttons['start'].setText('Start Streaming')



    def write_video(self):
        # import here so only import when this particular widget is used.
        # (until we refactor GUI objects)
        from autopilot.hardware.cameras import Video_Writer

        if self.buttons['write'].isChecked():
            if self.writer is None:
                self.writer_file, _ = QtWidgets.QFileDialog.getSaveFileName(
                    self, "Select Output Video Location",
                    prefs.get("DATADIR"),
                    "Video File (*.mp4)"
                )

                # remake queue just in case
                self.writer_q = mp.Queue()

                # try to get fps
                try:
                    fps = int(self.cameras[self.current_pilot][self.current_camera]['fps'])
                except KeyError:
                    self.logger.warning('Camera does not have an "fps" parameter, using 30')
                    fps = 30

                self.writer = Video_Writer(
                    q = self.writer_q,
                    path = self.writer_file,
                    fps=fps,
                    timestamps=True,
                    blosc=False
                )
                self.writer.start()
                self.writing.set()
                self.buttons['write'].setText('Writing')
        else:
            if self.writer is not None:
                self.writing.clear()
                self.writer_q.put('END')

                self.logger.info('Waiting for writer to finish...')
                self.buttons['write'].setDisabled(True)
                while not self.writer_q.empty():
                    self.buttons['write'].setText(f'Writer finishing {self.writer_q.qsize()} frames')
                    time.sleep(0.2)

                # give the writer an additional second if it needs it
                self.writer.join(3)

                if self.writer.exitcode is None:
                    # ask if we want to wait
                    waitforit = pop_dialog(
                        'Wait for writer?',
                        details="Writer isn't finished but queue is empty, wait for it to finish? Otherwise we'll try to terminate it",
                        msg_type='question',
                        buttons=('Ok', 'Abort')
                    )
                    print(waitforit)

                    if waitforit == True:
                        start_time = time.time()
                        while self.writer.exitcode is None:
                            waited = time.time() - start_time
                            self.buttons['write'].setText(f'Waiting for Writer ({waited:.1f})')
                            self.writer.join(0.1)

                    else:
                        self.logger.exception("Had to terminate Video Writer!")
                        self.writer.terminate()

                self.writer = None

                self.buttons['write'].setText("Write Video...")
                self.buttons['write'].setDisabled(False)

    def _clear_info(self):
        self.cam_info['label'].setText('')
        while self.cam_info['form'].count():
            child = self.cam_info['form'].takeAt(0)
            if child.widget():
                child.widget().deleteLater()


    def l_frame(self, value):
        self.video.update_frame('stream', value[self._streaming_cam_id])
        if self.writing.is_set():
            self.writer_q.put_nowait((value['timestamp'],
                                      value[self._streaming_cam_id]))

    def closeEvent(self, arg__1:QtGui.QCloseEvent):

        if self.buttons['start'].isChecked():
            self.buttons['start'].toggle()
            # this will also stop the writer
            max_wait = 10
            waited = 0
            while not self.buttons['start'].isEnabled() and waited < max_wait:
                time.sleep(1)
                waited += 1

        super(Stream_Video, self).closeEvent(arg__1)


def pop_dialog(message:str,
               details:str="",
               buttons:tuple=("Ok",),
               modality:str="nonmodal",
               msg_type:str="info",) -> QtWidgets.QMessageBox:
    """Convenience function to pop a :class:`.QtGui.QDialog window to display a message.

    .. note::

        This function does *not* call `.exec_` on the dialog so that it can be managed by the caller.

    Examples:
        box = pop_dialog(
            message='Hey what up',
            details='i got something to tell you',
            buttons = ('Ok', 'Cancel'))
        ret = box.exec_()
        if ret == box.Ok:
            print("user answered 'Ok'")
        else:
            print("user answered 'Cancel'")

    Args:
        message (str): message to be displayed
        details (str): Additional detailed to be added to the displayed message
        buttons (list): A list specifying which :class:`.QtWidgets.QMessageBox.StandardButton` s to display. Use a string matching the button name, eg. "Ok" gives :class:`.QtWidgets.QMessageBox.Ok`

            The full list of available buttons is::

                ['NoButton', 'Ok', 'Save', 'SaveAll', 'Open', 'Yes', 'YesToAll',
                 'No', 'NoToAll', 'Abort', 'Retry', 'Ignore', 'Close', 'Cancel',
                 'Discard', 'Help', 'Apply', 'Reset', 'RestoreDefaults',
                 'FirstButton', 'LastButton', 'YesAll', 'NoAll', 'Default',
                 'Escape', 'FlagMask', 'ButtonMask']

        modality (str): Window modality to use, one of "modal", "nonmodal" (default). Modal windows block nonmodal windows don't.
        msg_type (str): "info" (default), "question", "warning", or "error" to use :meth:`.QtGui.QMessageBox.information`,
            :meth:`.QtGui.QMessageBox.question`, :meth:`.QtGui.QMessageBox.warning`, or :meth:`.QtGui.QMessageBox.error`,
            respectively

    Returns:
        QtWidgets.QMessageBox
    """

    msgBox = QtWidgets.QMessageBox()

    # set text
    msgBox.setText(message)
    if details:
        msgBox.setInformativeText(details)

    # add buttons
    button_objs = [getattr(QtWidgets.QMessageBox, button) for button in buttons]
    # bitwise or to add them to the dialog box
    # https://www.geeksforgeeks.org/python-bitwise-or-among-list-elements/
    bitwise_buttons = reduce(ior, button_objs)
    msgBox.setStandardButtons(bitwise_buttons)

    if "Ok" in buttons:
        msgBox.setDefaultButton(QtWidgets.QMessageBox.Ok)

    icon = _MAPS['dialog']['icon'].get(msg_type, None)
    if icon is not None:
        msgBox.setIcon(icon)

    modality = _MAPS['dialog']['modality'].get(modality, None)
    if modality is not None:
        msgBox.setWindowModality(modality)

    return msgBox