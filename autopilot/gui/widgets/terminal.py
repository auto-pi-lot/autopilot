import json
import typing

from PySide6 import QtWidgets, QtCore

from autopilot import prefs
from autopilot.gui import styles
from autopilot.gui.gui import gui_event
from autopilot.gui.widgets.subject import New_Subject_Wizard
from autopilot.utils.loggers import init_logger
from autopilot.data.subject import Subject


class Control_Panel(QtWidgets.QWidget):
    """A :class:`QtWidgets.QWidget` that contains the controls for all pilots.

    Args:
        subjects (dict): See :py:attr:`.Control_Panel.subjects`
        start_fn (:py:meth:`~autopilot.agents.terminal.Terminal.toggle_start`): the Terminal's
            toggle_start function, propagated down to each :class:`~.Pilot_Button`
        pilots: Usually the Terminal's :py:attr:`~.Terminal.pilots` dict. If not passed,
            will try to load :py:attr:`.params.PILOT_DB`

    Attributes:
        subjects (dict): A dictionary with subject ID's as keys and
                :class:`data.subject.Subject` objects as values. Shared with the
                Terminal object to manage access conflicts.
        start_fn (:py:meth:`~autopilot.agents.terminal.Terminal.toggle_start`): See :py:attr:`.Control_Panel.start_fn`
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

            biography = new_subject_wizard.bio_tab.value()

            self.logger.debug(f'subject wizard exited with 1, got biography {biography}')

            new_subject = Subject.new(biography)
            self.subjects[biography.id] = new_subject

            # assign protocol if one was assigned
            try:
                protocol_vals = new_subject_wizard.task_tab.values
                new_subject.assign_protocol(
                    protocol=protocol_vals['protocol'],
                    step_n = int(protocol_vals['step']),
                    pilot=pilot
                )
                self.logger.debug(f"Successfully assigned protocol with status:\n{new_subject.protocol}")
            except Exception as e:
                self.logger.exception(f'exception when assigning protocol, continuing subject creation. \n{e}')

            # Add subject to pilots dict, update it and our tabs
            self.pilots[pilot]['subjects'].append(biography.id)
            self.subject_lists[pilot].addItem(biography.id)
            self.update_db()

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
        start_fn (:py:meth:`~autopilot.agents.terminal.Terminal.toggle_start`): Passed by :class:`Control_Panel`
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
            start_fn (:py:meth:`~autopilot.agents.terminal.Terminal.toggle_start`): The final
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

        self.logger = init_logger(self)


    def toggle_start(self):
        """
        Minor window dressing to call the :py:meth:`~.Pilot_Button.start_fn` with the
        appropriate pilot, subject, and whether the task is starting or stopping

        """
        # If we're stopped, start, and vice versa...

        if self.state == "DISCONNECTED":
            # ping our lil bebs
            self.ping_fn(self.pilot)
            return

        try:
            current_subject = self.subject_list.currentItem().text()
        except AttributeError:
            self.logger.warning('Start button clicked, but no subject selected')
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