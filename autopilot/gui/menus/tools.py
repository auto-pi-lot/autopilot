import copy
import datetime
import json
import os
from collections import OrderedDict as odict

import numpy as np
from PySide6 import QtWidgets, QtGui

from autopilot import prefs
from autopilot.utils.loggers import init_logger
from autopilot.gui.gui import gui_event
from autopilot.networking import Net_Node


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
            protocol_box.addItem('')

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