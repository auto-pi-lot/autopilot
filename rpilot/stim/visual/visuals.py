"""
Visual Stimuli -- still very alpha
"""

WIN = None

from rpilot import prefs

import threading

print(prefs.prefdict.items())
if 'VISUAL' in prefs.CONFIG:
    from psychopy import visual, core


class Visual(object):
    """Metaclass for visual stimuli"""
    callback = None


    def __init__(self):
        # psychopy Window
        self.win = None
        self.duration = None
        self.ppo = None # psychopy object
        self.get_window()

        self.clock = core.Clock()
        self.draw_time = 0

        self.thread_lock = threading.Lock()

    def get_window(self):
        """
        Try to get the global visuals.WIN window,
        if it hasn't been made yet, make it.
        """
        if globals()['WIN'] is not None:
            self.win = globals()['WIN']
        else:
            try:
                global WIN
                WIN = visual.Window(winType="pyglet")
                self.win = WIN
            except:
                Exception("Couldn't get psychopy Window!")




class Grating(Visual):
    """
    Moving grating
    """

    PARAMS = ['angle', 'freq', 'rate', 'phase',
              'mask', 'pos', 'size', 'duration']

    def __init__(self, angle, freq, rate, phase=0,
                 mask="gauss", pos=(0., 0.), size=None,
                 duration=5000.):
        super(Grating, self).__init__()

        self.angle = angle
        self.freq = freq
        self.rate = rate
        self.phase = phase
        self.mask = mask
        self.pos = pos
        self.size = size
        self.duration = duration

        # init psychopy object
        self.ppo = visual.GratingStim(
            self.win,
            mask = self.mask,
            pos = self.pos,
            size = self.size,
            sf = self.freq,
            ori = self.angle,
            phase = self.phase)

    def set(self, attr, value):
        """
        Set psychopy attrs

        Args:
            attr ():
            value ():

        Returns:

        """
        attr_map = {
            'mask':'mask', 'pos':'pos', 'size':'size',
            'freq':'sf', 'angle':'ori', 'phase':'phase'
        }

        if attr in ('mask', 'pos', 'size', 'freq', 'angle', 'phase'):
            setattr(self.ppo, attr_map[attr], value)


    def update(self):
        """advance the psychopy object one frame"""

        # get change since last draw, divide by rate
        dt = self.clock.getTime()-self.draw_time
        self.ppo.phase = (self.ppo.phase + self.rate*dt) % 1.0
        self.draw_time = self.clock.getTime()


    def play(self):
        threading.Thread(target=self._play).start()

    def _play(self):
        with self.thread_lock:
            # reset stim
            self.ppo.phase = self.phase

            start_time = self.clock.getTime()
            end_time = start_time + (self.duration/1000.0)
            while self.clock.getTime() < end_time:
                self.update()
                self.ppo.draw()
                self.win.flip()

            # another flip clears the screen
            self.win.flip()


class Grating_Continuous(Grating):
    """
    Moving grating that goes continuously, but changes angles
    """

    PARAMS = ['angle', 'freq', 'rate', 'phase',
              'mask', 'pos', 'size']

    def __init__(self, **kwargs):
        super(Grating_Continuous, self).__init__(**kwargs)
        self.stop_flag = threading.Event()
        self.stop_flag.clear()

    def start(self):
        self.stop_flag.set()
        while self.stop_flag:
            self.play()
        self.win.flip()

    def stop(self):
        self.stop_flag.clear()


    def play(self):
        """
        draws continuously
        Returns:

        """
        self.update()
        self.ppo.draw()
        self.win.flip()







