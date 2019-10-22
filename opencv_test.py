import cv2
from threading import Thread, Event
from subprocess import Popen, PIPE
import sys
import time
from itertools import count
import os
from skvideo import io
from tqdm import tqdm, trange
from datetime import datetime

# import the Queue class from Python 3
if sys.version_info >= (3, 0):
    from queue import Queue

# otherwise, import the Queue class for Python 2.7
else:
    from Queue import Queue

class Camera(object):
    """
    https://www.pyimagesearch.com/2017/02/06/faster-video-file-fps-with-cv2-videocapture-and-opencv/
    """

    def __init__(self, camera_idx = 0, queue_size = 128):
        self._v4l_info = None

        self.stream = cv2.VideoCapture(camera_idx)

        self.stopped = Event()
        self.stopped.clear()
    #
    #     self.q = Queue(maxsize=queue_size)
    #
    def start(self):
        t = Thread(target=self._update)
        t.daemon = True
        t.start()

    def _update(self):
        while not self.stopped.is_set():
            self._frame = self.stream.read()





    #
    # def update(self):
    #     # keep looping infinitely
    #     while True:
    #         # if the thread indicator variable is set, stop the
    #         # thread
    #         if self.stopped:
    #             return
    #
    #         # otherwise, ensure the queue has room in it
    #         if not self.q.full():
    #             # read the next frame from the file
    #             (grabbed, frame) = self.stream.read()
    #
    #             # if the `grabbed` boolean is `False`, then we have
    #             # reached the end of the video file
    #             if not grabbed:
    #                 self.stop()
    #                 return
    #
    #             # add the frame to the queue
    #             self.q.put(frame)
    #
    # @property
    # def frame(self):
    #     return self.q.get()
    #
    # @property
    # def more(self):
    #     return self.q.qsize() > 0
    #
    # def stop(self):
    #     self.stopped = True

    @property
    def frame(self):
        #_, frame = self.stream.read()
        return self._frame

    @property
    def v4l_info(self):
        # TODO: get camera by other properties than index
        if not self._v4l_info:
            # query v4l device info
            cmd = ["/usr/bin/v4l2-ctl", '-D']
            out, err = Popen(cmd, stdout=PIPE, stderr=PIPE).communicate()
            out, err = out.strip(), err.strip()

            # split by \n to get lines, then group by \t
            out = out.split('\n')
            out_dict = {}
            vals = {}
            key = ''
            n_indents = 0
            for l in out:

                # if we're a sublist, but not a subsublist, split and strip, make a subdictionary
                if l.startswith('\t') and not l.startswith('\t\t'):
                    this_list = [k.strip() for k in l.strip('\t').split(':')]
                    subkey, subval = this_list[0], this_list[1]
                    vals[subkey] = subval

                # but if we're a subsublist... shouldn't have a dictionary
                elif l.startswith('\t\t'):
                    if not isinstance(vals[subkey], list):
                        # catch the previously assined value from the top level of the subdictionary
                        vals[subkey] = [vals[subkey]]

                    vals[subkey].append(l.strip('\t'))

                else:
                    # otherwise if we're at the bottom level, stash the key and any value dictioanry we've gathered before
                    key = l.strip(':')
                    if vals:
                        out_dict[key] = vals
                        vals = {}

            # get the last one
            out_dict[key] = vals

            self._v4l_info = out_dict

        return self._v4l_info


if __name__ == "__main__":
    n_frames = 500

    out_vid_fn = os.path.join(os.path.expanduser('~'),
                              "opencv_{}.mp4".format(datetime.now().strftime("%y%m%d-%H%M%S")))
    #
    # vid_out = io.FFmpegWriter(out_vid_fn,
    #                           outputdict={
    #                               '-vcodec': 'libx264',
    #                               '-pix_fmt': 'yuv420p',
    #                               '-preset': 'fast'
    #                           }
    #                           )
    print('output initialized')

    start_time = time.time()
    #frame_count = count()

    cam = Camera()
    #cam.start()

    for i in trange(n_frames):
        newframe = cam.frame
        # vid_out.writeFrame(cam.frame)

    end_time = time.time()

    #cam.stop()
    #vid_out.close()

    print('Total Frames : {}\nElapsed Time (s): {}\nFPS: {}'.format(n_frames, end_time-start_time, (float(n_frames)/(end_time-start_time))))


