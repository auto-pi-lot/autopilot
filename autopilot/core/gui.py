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
import sys
import typing
import os
import json
import copy
import datetime
import time
from collections import OrderedDict as odict
import numpy as np
import ast
from PySide2 import QtGui, QtCore, QtWidgets
import pyqtgraph as pg
import pandas as pd
import itertools
import threading
from queue import Empty, Full
import multiprocessing as mp
import logging
from operator import ior
from functools import reduce
from collections import abc

# adding autopilot parent directory to path
import autopilot
from autopilot.core.subject import Subject
from autopilot import prefs
from autopilot.stim.sound import sounds
from autopilot.networking import Net_Node
from functools import wraps
from autopilot.utils.invoker import InvokeEvent, get_invoker
from autopilot.core import styles
from autopilot.core.plots import Video
from autopilot.core.loggers import init_logger
from autopilot.utils import plugins, registry, wiki

_MAPS = {
    'dialog': {
        'icon': {
            'info': QtWidgets.QMessageBox.Information,
            'question': QtWidgets.QMessageBox.Question,
            'warning': QtWidgets.QMessageBox.Warning,
            'error': QtWidgets.QMessageBox.Critical
        },
        'modality': {
            'modal': QtCore.Qt.NonModal,
            'nonmodal': QtCore.Qt.WindowModal
        }
    }
}
"""
Maps of shorthand names for objects to the objects themselves.

Grouped by a rough use case, intended for internal (rather than user-facing) use.
"""


def gui_event(fn):
    """
    Wrapper/decorator around an event that posts GUI events back to the main
    thread that our window is running in.

    Args:
        fn (callable): a function that does something to the GUI
    """
    @wraps(fn)
    def wrapper_gui_event(*args, **kwargs):
        """

        Args:
            *args ():
            **kwargs ():
        """
        QtCore.QCoreApplication.postEvent(get_invoker(), InvokeEvent(fn, *args, **kwargs))
    return wrapper_gui_event


class Control_Panel(QtWidgets.QWidget):
    """A :class:`QtWidgets.QWidget` that contains the controls for all pilots.

    Args:
        subjects (dict): See :py:attr:`.Control_Panel.subjects`
        start_fn (:py:meth:`~autopilot.core.terminal.Terminal.toggle_start`): the Terminal's
            toggle_start function, propagated down to each :class:`~core.gui.Pilot_Button`
        pilots: Usually the Terminal's :py:attr:`~.Terminal.pilots` dict. If not passed,
            will try to load :py:attr:`.params.PILOT_DB`

    Attributes:
        subjects (dict): A dictionary with subject ID's as keys and
                :class:`core.subject.Subject` objects as values. Shared with the
                Terminal object to manage access conflicts.
        start_fn (:py:meth:`~autopilot.core.terminal.Terminal.toggle_start`): See :py:attr:`.Control_Panel.start_fn`
        pilots (dict): A dictionary with pilot ID's as keys and nested dictionaries
                    containing subjects, IP, etc. as values
        subject_lists (dict): A dict mapping subject ID to :py:class:`.subject_List`
        layout (:py:class:`~QtWidgets.QGridLayout`): Layout grid for widget
        panels (dict): A dict mapping pilot name to the relevant :py:class:`.Pilot_Panel`

    Specifically, for each pilot, it contains

    * one :class:`subject_List`: A list of the subjects that run in each pilot.
    * one :class:`Pilot_Panel`: A set of button controls for starting/stopping behavior

    This class should not be instantiated outside the context of a
    :py:class:`~.terminal.Terminal` object, as they share the :py:attr:`.subjects` dictionary.

    """
    # Hosts two nested tab widgets to select pilot and subject,
    # set params, run subjects, etc.

    def __init__(self, subjects, start_fn, ping_fn, pilots):
        """

        """
        super(Control_Panel, self).__init__()

        self.logger = init_logger(self)

        # We share a dict of subject objects with the main Terminal class to avoid access conflicts
        self.subjects = subjects

        # We get the Terminal's send_message function so we can communicate directly from here
        self.start_fn = start_fn
        self.ping_fn = ping_fn
        self.pilots = pilots


        # Make dict to store handles to subjects lists
        self.subject_lists = {}
        self.panels = {}

        # Set layout for whole widget
        self.layout = QtWidgets.QGridLayout()
        self.layout.setContentsMargins(0,0,0,0)
        self.layout.setSpacing(0)
        self.setLayout(self.layout)

        self.init_ui()

        # self.setSizePolicy(QtWidgets.QSizePolicy.Maximum,QtWidgets.QSizePolicy.Maximum)
        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding,QtWidgets.QSizePolicy.Expanding)

        self.setStyleSheet(styles.CONTROL_PANEL)

    def init_ui(self):
        """
        Called on init, creates the UI components.

        Specifically, for each pilot in :py:attr:`.pilots`,
        make a :class:`subject_List`: and :class:`Pilot_Panel`:,
        set size policies and connect Qt signals.
        """
        self.layout.setColumnStretch(0, 2)
        self.layout.setColumnStretch(1, 2)

        for pilot_id, pilot_params in self.pilots.items():
            self.add_pilot(pilot_id, pilot_params.get('subjects', []))

    @gui_event
    def add_pilot(self, pilot_id:str, subjects:typing.Optional[list]=None):
        """
        Add a :class:`.Pilot_Panel` for a new pilot, and populate a :class:`.Subject_List` for it
        Args:
         pilot_id (str): ID of new pilot
         subjects (list): Optional, list of any subjects that the pilot has.
        Returns:
        """
        if subjects is None:
            subjects = []

        # Make a list of subjects
        subject_list = Subject_List(subjects, drop_fn=self.update_db)
        subject_list.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        # subject_list.itemDoubleClicked.connect(self.edit_params)
        self.subject_lists[pilot_id] = subject_list

        # Make a panel for pilot control
        pilot_panel = Pilot_Panel(pilot_id, subject_list, self.start_fn, self.ping_fn, self.create_subject)
        pilot_panel.setFixedWidth(150)
        self.panels[pilot_id] = pilot_panel

        row_idx = self.layout.rowCount()

        self.layout.addWidget(pilot_panel, row_idx, 1, 1, 1)
        self.layout.addWidget(subject_list, row_idx, 2, 1, 1)

    def create_subject(self, pilot):
        """
        Becomes :py:attr:`.Pilot_Panel.create_fn`.
        Opens a :py:class:`.New_Subject_Wizard` to create a new subject file and assign protocol.
        Finally, adds the new subject to the :py:attr:`~.Control_Panel.pilots` database and updates it.

        Args:
            pilot (str): Pilot name passed from :py:class:`.Pilot_Panel`, added to the created Subject object.
        """
        new_subject_wizard = New_Subject_Wizard()
        new_subject_wizard.exec_()

        # If the wizard completed successfully, get its values
        if new_subject_wizard.result() == 1:

            biography_vals = new_subject_wizard.bio_tab.values
            self.logger.debug(f'subject wizard exited with 1, got biography vals {biography_vals}')
            # TODO: Make a "session" history table that stashes pilot, git hash, step, etc. for each session - subjects might run on different pilots
            biography_vals['pilot'] = pilot

            # Make a new subject object, make it temporary because we want to close it
            subject_obj = Subject(biography_vals['id'], new=True,
                                biography=biography_vals)
            self.subjects[biography_vals['id']] = subject_obj

            # If a protocol was selected in the subject wizard, assign it.
            try:
                protocol_vals = new_subject_wizard.task_tab.values
                if 'protocol' in protocol_vals.keys() and 'step' in protocol_vals.keys():
                    protocol_file = os.path.join(prefs.get('PROTOCOLDIR'), protocol_vals['protocol'] + '.json')
                    subject_obj.assign_protocol(protocol_file, int(protocol_vals['step']))
                    self.logger.debug(f'assigned protocol with {protocol_vals}')
                else:
                    self.logger.warning(f'protocol couldnt be assigned, no step and protocol keys in protocol_vals.\ngot protocol_vals: {protocol_vals}')
            except Exception as e:
                self.logger.exception(f'exception when assigning protocol, continuing subject creation. \n{e}')
                # the wizard couldn't find the protocol dir, so no task tab was made
                # or no task was assigned

            # Add subject to pilots dict, update it and our tabs
            self.pilots[pilot]['subjects'].append(biography_vals['id'])
            self.subject_lists[pilot].addItem(biography_vals['id'])
            self.update_db()

    # TODO: fix this
    # def edit_params(self, item):
    #     """
    #     Args:
    #         item:
    #     """
    #     # edit a subject's task parameters, called when subject double-clicked
    #     subject = item.text()
    #     if subject not in self.subjects.keys():
    #         self.subjects[subject] = Subject(subject)
    #
    #     if '/current' not in self.subjects[subject].h5f:
    #         Warning("Subject {} has no protocol!".format(subject))
    #         return
    #
    #     protocol = self.subjects[subject].current
    #     step = self.subjects[subject].step
    #
    #     protocol_edit = Protocol_Parameters_Dialogue(protocol, step)
    #     protocol_edit.exec_()
    #
    #     if protocol_edit.result() == 1:
    #         param_changes = protocol_edit.step_changes
    #         # iterate through steps, checking for changes
    #         for i, step_changes in enumerate(param_changes):
    #             # if there are any changes to this step, stash them
    #             if step_changes:
    #                 for k, v in step_changes.items():
    #                     self.subjects[subject].update_history('param', k, v, step=i)
    #
    #

    def update_db(self, pilots:typing.Optional[dict]=None, **kwargs):
        """
        Gathers any changes in :class:`Subject_List` s and dumps :py:attr:`.pilots` to :py:attr:`.prefs.get('PILOT_DB')`

        Args:
            kwargs: Create new pilots by passing a dictionary with the structure

                `new={'pilot_name':'pilot_values'}`

                where `'pilot_values'` can be nothing, a list of subjects,
                or any other information included in the pilot db
        """
        # if we were given a new pilot, add it
        if 'new' in kwargs.keys():
            for pilot, value in kwargs['new'].items():
                self.pilots[pilot] = value

        if pilots is None:
            pilots = self.pilots.copy()

        # gather subjects from lists
        for pilot, mlist in self.subject_lists.items():
            subjects = []
            for i in range(mlist.count()):
                subjects.append(mlist.item(i).text())

            pilots[pilot]['subjects'] = subjects

        # strip any state that's been stored
        for p, val in pilots.items():
            if 'state' in val.keys():
                del val['state']

        with open(prefs.get('PILOT_DB'), 'w') as pilot_file:
            json.dump(self.pilots, pilot_file, indent=4, separators=(',', ': '))

####################################
# Control Panel Widgets
###################################

class Subject_List(QtWidgets.QListWidget):
    """
    A trivial modification of :class:`~.QtWidgets.QListWidget` that updates
    :py:attr:`~.Terminal.pilots` when an item in the list is dragged to another location.

    Should not be initialized except by :class:`.Control_Panel` .

    Attributes:
        subjects (list): A list of subjects ID's passed by :class:`.Control_Panel`
        drop_fn (:py:meth:`.Control_Panel.update_db`): called on a drop event
    """

    def __init__(self, subjects=None, drop_fn=None):
        """
        Args:
            subjects: see :py:attr:`~.Subject_List.subjects`. Can be `None` for an empty list
            drop_fn: see :py:meth:`~.Subject_List.drop_fn`. Passed from :class:`.Control_Panel`
        """
        super(Subject_List, self).__init__()

        # if we are passed a list of subjects, populate
        if subjects:
            self.subjects = subjects
            self.populate_list()
        else:
            self.subjects = []

        # make draggable
        self.setDragDropMode(QtWidgets.QAbstractItemView.InternalMove)
        self.setDragDropOverwriteMode(False)
        self.setAcceptDrops(True)

        # drop_fn gets called on a dropEvent (after calling the superclass method)
        self.drop_fn = drop_fn

    def populate_list(self):
        """
        Adds each item in :py:attr:`Subject_List.subjects` to the list.
        """
        for m in self.subjects:
            self.addItem(m)

    def dropEvent(self, event):
        """
        A trivial redefinition of :py:meth:`.QtWidgets.QListWidget.dropEvent`
        that calls the parent `dropEvent` and then calls :py:attr:`~.Subject_List.drop_fn`

        Args:
            event: A :class:`.QtCore.QEvent` simply forwarded to the superclass.
        """
        # call the parent dropEvent to make sure all the list ops happen
        super(Subject_List, self).dropEvent(event)
        # then we call the drop_fn passed to us
        self.drop_fn()


class Pilot_Panel(QtWidgets.QWidget):
    """
    A little panel with

    * the name of a pilot,
    * A :class:`Pilot_Button` to start and stop the task
    * Add and remove buttons to :py:meth:`~Pilot_Panel.create_subject` and :py:meth:`Pilot_Panel.remove_subject`

    Note:
        This class should not be instantiated except by :class:`Control_Panel`

    Args:
        pilot (str): The name of the pilot this panel controls
        subject_list (:py:class:`.Subject_List`): The :py:class:`.Subject_List` we control
        start_fn (:py:meth:`~autopilot.core.terminal.Terminal.toggle_start`): Passed by :class:`Control_Panel`
        create_fn (:py:meth:`Control_Panel.create_subject`): Passed by :class:`Control_Panel`

    Attributes:
        layout (:py:class:`QtWidgets.QGridLayout`): Layout for UI elements
        button (:class:`.Pilot_Button`): button used to control a pilot
    """
    def __init__(self, pilot=None, subject_list=None, start_fn=None, ping_fn=None, create_fn=None):
        """

        """
        super(Pilot_Panel, self).__init__()

        self.layout = QtWidgets.QGridLayout()
        self.layout.setContentsMargins(0,0,0,0)
        self.layout.setSpacing(0)
        self.setLayout(self.layout)

        self.pilot = pilot
        self.subject_list = subject_list
        self.start_fn = start_fn
        self.ping_fn = ping_fn
        self.create_fn = create_fn
        self.button = None

        self.init_ui()

    def init_ui(self):
        """
        Initializes UI elements - creates widgets and adds to :py:attr:`Pilot_Panel.layout` .
        Called on init.
        """

        label = QtWidgets.QLabel(self.pilot)
        label.setStyleSheet("font: bold 14pt; text-align:right")
        label.setAlignment(QtCore.Qt.AlignVCenter)
        self.button = Pilot_Button(self.pilot, self.subject_list, self.start_fn, self.ping_fn)
        add_button = QtWidgets.QPushButton("+")
        add_button.clicked.connect(self.create_subject)
        add_button.setSizePolicy(QtWidgets.QSizePolicy.Expanding,QtWidgets.QSizePolicy.Expanding)
        remove_button = QtWidgets.QPushButton("-")
        remove_button.clicked.connect(self.remove_subject)
        remove_button.setSizePolicy(QtWidgets.QSizePolicy.Expanding,QtWidgets.QSizePolicy.Expanding)

        self.layout.addWidget(label, 0, 0, 1, 2)
        self.layout.addWidget(self.button, 1, 0, 1, 2)
        self.layout.addWidget(add_button, 2,0,1,1)
        self.layout.addWidget(remove_button, 2,1,1,1)

        self.layout.setRowStretch(0, 3)
        self.layout.setRowStretch(1, 2)
        self.layout.setRowStretch(2, 1)

    def remove_subject(self):
        """
        Remove the currently selected subject in :py:attr:`Pilot_Panel.subject_list`,
        and calls the :py:meth:`Control_Panel.update_db` method.
        """

        current_subject = self.subject_list.currentItem().text()
        msgbox = QtWidgets.QMessageBox()
        msgbox.setText("\n(only removes from pilot_db.json, data will not be deleted)".format(current_subject))

        msgBox = QtWidgets.QMessageBox()
        msgBox.setText("Are you sure you would like to remove {}?".format(current_subject))
        msgBox.setInformativeText("'Yes' only removes from pilot_db.json, data will not be deleted")
        msgBox.setStandardButtons(QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No)
        msgBox.setDefaultButton(QtWidgets.QMessageBox.No)
        ret = msgBox.exec_()

        if ret == QtWidgets.QMessageBox.Yes:

            self.subject_list.takeItem(self.subject_list.currentRow())
            # the drop fn updates the db
            self.subject_list.drop_fn()

    def create_subject(self):
        """
        Just calls :py:meth:`Control_Panel.create_subject` with our `pilot` as the argument
        """
        self.create_fn(self.pilot)


class Pilot_Button(QtWidgets.QPushButton):
    def __init__(self, pilot=None, subject_list=None, start_fn=None, ping_fn=None):
        """
        A subclass of (toggled) :class:`QtWidgets.QPushButton` that incorporates the style logic of a
        start/stop button - ie. color, text.

        Starts grayed out, turns green if contact with a pilot is made.

        Args:
            pilot (str): The ID of the pilot that this button controls
            subject_list (:py:class:`.Subject_List`): The Subject list used to determine which
                subject is starting/stopping
            start_fn (:py:meth:`~autopilot.core.terminal.Terminal.toggle_start`): The final
                resting place of the toggle_start method

        Attributes:
            state (str): The state of our pilot, reflected in our graphical properties.
                Mirrors :attr:`~.pilot.Pilot.state` , with an additional "DISCONNECTED"
                state for before contact is made with the pilot.
        """
        super(Pilot_Button, self).__init__()

        ## GUI Settings
        self.setCheckable(False)
        self.setChecked(False)
        self.setEnabled(True)

        self.normal_stylesheet = (
            "QPushButton {color:white; background-color: green}"
            "QPushButton:checked {color:white; background-color: red}"
            "QPushButton:disabled {color:black; background-color: gray}"
        )

        self.limbo_stylesheet = (
            "QPushButton {color:black; background-color: gray}"
        )

        self.setStyleSheet(self.limbo_stylesheet)
        # at start, set our text to no pilot and wait for the signal
        self.setText("?PING?")

        # keep track of our visual and functional state.
        self.state = "DISCONNECTED"

        # Normally buttons only expand horizontally, but these big ole ones....
        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)

        # What's yr name anyway?
        self.pilot = pilot

        # What subjects do we know about?
        self.subject_list = subject_list



        # Passed a function to toggle start from the control panel
        self.start_fn = start_fn
        self.ping_fn = ping_fn
        # toggle_start has a little sugar on it before sending to control panel
        # use the clicked rather than toggled signal, clicked only triggers on user
        # interaction, toggle is whenever the state is toggled - so programmatically
        # toggling the button - ie. responding to pilot state changes - double triggers.
        self.clicked.connect(self.toggle_start)


    def toggle_start(self):
        """
        Minor window dressing to call the :py:meth:`~.Pilot_Button.start_fn` with the
        appropriate pilot, subject, and whether the task is starting or stopping

        """
        # If we're stopped, start, and vice versa...
        current_subject = self.subject_list.currentItem().text()

        if self.state == "DISCONNECTED":
            # ping our lil bebs
            self.ping_fn()
            return

        if current_subject is None:
            Warning("Start button clicked, but no subject selected.")
            return


        toggled = self.isChecked()
        if toggled is True: # ie button is already down, already running.

            self.setText("STOP")
            self.start_fn(True, self.pilot, current_subject)

        else:
            self.setText("START")
            self.start_fn(False, self.pilot, current_subject)

    @gui_event
    def set_state(self, state):
        """
        Set the button's appearance and state

        Args:
            state (str): one of ``('IDLE', 'RUNNING', 'STOPPING', 'DISCONNECTED')

        .. todo::

            There is some logic duplication in this class, ie. if the button state is changed
            it also emits a start/stop signal to the pi, which is undesirable. This class needs
            to be reworked.

        Returns:

        """
        # if we're good, do nothing.
        if state == self.state:
            return


        if state == "IDLE":
            # responsive and waiting
            self.setCheckable(True)
            self.setEnabled(True)
            self.setText('START')
            self.setChecked(False)
        elif state == "RUNNING":
            # running a task
            self.setCheckable(True)
            self.setEnabled(True)
            self.setText('STOP')
            self.setChecked(True)
        elif state == "STOPPING":
            # stopping
            self.setCheckable(True)
            self.setEnabled(False)
            self.setText("STOPPING")
            self.setChecked(False)
        elif state == "DISCONNECTED":
            # contact w the pi is missing or lost
            self.setCheckable(False)
            self.setEnabled(True)
            self.setText("?PING?")
            self.setChecked(False)

        if state == "DISCONNECTED":
            self.setStyleSheet(self.limbo_stylesheet)
        else:
            if self.isChecked():
                self.setText('STOP')
            else:
                self.setText('START')
            self.setStyleSheet(self.normal_stylesheet)

        self.state = state


##################################
# Wizard Widgets
################################3#

# TODO: Change these classes to use the update params windows

class New_Subject_Wizard(QtWidgets.QDialog):
    """
    A popup that prompts you to define variables for a new :class:`.subject.Subject` object

    Called by :py:meth:`.Control_Panel.create_subject` , which handles actually creating
    the subject file and updating the :py:attr:`.Terminal.pilots` dict and file.

    Contains two tabs
    - :class:`~.New_Subject_Wizard.Biography_Tab` - to set basic biographical information about a subject
    - :class:`~.New_Subject_Wizard.Task_Tab` - to set the protocol and step to start the subject on

    Attributes:
        protocol_dir (str): A full path to where protocols are stored,
            received from :py:const:`.prefs.get('PROTOCOLDIR')`
        bio_tab (:class:`~.New_Subject_Wizard.Biography_Tab`): Sub-object to set and store biographical variables
        task_tab (:class:`~.New_Subject_Wizard.Task_Tab`): Sub-object to set and store protocol and step assignment
    """

    def __init__(self):
        QtWidgets.QDialog.__init__(self)

        self.protocol_dir = prefs.get('PROTOCOLDIR')

        tabWidget = QtWidgets.QTabWidget()

        self.bio_tab = self.Biography_Tab()
        tabWidget.addTab(self.bio_tab, "Biography")

        if self.protocol_dir:
            self.task_tab = self.Task_Tab()
            tabWidget.addTab(self.task_tab, "Protocol")

        buttonBox = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        buttonBox.accepted.connect(self.accept)
        buttonBox.rejected.connect(self.reject)

        mainLayout = QtWidgets.QVBoxLayout()
        mainLayout.addWidget(tabWidget)
        mainLayout.addWidget(buttonBox)
        self.setLayout(mainLayout)

        self.setWindowTitle("Setup New Subject")

    class Biography_Tab(QtWidgets.QWidget):
        """
        A widget that allows defining basic biographical attributes about a subject

        Creates a set of widgets connected to :py:meth:`~.Biography_Tab.update_return_dict` that stores the parameters.

        Warning:
            The below attributes are **not** the object attributes, but are descriptions of the parameters
            available in the values dictionary. The attributes themselves are PySide Widgets that set the values.

        Attributes:
            id (str): A Subject's ID or name
            start_date (str): The date the subject started the task. Automatically filled by
                :py:meth:`datetime.date.today().isoformat()`
            blmass (float): The subject's baseline mass
            minmass_pct (int): The percentage of baseline mass that a water restricted subject is allowed to reach
            minmass (float): The subject's minimum mass, automatically calculated `blmass * (minmass_pct / 100.)`
            genotype (str): A string describing the subject's genotype
            expt (str): A tag to describe what experiment this subject is a part of
        """
        def __init__(self):
            QtWidgets.QWidget.__init__(self)

            # Input Labels
            ID_label = QtWidgets.QLabel("ID:")
            start_label = QtWidgets.QLabel("Start Date:")
            blmass_label = QtWidgets.QLabel("Baseline Mass:")
            minmasspct_label = QtWidgets.QLabel("% of Baseline Mass:")
            minmass_label = QtWidgets.QLabel("Minimum Mass:")
            genotype_label = QtWidgets.QLabel("Genotype:")
            expt_label = QtWidgets.QLabel("Experiment Tag:")

            # Input widgets
            self.id = QtWidgets.QLineEdit()
            self.start_date = QtWidgets.QLineEdit(datetime.date.today().isoformat())
            self.blmass = QtWidgets.QLineEdit()
            self.blmass.setValidator(QtGui.QDoubleValidator(0.0, 30.0, 1, self.blmass))
            self.minmass_pct = QtWidgets.QSpinBox()
            self.minmass_pct.setRange(0,100)
            self.minmass_pct.setSingleStep(5)
            self.minmass_pct.setSuffix('%')
            self.minmass_pct.setValue(80)
            self.minmass = QtWidgets.QLineEdit()
            self.minmass.setValidator(QtGui.QDoubleValidator(0.0, 30.0, 1, self.minmass))
            self.genotype = QtWidgets.QLineEdit()
            self.expt     = QtWidgets.QLineEdit()

            # Set return dictionary signals
            self.id.editingFinished.connect(lambda: self.update_return_dict('id', self.id.text()))
            self.start_date.editingFinished.connect(lambda: self.update_return_dict('start_date', self.start_date.text()))
            self.blmass.editingFinished.connect(lambda: self.update_return_dict('baseline_mass', self.blmass.text()))
            self.minmass.editingFinished.connect(lambda: self.update_return_dict('min_mass', self.minmass.text()))
            self.genotype.editingFinished.connect(lambda: self.update_return_dict('genotype', self.genotype.text()))
            self.expt.editingFinished.connect(lambda: self.update_return_dict('experiment', self.expt.text()))

            # Set update minmass signals
            self.blmass.editingFinished.connect(self.calc_minmass)
            self.minmass_pct.valueChanged.connect(self.calc_minmass)

            # Setup Layout
            mainLayout = QtWidgets.QVBoxLayout()
            mainLayout.addWidget(ID_label)
            mainLayout.addWidget(self.id)
            mainLayout.addWidget(start_label)
            mainLayout.addWidget(self.start_date)
            mainLayout.addWidget(blmass_label)
            mainLayout.addWidget(self.blmass)
            mainLayout.addWidget(minmasspct_label)
            mainLayout.addWidget(self.minmass_pct)
            mainLayout.addWidget(minmass_label)
            mainLayout.addWidget(self.minmass)
            mainLayout.addWidget(genotype_label)
            mainLayout.addWidget(self.genotype)
            mainLayout.addWidget(expt_label)
            mainLayout.addWidget(self.expt)
            mainLayout.addStretch(1)

            self.setLayout(mainLayout)

            # Dictionary to return values
            self.values = {}

        def update_return_dict(self, key, val):
            """
            Called by lambda functions by the widgets, eg.::

                self.id.editingFinished.connect(lambda: self.update_return_dict('id', self.id.text()))

            Args:
                key (str): The key of the value being stored
                val: The value being stored.
            """
            self.values[key] = val
            # When values changed, update return dict

        def calc_minmass(self):
            """
            Calculates the minimum mass for a subject based on its baseline mass
            and the allowable percentage of that baseline
            """
            # minimum mass automatically from % and baseline
            baseline = float(self.blmass.text())
            pct = float(self.minmass_pct.text()[:-1])/100
            self.minmass.setText(str(baseline*pct))

    class Task_Tab(QtWidgets.QWidget):
        """
        A tab for selecting a task and step to assign to the subject.

        Reads available tasks from `prefs.get('PROTOCOLDIR')` , lists them, and
        creates a spinbox to select from the available steps.

        Warning:
            Like :class:`.Biography_Tab` , these are not the actual instance attributes.
            Values are stored in a `values` dictionary.

        Attributes:
            protocol (str): the name of the assigned protocol, filename without .json extension
            step (int): current step to assign.
        """
        def __init__(self):
            QtWidgets.QWidget.__init__(self)

            self.protocol_dir = prefs.get('PROTOCOLDIR')

            topLabel = QtWidgets.QLabel("Protocols:")

            # List available protocols
            protocol_list = os.listdir(self.protocol_dir)
            protocol_list = [os.path.splitext(p)[0] for p in protocol_list]

            self.protocol_listbox = QtWidgets.QListWidget()
            self.protocol_listbox.insertItems(0, protocol_list)
            self.protocol_listbox.currentItemChanged.connect(self.protocol_changed)

            # Make Step combobox
            self.step_selection = QtWidgets.QComboBox()
            self.step_selection.currentIndexChanged.connect(self.step_changed)

            layout = QtWidgets.QVBoxLayout()
            layout.addWidget(topLabel)
            layout.addWidget(self.protocol_listbox)
            layout.addWidget(self.step_selection)

            self.setLayout(layout)

            # Dict to return values
            self.values = {}

        def update_step_box(self):
            """
            Clears any steps that might be in the step selection box,
            loads the protocol file and repopulates it.
            """
            # Clear box
            while self.step_selection.count():
                self.step_selection.removeItem(0)

            # Load the protocol and parse its steps
            protocol_str = self.protocol_listbox.currentItem().text()
            protocol_file = os.path.join(self.protocol_dir,protocol_str + '.json')
            with open(protocol_file) as protocol_file_open:
                protocol = json.load(protocol_file_open)

            step_list = []
            self.step_ind   = {}
            for i, s in enumerate(protocol):
                step_list.append(s['step_name'])
                self.step_ind[s['step_name']] = i

            self.step_selection.insertItems(0, step_list)
            self.step_selection.setCurrentIndex(0)

        def protocol_changed(self):
            """
            When the protocol is changed, save the value and call :py:meth:`.update_step_box`.
            """
            self.values['protocol'] = self.protocol_listbox.currentItem().text()
            self.update_step_box()

        def step_changed(self):
            """
            When the step is changed, save it.
            """
            current_step = self.step_selection.currentText()
            # Check that we have selected a step...
            if current_step != '':
                self.values['step'] = self.step_ind[current_step]


class Protocol_Wizard(QtWidgets.QDialog):
    """
    A dialog window to create a new protocol.

    Warning:
        This is a heavily overloaded class, and will be split into separate objects
        to handle parameters separately. For now this is what we got though and it works.

    Protocols are collections of multiple tasks (steps)
    with some graduation criterion for moving between them.

    This widget is composed of three windows:

    * **left**: possible task types from :func:`autopilot.get_task()`
    * **center**: current steps in task
    * **right**: :class:`.Parameters` for currently selected step.

    The parameters that are used are of the form used by :py:attr:`.Task.PARAMS`
    (see :py:attr:`.Nafc.PARAMS` for an example).

    TODO:
        Make specific parameter class so this definition is less squishy

    its general structure is::

        {'parameter_key': {'tag':'Human Readable Name',
                           'type':'param_type'}}

    while some parameter types have extra items, eg.::

        {'list_param': {'tag':'Select from a List of Parameters',
                        'type': 'list',
                        'values': {'First Option':0, 'Second Option':1}}

    where k:v pairs are still used with lists to allow parameter values (0, 1) be human readable.

    The available types include:

    * **int** - integer
    * **float** - floating point number
    * **bool** - boolean boolbox
    * **list** - a list of `values` to choose from
    * **sounds** - a :class:`.Sound_Widget` that allows sounds to be defined.
    * **graduation** - a :class:`.Graduation_Widget` that allows graduation criteria to be defined

    Attributes:
        task_list (:class:`QtWidgets.QListWidget`): The leftmost window, lists available tasks
        step_list (:class:`QtWidgets.QListWidget`): The center window, lists tasks currently in protocol
        param_layout (:class:`QtWidgets.QFormLayout`): The right window, allows changing available
            parameters for currently selected step.
        steps (list): A list of dictionaries defining the protocol.

    """
    def __init__(self):
        QtWidgets.QDialog.__init__(self)

        # Left Task List/Add Step Box
        addstep_label = QtWidgets.QLabel("Add Step")
        addstep_label.setFixedHeight(40)
        self.task_list = QtWidgets.QListWidget()
        self.task_list.insertItems(0, autopilot.get_names('task'))
        self.add_button = QtWidgets.QPushButton("+")
        self.add_button.setFixedHeight(40)
        self.add_button.clicked.connect(self.add_step)

        addstep_layout = QtWidgets.QVBoxLayout()
        addstep_layout.addWidget(addstep_label)
        addstep_layout.addWidget(self.task_list)
        addstep_layout.addWidget(self.add_button)

        # Center Step List Box
        steplist_label = QtWidgets.QLabel("Step List")
        steplist_label.setFixedHeight(40)
        self.step_list = QtWidgets.QListWidget()
        self.step_list.setDragDropMode(QtWidgets.QAbstractItemView.InternalMove)
        self.step_list.selectionMode = QtWidgets.QAbstractItemView.SingleSelection
        self.step_list.itemSelectionChanged.connect(self.populate_params)
        self.list_model = self.step_list.model()
        self.list_model.rowsMoved.connect(self.reorder_steps)
        self.remove_step_button = QtWidgets.QPushButton('-')
        self.remove_step_button.setFixedHeight(40)
        self.remove_step_button.clicked.connect(self.remove_step)

        steplist_layout = QtWidgets.QVBoxLayout()
        steplist_layout.addWidget(steplist_label)
        steplist_layout.addWidget(self.step_list)
        steplist_layout.addWidget(self.remove_step_button)

        # Right Parameter Definition Window
        param_label = QtWidgets.QLabel("Step Parameters")
        param_label.setFixedHeight(40)
        self.param_layout = QtWidgets.QFormLayout()
        param_frame = QtWidgets.QFrame()
        param_frame.setLayout(self.param_layout)

        param_box_layout = QtWidgets.QVBoxLayout()
        param_box_layout.addWidget(param_label)
        param_box_layout.addWidget(param_frame)

        # Main Layout
        frame_layout = QtWidgets.QHBoxLayout()
        frame_layout.addLayout(addstep_layout, stretch=1)
        frame_layout.addLayout(steplist_layout, stretch=1)
        frame_layout.addLayout(param_box_layout, stretch=3)

        buttonBox = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        buttonBox.accepted.connect(self.accept)
        buttonBox.rejected.connect(self.reject)

        main_layout = QtWidgets.QVBoxLayout()
        main_layout.addLayout(frame_layout)
        main_layout.addWidget(buttonBox)

        self.setLayout(main_layout)
        self.setWindowTitle("Make New Protocol")

        # List to store dicts of steps and params
        self.steps = []

    def add_step(self):
        """
        Loads `PARAMS` from task object, adds base parameters to :py:attr:`.steps` list
        """
        task_type = self.task_list.currentItem().text()
        new_item = QtWidgets.QListWidgetItem()
        new_item.setText(task_type)
        task_params = copy.deepcopy(autopilot.get_task(task_type).PARAMS)

        # Add params that are non-task specific
        # Name of task type
        task_params['task_type'] = {'type':'label','value':task_type}
        # Prepend name of step shittily
        task_params_temp = odict()
        task_params_temp['step_name'] = {'type':'str', 'tag':'Step Name', 'value':task_type}
        task_params_temp.update(task_params)
        task_params.clear()
        task_params.update(task_params_temp)
        # add graduation field
        task_params['graduation'] = {'type':'graduation', 'tag':'Graduation Criterion', 'value':{}}

        self.steps.append(task_params)
        self.step_list.addItem(new_item)
        self.step_list.setCurrentItem(new_item)

    def rename_step(self):
        """
        When the step name widget's text is changed,
        fire this function to update :py:attr:`.step_list` which updates
         :py:attr:`.steps`
        """
        sender = self.sender()
        sender_text = sender.text()
        current_step = self.step_list.item(self.step_list.currentRow())
        current_step.setText(sender_text)

    def remove_step(self):
        """
        Remove step from :py:attr:`.step_list` and :py:attr:`.steps`
        """
        step_index = self.step_list.currentRow()
        del self.steps[step_index]
        self.step_list.takeItem(step_index)

    def populate_params(self):
        """
        Calls :py:meth:`.clear_params` and then creates widgets to edit parameter values.
        Returns:

        """
        self.clear_params()

        # Get current item index
        step_index = self.step_list.currentRow()
        step_dict = self.steps[step_index]

        # Iterate through params to make input widgets
        for k, v in step_dict.items():
            # Make Input Widget depending on type
            # Each Input type needs a different widget type,
            # and each widget type has different methods to get/change values, so we have to do this ugly
            if v['type'] == 'int' or v['type'] == 'str' or v['type'] == 'float':
                rowtag = QtWidgets.QLabel(v['tag'])
                input_widget = QtWidgets.QLineEdit()
                input_widget.setObjectName(k)
                if v['type'] == 'int':
                    input_widget.setValidator(QtGui.QIntValidator())
                elif v['type'] == 'float':
                    input_widget.setValidator(QtGui.QDoubleValidator())
                input_widget.editingFinished.connect(self.set_param)
                if 'value' in v.keys():
                    input_widget.setText(v['value'])
                elif v['type'] == 'str':
                    self.steps[step_index][k]['value'] = ''
                self.param_layout.addRow(rowtag,input_widget)

            elif v['type'] == 'bool':
                rowtag = QtWidgets.QLabel(v['tag'])
                input_widget = QtWidgets.QCheckBox()
                input_widget.setObjectName(k)
                input_widget.stateChanged.connect(self.set_param)
                if 'value' in v.keys():
                    input_widget.setChecked(v['value'])
                else:
                    self.steps[step_index][k]['value'] = False
                self.param_layout.addRow(rowtag, input_widget)

            elif v['type'] == 'list':
                rowtag = QtWidgets.QLabel(v['tag'])
                input_widget = QtWidgets.QListWidget()
                input_widget.setObjectName(k)
                sorted_values = sorted(v['values'], key=v['values'].get)
                input_widget.insertItems(0, sorted_values)
                input_widget.itemSelectionChanged.connect(self.set_param)
                if 'value' in v.keys():
                    select_item = input_widget.item(v['value'])
                    input_widget.setCurrentItem(select_item)
                else:
                    self.steps[step_index][k]['value'] = sorted_values[0]
                self.param_layout.addRow(rowtag, input_widget)
                self.steps[step_index][k]['value'] = False
            elif v['type'] == 'sounds':
                self.sound_widget = Sound_Widget()
                self.sound_widget.setObjectName(k)
                self.sound_widget.pass_set_param_function(self.set_sounds)
                self.param_layout.addRow(self.sound_widget)
                self.steps[step_index][k]['sounds'] = {}
                if 'value' in v.keys():
                    self.sound_widget.populate_lists(v['value'])
            elif v['type'] == 'graduation':
                self.grad_widget = Graduation_Widget()
                self.grad_widget.setObjectName(k)
                self.grad_widget.set_graduation = self.set_graduation
                self.param_layout.addRow(self.grad_widget)
                if 'type' in v['value'].keys():
                    combo_index = self.grad_widget.type_selection.findText(v['value']['type'])
                    self.grad_widget.type_selection.setCurrentIndex(combo_index)
                    self.grad_widget.populate_params(v['value']['value'])

            elif v['type'] == 'label':
                # This is a .json label not for display
                pass

            # Step name needs to be hooked up to the step list text
            if k == 'step_name':
                input_widget.editingFinished.connect(self.rename_step)

        # TODO: Implement dependencies between parameters

    def clear_params(self):
        """
        Clears widgets from parameter window
        """
        while self.param_layout.count():
            child = self.param_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

    def reorder_steps(self, *args):
        """
        When steps are dragged into a different order, update the step dictionary

        Args:
            *args: Input from our :py:attr:`.step_list` 's :class:`.QtWidgets.QListModel` 's reorder signal.
        """
        # arg positions 1 and 4 are starting and ending positions in the list, respectively
        # We reorder our step list so the params line up.
        before = args[1]
        after = args[4]
        self.steps.insert(after, self.steps.pop(before))

    def set_param(self):
        """
        Callback function connected to the signal each widget uses to signal it has changed.

        Identifies the param that was changed, gets the current value, and updates `self.steps`
        """
        sender = self.sender()
        param_name = sender.objectName()
        current_step = self.step_list.currentRow()
        sender_type = self.steps[current_step][param_name]['type']

        if sender_type == 'bool':
            self.steps[current_step][param_name]['value'] = sender.isChecked()
        elif sender_type == 'list':
            list_text = sender.currentItem().text()
            #list_value = self.steps[current_step][param_name]['values'][list_text]
            self.steps[current_step][param_name]['value'] = list_text
        elif sender_type == 'sounds':
            self.steps[current_step][param_name]['value'] = self.sound_widget.sound_dict
        else:
            try:
                sender_text = ast.literal_eval(sender.text())
            except:
                sender_text = sender.text()
            self.steps[current_step][param_name]['value'] = sender_text

    def set_sounds(self):
        """
        Stores parameters that define sounds.

        Sound parameters work a bit differently, specifically we have to retrieve
        :py:attr:`.Sound_Widget.sound_dict`.
        """
        current_step = self.step_list.currentRow()
        #if 'sounds' in self.steps[current_step]['stim'].keys():
        #    self.steps[current_step][param_name]['sounds']['value'].update(self.sound_widget.sound_dict)
        #else:
        self.steps[current_step]['stim']['sounds'] = self.sound_widget.sound_dict

    def set_graduation(self):
        """
        Stores parameters that define graduation criteria in `self.steps`

        Graduation parameters work a bit differently, specifically we have to retrieve
        :py:attr:`.Graduation_Widget.param_dict`.
        """
        current_step = self.step_list.currentRow()
        grad_type = self.grad_widget.type
        grad_params = self.grad_widget.param_dict
        self.steps[current_step]['graduation']['value'] = {'type':grad_type,'value':grad_params}


    def check_depends(self):
        """
        Handle dependencies between parameters, eg. if "correction trials" are unchecked,
        the box that defines the correction trial percentage should be grayed out.

        TODO:
            Not implemented.
        """
        # TODO: Make dependent fields unavailable if dependencies unmet
        # I mean if it really matters
        pass

class Graduation_Widget(QtWidgets.QWidget):
    """
    A widget used in :class:`.Protocol_Wizard` to define graduation parameters.

    See :py:mod:`.tasks.graduation` .

    A protocol is composed of multiple tasks (steps), and graduation criteria
    define when a subject should progress through those steps.

    eg. a subject should graduate one stage after 300 trials, or after it reaches
    75% accuracy over the last 500 trials.

    Attributes:
        type_selection (:class:`QtWidgets.QComboBox`): A box to select from the available
            graduation types listed in :func:`autopilot.get_task()` . Has its `currentIndexChanged`
            signal connected to :py:meth:`.Graduation_Widget.populate_params`
        param_dict (dict): Stores the type of graduation and the relevant params,
            fetched by :class:`.Protocol_Wizard` when defining a protocol.
        set_graduation (:py:meth:`.Protocol_Wizard.set_graduation`): Passed to us after we're inited.
    """

    def __init__(self):
        super(Graduation_Widget, self).__init__()

        # Grad type dropdown
        type_label = QtWidgets.QLabel("Graduation Criterion:")
        self.type_selection = QtWidgets.QComboBox()
        self.type_selection.insertItems(0, autopilot.get_names('graduation'))
        self.type_selection.currentIndexChanged.connect(self.populate_params)

        # Param form
        self.param_layout = QtWidgets.QFormLayout()

        layout = QtWidgets.QVBoxLayout()
        layout.addWidget(type_label)
        layout.addWidget(self.type_selection)
        layout.addLayout(self.param_layout)

        self.setLayout(layout)

        self.param_dict = {}

        self.type = ""

        self.set_graduation = None

        self.populate_params()

    def populate_params(self, params=None):
        """
        Repopulate the widget with fields to edit graduation parameters, fill fields
        if we are passed `params`.

        Each :class:`QtWidgets.QLineEdit` 's :py:meth:`.QLineEdit.editingFinished` signal is connected
        to :py:meth:`.Graduation_Widget.store_param` .

        TODO:
            For now we assume all parameters are defined with a text edit box, so it's not
            clear how we'd do boolean parameters for example. This will be fixed with refactoring
            the parameter scheme.

        Args:
            params (dict): In the case that :class:`.Protocol_Wizard` switches us back to
                a step where we have already defined graduation parameters, it will pass them
                so we can repopulate the relevant widgets with them.
        """
        self.clear_params()
        self.type = self.type_selection.currentText()
        self.param_dict['type'] = self.type

        for k in autopilot.get_task(self.type).PARAMS:
            edit_box = QtWidgets.QLineEdit()
            edit_box.setObjectName(k)
            edit_box.editingFinished.connect(self.store_param)
            if isinstance(params, dict):
                if k in params.keys():
                    edit_box.setText(params[k])
            self.param_layout.addRow(QtWidgets.QLabel(k), edit_box)

    def clear_params(self):
        """
        Clear any parameter widgets we have.
        """
        while self.param_layout.count():
            child = self.param_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

    def store_param(self):
        """
        When a parameter is edited, save it in our param_dict, and also call our
        `set_graduation` method, which should be :py:meth:`.Protocol_Wizard.set_graduation`
        passed to us after instantiation.

        If we were not passed `set_graduation`, just saves in `param_dict`.
        """
        sender = self.sender()
        name = sender.objectName()
        self.param_dict[name] = sender.text()

        if not callable(self.set_graduation):
            Warning("Stored Graduation parameters in our param_dict, but wasn't passed a set_graduation method!")
            return

        self.set_graduation()

class Drag_List(QtWidgets.QListWidget):
    """
    A :class:`QtWidgets.QListWidget` that is capable of having files dragged & dropped.

    copied with much gratitude from `stackoverflow <https://stackoverflow.com/a/25614674>`_

    Primarily used in :class:`.Sound_Widget` to be able to drop sound files.

    To use: connect `fileDropped` to a method, that method will receive a list of files
    dragged onto this widget.

    Attributes:
        fileDropped (:class:`QtCore.Signal`): A Qt signal that takes a list
    """
    fileDropped = QtCore.Signal(list)

    def __init__(self):
        # type: () -> None
        super(Drag_List, self).__init__()
        self.setAcceptDrops(True)

    def dragEnterEvent(self, e):
        """
        When files are dragged over us, if they have paths in them,
        accept the event.

        Args:
            e (:class:`QtCore.QEvent`): containing the drag information.
        """
        if e.mimeData().hasUrls:
            e.accept()
        else:
            e.ignore()

    def dragMoveEvent(self, event):
        """
        If the `dragEnterEvent` was accepted, while the drag is being moved within us,
        `setDropAction` to :class:`.QtCore.Qt.CopyAction`

        Args:
            event (:class:`QtCore.QEvent`): containing the drag information.
        """
        if event.mimeData().hasUrls:
            event.setDropAction(QtCore.Qt.CopyAction)
            event.accept()
        else:
            event.ignore()

    def dropEvent(self, event):
        """
        When the files are finally dropped, if they contain paths,
        emit the list of paths through the `fileDropped` signal.

        Args:
            event (:class:`QtCore.QEvent`): containing the drag information.
        """
        if event.mimeData().hasUrls:
            event.setDropAction(QtCore.Qt.CopyAction)
            event.accept()
            links = []
            for url in event.mimeData().urls():
                links.append(str(url.toLocalFile()))
            self.fileDropped.emit(links)
        else:
            event.ignore()


class Sound_Widget(QtWidgets.QWidget):
    """
    A widget that allows sounds to be parameterized.

    Used in :class:`.Protocol_Wizard` .

    Has two :class:`.Drag_List` s for left and right sounds (for a 2afc task), given
    Buttons beneath them allow adding and removing sounds.

    Adding a sound will open a :class:`.Add_SoundDialog`

    TODO:
        Sounds will eventually be more elegantly managed by a ... sound manager..
        For now sound managers are rudimentary and only support random presentation
        with correction trials and bias correction.

    Attributes:
        sound_dict (dict): Dictionary with the structure::

                {'L': [{'param_1':'param_1', ... }], 'R': [...]}

            where multiple sounds can be present in either 'L' or 'R' list.



    """
    def __init__(self):
        # type: () -> None
        QtWidgets.QWidget.__init__(self)

        self.sounddir = prefs.get('SOUNDDIR')

        self.set_sounds = None

        # Left sounds
        left_label = QtWidgets.QLabel("Left Sounds")
        left_label.setFixedHeight(30)
        self.left_list = Drag_List()
        self.left_list.fileDropped.connect(self.files_dropped)
        self.left_list.setObjectName("L")
        self.add_left_button = QtWidgets.QPushButton("+")
        self.add_left_button.setFixedHeight(30)
        self.add_left_button.clicked.connect(lambda: self.add_sound('L'))
        self.remove_left_button = QtWidgets.QPushButton("-")
        self.remove_left_button.setFixedHeight(30)
        self.remove_left_button.clicked.connect(lambda: self.remove_sound('L'))

        left_layout = QtWidgets.QVBoxLayout()
        left_button_layout = QtWidgets.QHBoxLayout()
        left_button_layout.addWidget(self.add_left_button)
        left_button_layout.addWidget(self.remove_left_button)
        left_layout.addWidget(left_label)
        left_layout.addWidget(self.left_list)
        left_layout.addLayout(left_button_layout)

        # Right sounds
        right_label = QtWidgets.QLabel("Right Sounds")
        right_label.setFixedHeight(30)
        self.right_list = Drag_List()
        self.right_list.fileDropped.connect(self.files_dropped)
        self.right_list.setObjectName("R")
        self.add_right_button = QtWidgets.QPushButton("+")
        self.add_right_button.setFixedHeight(30)
        self.add_right_button.clicked.connect(lambda: self.add_sound('R'))
        self.remove_right_button = QtWidgets.QPushButton("-")
        self.remove_right_button.setFixedHeight(30)
        self.remove_right_button.clicked.connect(lambda: self.remove_sound('R'))

        right_layout = QtWidgets.QVBoxLayout()
        right_button_layout = QtWidgets.QHBoxLayout()
        right_button_layout.addWidget(self.add_right_button)
        right_button_layout.addWidget(self.remove_right_button)
        right_layout.addWidget(right_label)
        right_layout.addWidget(self.right_list)
        right_layout.addLayout(right_button_layout)

        self.sound_dict = {'L': [], 'R': []}

        main_layout = QtWidgets.QHBoxLayout()
        main_layout.addLayout(left_layout)
        main_layout.addLayout(right_layout)
        self.setLayout(main_layout)

        # TODO:Add drag and drop for files

    def pass_set_param_function(self, set_param_fnxn):
        """
        Receives :py:meth:`.Protocol_Wizard.set_sounds`

        Args:
            set_param_fnxn (:py:meth:`.Protocol_Wizard.set_sounds`): Called when sounds are changed.
        """
        self.set_sounds = set_param_fnxn

    def add_sound(self, side):
        """
        When the "+" button on either side is pressed, open an :class:`.Add_Sound_Dialog`.

        Args:
            side (str): The buttons are connected with a lambda function, this will be either 'L' or 'R'.
                Used to add sounds to the `sound_dict`
        """
        new_sound = self.Add_Sound_Dialog()
        new_sound.exec_()

        if new_sound.result() == 1:
            self.sound_dict[side].append(new_sound.param_dict)
            if side == 'L':
                self.left_list.addItem(new_sound.param_dict['type'])
            elif side == 'R':
                self.right_list.addItem(new_sound.param_dict['type'])
            self.set_sounds()

    def remove_sound(self, side):
        """
        When the "-" button is pressed, remove the currently highlighted sound.

        Args:
            side (str): The buttons are connected with a lambda function, this will be either 'L' or 'R'.
                Selects that list so we can remove the currently selected row.
        """
        if side == 'L':
            current_sound = self.left_list.currentRow()
            del self.sound_dict['L'][current_sound]
            self.left_list.takeItem(current_sound)
        elif side == 'R':
            current_sound = self.right_list.currentRow()
            del self.sound_dict['R'][current_sound]
            self.right_list.takeItem(current_sound)
        self.set_sounds()

    def populate_lists(self, sound_dict):
        """
        Populates the sound lists after re-selecting a step.

        Args:
            sound_dict (dict): passed to us by :class:`.Protocol_Wizard` upon reselecting a step.
        """
        # Populate the sound lists after re-selecting a step
        self.sound_dict = sound_dict
        for k in self.sound_dict['L']:
            self.left_list.addItem(k['type'])
        for k in self.sound_dict['R']:
            self.right_list.addItem(k['type'])

    def files_dropped(self, files):
        """
        Warning:
            This was programmed hastily and is pretty idiosyncratic to my use.

            It does work for general files but has some extra logic built in to handle my stimuli.

            To be made more general in v0.3

        Note:
            Sounds must be in the folder specified in `prefs.get('SOUNDDIR')`.

        When files are dropped on the lists, strips `prefs.get('SOUNDDIR')` from them to make them
        relative paths, adds them to the `sound_dict`

        Args:
            files (list): List of absolute paths.
        """
        # TODO: Make this more general...
        msg = QtWidgets.QMessageBox()
        msg.setText("Are these Speech sounds in the format '/speaker/cv/cv_#.wav'?")
        msg.setStandardButtons(QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No)
        ret = msg.exec_()

        sender = self.sender()
        side = sender.objectName()

        if ret == QtWidgets.QMessageBox.No:
            for f in files:
                f = f.strip(self.sounddir)

                self.sound_dict[side].append({'type':'File', 'path':f})
                if side == 'L':
                    self.left_list.addItem(f)
                elif side == 'R':
                    self.right_list.addItem(f)


        elif ret == QtWidgets.QMessageBox.Yes:
            for f in files:
                f = f.strip(self.sounddir)
                f_split = f.split(os.sep)
                speaker = f_split[0]
                cv = f_split[-1].split('.')[0].split('_')[0]
                consonant = cv[0]
                vowel = cv[1:]
                token = f_split[-1].split('.')[0].split('_')[1]
                param_dict = {'type':'Speech','path':f,
                 'speaker':speaker,'consonant':consonant,
                 'vowel':vowel,'token':token}
                self.sound_dict[side].append(param_dict)
                if side == 'L':
                    self.left_list.addItem(f)
                elif side == 'R':
                    self.right_list.addItem(f)

        self.set_sounds()

    class Add_Sound_Dialog(QtWidgets.QDialog):
        """
        Presents a dialog to define a new sound.

        Makes a selection box to choose the sound type from
        ``autopilot.get_names('sound')``, and then populates edit boxes
        so we can fill in its `PARAMS` .

        Attributes:
            type_selection (:class:`QtWidgets.QComboBox`): Select from a list of available sounds
            param_dict (dict): Parameters that are retreived by the calling :class:`.Sound_Widget`.

        """
        def __init__(self):
            # type: () -> None
            QtWidgets.QDialog.__init__(self)

            # Sound type dropdown
            type_label = QtWidgets.QLabel("Sound Type:")
            self.type_selection = QtWidgets.QComboBox()
            self.type_selection.insertItems(0, autopilot.get_names('sound'))
            self.type_selection.currentIndexChanged.connect(self.populate_params)

            # Param form
            self.param_layout = QtWidgets.QFormLayout()

            # Button box
            buttonBox = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
            buttonBox.accepted.connect(self.accept)
            buttonBox.rejected.connect(self.reject)

            # Layout
            layout = QtWidgets.QVBoxLayout()
            layout.addWidget(type_label)
            layout.addWidget(self.type_selection)
            layout.addLayout(self.param_layout)
            layout.addWidget(buttonBox)

            self.setLayout(layout)


            # dict for storing params
            self.param_dict = {}

            # do initial population
            self.populate_params()

        def populate_params(self):
            """
            When a sound type is selected, make a :class:`.QtWidgets.QLineEdit` for each
            `PARAM` in its definition.
            """
            self.clear_params()

            self.type = self.type_selection.currentText()
            self.param_dict['type'] = self.type

            for k in autopilot.get('sound', self.type).PARAMS:
                edit_box = QtWidgets.QLineEdit()
                edit_box.setObjectName(k)
                edit_box.editingFinished.connect(self.store_param)
                self.param_layout.addRow(QtWidgets.QLabel(k), edit_box)

        def clear_params(self):
            """
            Clear all current widgets
            """
            while self.param_layout.count():
                child = self.param_layout.takeAt(0)
                if child.widget():
                    child.widget().deleteLater()

        def store_param(self):
            """
            When one of our edit boxes is edited, stash the parameter in `param_dict`
            """
            sender = self.sender()
            name = sender.objectName()
            self.param_dict[name] = sender.text()

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
            protocol_box.addItem(text='')

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