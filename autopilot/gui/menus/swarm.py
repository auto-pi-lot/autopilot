import multiprocessing as mp
import threading
import time
import typing

from PySide6 import QtWidgets, QtGui

from autopilot import prefs
from autopilot.gui.dialog import pop_dialog
from autopilot.utils.loggers import init_logger
from autopilot.gui.plots.video import Video
from autopilot.networking import Net_Node


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