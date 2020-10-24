from autopilot.hardware.gpio import Digital_Out
import numpy as np

DEFAULT_OFFSET = np.array((
    (26, 25, 25, 22, 26, 24),
    (26, 29, 27, 25, 25, 26),
    (24, 25, 25, 30, 25, 26),
    (27, 26, 27, 24, 29, 28),
    (26, 26, 28, 27, 26, 29),
    (26, 27, 28, 27, 20, 19)
))

class Parallax_Platform(Digital_Out):
    """
    Transcription of Cliff Dax's BASIC program

    * One column, but all rows can be controlled at once?
    * wait for some undefined small time between each flip of 23
    * to reset/rehome, some hardcoded offset from zero that needs to be stepped for each column.

    Pins:

    Column Control:
        * 8 = col & 1
        * 9 = col & 2
        * 10 = col & 4

    Row control:
        * 0 = word & 1
        * 1 = word & 2
        * 2 = word & 4
        * 3 = word & 8
        * 4 = word & 16
        * 5 = word & 32

    Others:
        * 22 - flipped on and off at every loop, light control?
        * 23 - flipped on and off to execute a movement command
        * 24 - if 0, go down, if 1, go up

    """

    output = True
    type="PARALLAX_PLATFORM"
    pigs_function = b"w"

    def __init__(self, *args, **kwargs):
        super(Parallax_Platform, self).__init__(*args, **kwargs)



    @property
    def pin(self):
        pass

    @pin.setter
    def pin(self, pin):
        pass

    @property
    def pull(self):
        pass

    @pull.setter
    def pull(self, pull):
        pass

