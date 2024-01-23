from collections import deque
from threading import Event, Thread
from time import time, sleep

import numpy as np
import pyqtgraph as pg
from PySide6 import QtWidgets, QtCore

from autopilot import prefs


class Video(QtWidgets.QWidget):
    def __init__(self, videos, fps=None):
        """
        Display Video data as it is collected.

        Uses the :class:`ImageItem_TimedUpdate` class to do timed frame updates.

        Args:
            videos (list, tuple): Names of video streams that will be displayed
            fps (int): if None, draw according to ``prefs.get('DRAWFPS')``. Otherwise frequency of widget update

        Attributes:
            videos (list, tuple): Names of video streams that will be displayed
            fps (int): if None, draw according to ``prefs.get('DRAWFPS')``. Otherwise frequency of widget update
            ifps (int): 1/fps, duration of frame in s
            qs (dict): Dictionary of :class:`~queue.Queue`s in which frames will be dumped
            quitting (:class:`threading.Event`): Signal to quit drawing
            update_thread (:class:`threading.Thread`): Thread with target=:meth:`~.Video._update_frame`
            layout (:class:`PySide6.QtWidgets.QGridLayout`): Widget layout
            vid_widgets (dict): dict containing widgets for each of the individual video streams.
        """
        super(Video, self).__init__()

        self.videos = videos

        if fps is None:
            if prefs.get( 'DRAWFPS'):
                self.fps = prefs.get('DRAWFPS')
            else:
                self.fps = 10
        else:
            self.fps = fps

        self.ifps = 1.0/self.fps

        self.layout = None
        self.vid_widgets = {}


        #self.q = Queue(maxsize=1)
        self.qs = {}
        self.quitting = Event()
        self.quitting.clear()


        self.init_gui()

        self.update_thread = Thread(target=self._update_frame)
        self.update_thread.setDaemon(True)
        self.update_thread.start()

    def init_gui(self):
        self.layout = QtWidgets.QGridLayout()
        self.vid_widgets = {}


        for i, vid in enumerate(self.videos):
            vid_label = QtWidgets.QLabel(vid)

            # https://github.com/pyqtgraph/pyqtgraph/blob/3d3d0a24590a59097b6906d34b7a43d54305368d/examples/VideoSpeedTest.py#L51
            graphicsView= pg.GraphicsView(self)
            vb = pg.ViewBox()
            graphicsView.setCentralItem(vb)
            vb.setAspectLocked()
            #img = pg.ImageItem()
            img = ImageItem_TimedUpdate()
            vb.addItem(img)

            self.vid_widgets[vid] = (graphicsView, vb, img)

            # 3 videos in a row
            row = np.floor(i/3.)*2
            col = i%3

            self.layout.addWidget(vid_label, row,col, 1,1)
            self.layout.addWidget(self.vid_widgets[vid][0],row+1,col,5,1)

            # make queue for vid
            self.qs[vid] = deque(maxlen=1)



        self.setLayout(self.layout)
        self.resize(600,700)
        self.show()

    def _update_frame(self):
        """
        Pulls frames from :attr:`.Video.qs` and feeds them to the video widgets.

        Internal method, run in thread.
        """
        last_time = 0
        this_time = 0
        while not self.quitting.is_set():

            for vid, q in self.qs.items():
                data = None
                try:
                    data = q.popleft()
                    self.vid_widgets[vid][2].setImage(data)

                except IndexError:
                    pass
                except KeyError:
                    pass

            this_time = time()
            sleep(max(self.ifps-(this_time-last_time), 0))
            last_time = this_time





    def update_frame(self, video, data):
        """
        Put a frame for a video stream into its queue.

        If there is a waiting frame, pull it from the queue first -- it's old now.

        Args:
            video (str): name of video stream
            data (:class:`numpy.ndarray`): video frame
        """
        #pdb.set_trace()
        # cur_time = time()

        try:
            # put the new frame in there.
            self.qs[video].append(data)
        except KeyError:
            return

    def release(self):
        self.quitting.set()


VIDEO_TIMER = None


class ImageItem_TimedUpdate(pg.ImageItem):
    """
    Reclass of :class:`pyqtgraph.ImageItem` to update with a fixed fps.

    Rather than calling :meth:`~pyqtgraph.ImageItem.update` every time a frame is updated,
    call it according to the timer.

    fps is set according to ``prefs.get('DRAWFPS')``, if not available, draw at 10fps

    Attributes:
        timer (:class:`~PySide6.QtCore.QTimer`): Timer held in ``globals()`` that synchronizes frame updates across
            image items


    """

    def __init__(self, *args, **kwargs):
        super(ImageItem_TimedUpdate, self).__init__(*args, **kwargs)

        if globals()['VIDEO_TIMER'] is None:
            globals()['VIDEO_TIMER'] = QtCore.QTimer()


        self.timer = globals()['VIDEO_TIMER']
        self.timer.stop()
        self.timer.timeout.connect(self.update_img)
        if prefs.get( 'DRAWFPS'):
            self.fps = prefs.get('DRAWFPS')
        else:
            self.fps = 10.
        self.timer.start(1./self.fps)




    def setImage(self, image=None, autoLevels=None, **kargs):
        #profile = debug.Profiler()

        gotNewData = False
        if image is None:
            if self.image is None:
                return
        else:
            gotNewData = True
            shapeChanged = (self.image is None or image.shape != self.image.shape)
            image = image.view(np.ndarray)
            if self.image is None or image.dtype != self.image.dtype:
                self._effectiveLut = None
            self.image = image
            if self.image.shape[0] > 2 ** 15 - 1 or self.image.shape[1] > 2 ** 15 - 1:
                if 'autoDownsample' not in kargs:
                    kargs['autoDownsample'] = True
            if shapeChanged:
                self.prepareGeometryChange()
                self.informViewBoundsChanged()

        #profile()

        if autoLevels is None:
            if 'levels' in kargs:
                autoLevels = False
            else:
                autoLevels = True
        if autoLevels:
            img = self.image
            while img.size > 2 ** 16:
                img = img[::2, ::2]
            mn, mx = np.nanmin(img), np.nanmax(img)
            # mn and mx can still be NaN if the data is all-NaN
            if mn == mx or np.isnan(mn) or np.isnan(mx):
                mn = 0
                mx = 255
            kargs['levels'] = [mn, mx]


        self.setOpts(update=False, **kargs)

        self.qimage = None

        if gotNewData:
            self.sigImageChanged.emit()

    def update_img(self):
        """
        Call :meth:`~ImageItem_TimedUpdate.update`
        """
        self.update()

    def __del__(self):
        super(ImageItem_TimedUpdate,self).__del__()
        self.timer.stop()



#
# class VideoCV(mp.Process):
#     def __init__(self, videos, fps=30, parent=None):
#         super(VideoCV, self).__init__()
#         self.videos = videos
#
#         self.last_update = 0
#         self.fps = fps
#         self.ifps = 1.0/fps
#
#
#         #self.q = Queue(maxsize=1)
#         self.qs = {}
#         for vid in self.videos:
#             self.qs[vid] = mp.Queue(maxsize=1)
#
#         self.positions = {}
#         n_rows = 0
#         n_cols = 0
#         for i, vid in enumerate(sorted(self.videos)):
#             # 3 videos to a row
#             row = np.floor(i/3.)*2
#             col = i%3
#             if row>n_rows:
#                 n_rows = row
#             if col>n_cols:
#                 n_cols = col
#             self.positions[vid] = (row, col)
#
#         self.n_rows = n_rows+1
#         self.n_cols = n_cols+1
#
#
#
#         # computed as we receive images
#         self.sizes = {}
#         self.resize_factors = {}
#
#         self.quitting = mp.Event()
#         self.quitting.clear()
#
#     def run(self):
#
#         win = cv2.namedWindow('vid', cv2.WINDOW_NORMAL)
#         max_width = 0
#         max_height = 0
#
#         img_array = None
#         while not self.quitting.is_set():
#             pdb.set_trace()
#             for vid, q in self.qs.items():
#                 try:
#                     data = q.get_nowait()
#                 except Empty:
#                     continue
#
#                 if vid not in self.sizes.keys():
#                     self.sizes[vid] = (data.shape[0], data.shape[1])
#                     max_width, max_height = self.calc_resize()
#                     img_array = np.zeros((max_height*self.n_rows, max_width*self.n_cols))
#
#                 data = cv2.resize(data, self.resize_factors[vid])
#                 top = self.positions[vid][0] * max_height
#                 left = self.positions[vid][1] * max_width
#                 img_array[top:top+data.shape[0], left:left+data.shape[1]] = data
#
#             cv2.imshow('vid', img_array)
#             cv2.waitKey(0)
#
#
#
#     def calc_resize(self):
#         max_width = 0
#         max_height = 0
#         for vid, size in self.sizes:
#             if size[1]>max_width:
#                 # set both so we don't split
#                 max_width = size[1]
#                 max_height = size[0]
#             elif size[0]>max_height:
#                 max_width = size[1]
#                 max_height=size[0]
#
#         for vid, size in self.sizes:
#             self.resize_factors[vid] = (float(max_width)/size[0], float(max_height)/size[1])
#
#         return max_width, max_height
#
#
#     def update_frame(self, video, data):
#         #pdb.set_trace()
#         # cur_time = time()
#
#         try:
#             # if there's a waiting frame, it's old now so pull it.
#             _ = self.qs[video].get_nowait()
#         except Empty:
#             pass
#
#         try:
#             # put the new frame in there.
#             self.qs[video].put_nowait(data)
#         except Full:
#             return
#         except KeyError:
#             return
#         # if (cur_time-self.last_update)>self.ifps:
#         #     try:
#         #         self.vid_widgets[video].setImage(data)
#         #         #self.vid_widgets[video].update()
#         #     except KeyError:
#         #         return
#         #     self.last_update = cur_time
#             #self.update()
#             #self.app.processEvents()
#
#     def close(self):
#         self.quitting.set()
