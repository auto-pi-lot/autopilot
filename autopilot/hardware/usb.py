"""
Hardware that uses USB
"""
import sys
import threading
import time

from queue import Queue, Empty

import numpy as np
from inputs import devices

from autopilot import prefs
from autopilot.networking import Net_Node
from autopilot.hardware import Hardware


class Wheel(Hardware):
    """
    A continuously measured mouse wheel.

    Uses a USB computer mouse.

    Warning:
        'vel' thresh_type not implemented
    """

    input   = True
    type    = "Wheel"
    trigger = False # even though this is a triggerable option, typically don't want to assign a cb and instead us a GPIO
    # TODO: Make the standard-style trigger.
    # TODO: Make wheel movements available locally with a deque

    THRESH_TYPES = ['dist', 'x', 'y', 'vel']

    MODES = ('vel_total', 'steady', 'dist', 'timed')

    MOVE_DTYPE = [('vel', 'i4'), ('dir', 'U5'), ('timestamp', 'f8')]

    def __init__(self, mouse_idx=0, fs=10, thresh=100, thresh_type='dist', start=True,
                 digi_out = False, mode='vel_total', integrate_dur=5):
        """
        Args:
            mouse_idx (int):
            fs (int):
            thresh (int):
            thresh_type ('dist'):
            start (bool):
            digi_out (:class:`~.Digital_Out`, bool):
            mode ('vel_total'):
            integrate_dur (int):
        """

        # try to get mouse from inputs
        # TODO: More robust - specify mouse by hardware attrs
        try:
            self.mouse = devices.mice[mouse_idx]
        except IndexError:
            Warning('Could not find requested mouse with index {}\nAttempting to use mouse idx 0'.format(mouse_idx))
            self.mouse = devices.mice[0]

        # frequency of our updating
        self.fs = fs
        # time between updates
        self.update_dur = 1./float(self.fs)

        self.thresh = thresh
        # thresh type can be 'dist', 'x', 'y', or 'vel'
        if thresh_type not in self.THRESH_TYPES:
            ValueError('thresh_type must be one of {}, given {}'.format(self.THRESH_TYPES, thresh_type))
        self.thresh_type = thresh_type

        # mode can be 'vel_total', 'vel_x', 'vel_y' or 'dist' - report either velocity or distance
        # mode can also be '
        # TODO: Do two parameters - type 'vel' or 'dist' and measure 'x', 'y', 'total'z
        self.mode = mode
        # TODO: Implement this

        if self.mode == "steady":
            self.thresh_val = np.array([(0, "REL_Y", 0)], dtype=self.MOVE_DTYPE)
        else:
            self.thresh_val = 0.0

        self.integrate_dur = integrate_dur


        # event to signal quitting
        self.quit_evt = threading.Event()
        self.quit_evt.clear()
        # event to signal when to start accumulating movements to trigger
        self.measure_evt = threading.Event()
        self.measure_time = 0
        # queue to I/O mouse movements summarized at fs Hz
        self.q = Queue()
        # lock to prevent race between putting and getting
        self.qlock = threading.Lock()

        self.listens = {'MEASURE':self.l_measure,
                        'CLEAR':self.l_clear,
                        'STOP':self.l_stop}
        self.node = Net_Node('wheel_{}'.format(mouse_idx),
                             upstream=prefs.get('NAME'),
                             port=prefs.get('MSGPORT'),
                             listens=self.listens,
                             )

        # if we are being used in a child object, we send our trigger via a GPIO pin
        self.digi_out = digi_out



        self.thread = None

        if start:
            self.start()


    def start(self):
        self.thread = threading.Thread(target=self._record)
        self.thread.daemon = True
        self.thread.start()

    def _mouse(self):
        while self.quit_evt:
            events = self.mouse.read()
            self.q.put(events)

    def _record(self):
        moves = np.array([], dtype=self.MOVE_DTYPE)

        threading.Thread(target=self._mouse).start()

        last_update = time.time()

        while not self.quit_evt.is_set():

            try:
                events = self.q.get_nowait()
            except Empty:
                events = None

            if events is None:
                move = np.array([(0, "REL_Y", 0)], dtype=self.MOVE_DTYPE)
            else:
                # make a numpy record array of events with 3 fields:
                # velocity, dir(ection), timestamp (system seconds)
                move = np.array([(int(event.state), event.code, float(event.timestamp))\
                                 for event in events if event.code in ('REL_X', 'REL_Y')],
                                dtype=self.MOVE_DTYPE)
            moves = np.concatenate([moves, move])

            # If we have been told to start measuring for a trigger...
            if self.measure_evt.is_set():
                do_trigger = self.check_thresh(move)
                if do_trigger:
                    self.thresh_trig()
                    self.measure_evt.clear()
                # take the integral of velocities



            # If it's time to report velocity, do it.
            nowtime = time.time()
            if (nowtime-last_update)>self.update_dur:

                # TODO: Implement distance/position reporting
                y_vel = self.calc_move(moves, 'y')
                x_vel = self.calc_move(moves, 'x')

                self.node.send(key='CONTINUOUS', value={'x':x_vel, 'y':y_vel, 't':nowtime},
                               repeat=False)

                moves = np.array([], dtype=self.MOVE_DTYPE)

                last_update = nowtime

    def check_thresh(self, move):
        """
        Updates thresh_val and checks whether it's above/below threshold

        Args:
            move (np.array): Structured array with fields ('vel', 'dir', 'timestamp')

        Returns:

        """

        # Determine whether the threshold was surpassed
        do_trigger = False
        if self.mode == 'vel_total':
            thresh_update = self.calc_move(move)
            # If instantaneous velocity is above thresh...
            if thresh_update > self.thresh:
                do_trigger = True

        elif self.mode == 'steady':
            # If movements in the recent past are below a certain value
            # self.thresh_val should be set to a structured array by l_measure
            try:
                self.thresh_val = np.concatenate([self.thresh_val, move])
            except TypeError:
                print('THRESH_VAL:', self.thresh_val, 'MOVE:', move)
            # trim to movements in the time window
            thresh_val = self.thresh_val[self.thresh_val['timestamp'] > time.time()-self.integrate_dur]

            thresh_update = self.calc_move(thresh_val)

            if (thresh_update < self.thresh) and (self.measure_time+self.integrate_dur < time.time()):
                do_trigger = True

        elif self.mode == 'dist':
            thresh_update = self.calc_move(move)
            self.thresh_val += thresh_update

            if self.thresh_val > self.thresh:
                do_trigger = True

        else:
            Warning ("mode is not defined! mode is {}".format(self.mode))


        return do_trigger

    def calc_move(self, move, thresh_type=None):
        """
        Calculate distance move depending on type (x, y, total dist)

        Args:
            move ():
            thresh_type ():

        Returns:

        """

        if thresh_type is None:
            thresh_type = self.thresh_type

        # FIXME: rly inefficient
        # get the value of the movement depending on what we're measuring
        if thresh_type == 'x':

            distance = np.sum(move['vel'][move['dir'] == "REL_X"])
        elif thresh_type == 'y':
            distance = np.sum(move['vel'][move['dir'] == "REL_Y"])
        elif thresh_type == "dist":
            x_dist = np.sum(move['vel'][move['dir'] == "REL_X"])
            y_dist = np.sum(move['vel'][move['dir'] == "REL_Y"])
            distance = np.abs(np.sqrt(float(x_dist ** 2) + float(y_dist ** 2)))

        return distance

    def thresh_trig(self):


        if self.digi_out:
            self.digi_out.pulse()

        self.measure_evt.clear()




    def assign_cb(self, trigger_fn):
        # want to have callback write an output pin -- so callback should go back to
        # the task to write a GPIO pin.
        self.trig_fn = trigger_fn

    def l_measure(self, value):
        """
        Task has signaled that we need to start measuring movements for a trigger


        Args:
            value ():
        """

        if 'mode' in value.keys():
            if value['mode'] in self.MODES:
                self.mode = value['mode']
            else:
                Warning('incorrect mode sent: {}, needs to be one of {}'.format(value['mode'], self.MODES))

        if 'thresh' in value.keys():
            self.thresh = float(value['thresh'])

        if self.mode == "steady":
            self.thresh_val = np.array([(0, "REL_Y", 0)], dtype=self.MOVE_DTYPE)
        else:
            self.thresh_val = 0.0
        self.measure_time = time.time()

        self.measure_evt.set()

        sys.stdout.flush()

    def l_clear(self, value):
        """
        Stop measuring!

        Args:
            value ():

        Returns:

        """
        self.measure_evt.clear()

    def l_stop(self, value):
        """
        Stop measuring and clear system resources
        Args:
            value ():

        Returns:

        """

        self.measure_evt.set()
        self.release()

    def release(self):
        self.quit_evt.clear()


class Scale(Hardware):
    """
    Note:
        Not implemented, working on using a digital scale to
        make weighing faster.
    """
    MODEL={
        'stamps.com':{
            'vendor_id':0x1446,
            'product_id': 0x6a73

        }
    }
    def __init__(self, model='stamps.com', vendor_id = None, product_id = None):
        """
        Args:
            model:
            vendor_id:
            product_id:
        """
        self.vendor_id = self.MODEL[model]['vendor_id']
        self.product_id = self.MODEL[model]['product_id']

        if vendor_id:
            self.vendor_id = vendor_id
        if product_id:
            self.product_id = product_id

        # find device
        self.device = usb.core.find(idVendor=self.vendor_id,
                                    idProduct=self.product_id)
        # default configuration
        self.device.set_configuration()