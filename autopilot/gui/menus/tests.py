import ast
import datetime
import itertools
import threading
import time

import numpy as np
import pandas as pd
import pyqtgraph as pg
from PySide6 import QtWidgets, QtGui

from autopilot import prefs
from autopilot.gui.gui import gui_event
from autopilot.networking import Net_Node
from autopilot.utils.loggers import init_logger


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
        self.node.send('T', 'INIT')
        self.logger = init_logger(self)

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

        self.random = QtWidgets.QCheckBox()
        self.blosc = QtWidgets.QCheckBox()
        self.preserialized = QtWidgets.QCheckBox()

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
        self.settings.addRow('Use Random Arrays? (otherwise zeros)', self.random)
        self.settings.addRow('Compress with blosc?', self.blosc)
        self.settings.addRow('Preserialize message? \n(dont serialize each message separately)', self.preserialized)
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
        random = self.random.isChecked()
        blosc = self.blosc.isChecked()
        preserialized = self.preserialized.isChecked()
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
        self.tests_todo = [x for x in itertools.product(self.rate_list, self.payload_list, [self.n_messages_test], [get_receipts], [blosc], [random], [preserialized])]

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



    def send_test(self, rate:int, payload:int, n_msg:int, confirm:bool, blosc:bool, random:bool, preserialized:bool):
        """
        Send a message describing the test to each of the pilots in :attr:`Bandwidth_Test.test_pilots`

        Args:
            rate (int): Rate of message sending in Hz
            payload (int): Size of message payload in bytes
            n_msg (int): Number of messages to send
            confirm (bool): If True, use message confirmation, if False no confirmation.
            blosc (bool): Use blosc compression?
            random (bool): Use random arrays?
            preserialized (bool): Serialize the message once, rather than serializing every time?

        Returns:

        """
        self.finished_pilots = []
        self.messages = []


        msg = {'rate': rate,
               'payload': payload,
               'n_msg': n_msg,
               'confirm': confirm,
               'blosc':blosc,
               'random':random,
               'preserialized':preserialized
        }

        self.end_test.clear()
        self.this_pbar.reset()
        self.msg_counter = itertools.count()

        for p in self.test_pilots:
            self.node.send(to=p, key="BANDWIDTH", value=msg)

    @gui_event
    def process_test(self, rate, n_msg, confirm, blosc, random, preserialized):
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


        self.results.append((rate, mean_payload, mean_message, n_msg, confirm, blosc, random, preserialized,
                             len(self.test_pilots), mean_delay, drop_rate, mean_speed, send_jitter, delay_jitter))

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
                                                        'blosc', 'random', 'preserialized',
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
                self.process_test(value['rate'], value['n_msg'], value['confirm'], value['blosc'], value['random'], value['preserialized'])

            return

        payload_size = value['payload_size']

        receive_time = datetime.datetime.now().isoformat()

        try:
            if value['payload_n']>0:
                assert isinstance(value['payload'], np.ndarray)
                #print(value['payload'].shape, value['payload_n'], type(value['payload']))
                assert value['payload'].shape[0] == int(value['payload_n']*128)

            self.messages.append((value['pilot'],
                      int(value['n_msg']),
                      value['timestamp'],
                      receive_time,
                      payload_size,
                      value['message_size']))
        except AssertionError:
            self.logger.exception(f"Payload was not a numpy array or didnt have the expected size\ngot a {type(value['payload'])}")

        #payload_size = np.frombuffer(base64.b64decode(value['payload']),dtype=np.bool).nbytes

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