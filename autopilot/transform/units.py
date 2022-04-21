"""
For converting between things that are the same thing but have different numbers and shapes
"""

import typing
from enum import Enum, auto
import numpy as np
import colorsys

from autopilot.transform.transforms import Transform


class Rescale(Transform):
    """
    Rescale values from one range to another
    """

    format_in = {'type': (np.ndarray, float, int, tuple, list)}
    format_out = {'type': np.ndarray}

    def __init__(self,
                 in_range: typing.Tuple[float, float] = (0, 1),
                 out_range: typing.Tuple[float, float] = (0, 1),
                 clip = False,
                 *args, **kwargs):

        super(Rescale, self).__init__(*args, **kwargs)

        self.in_range = in_range
        self.out_range = out_range

        self.in_diff = self.in_range[1] - self.in_range[0]
        self.out_diff = self.out_range[1] - self.out_range[0]
        self.ratio = self.out_diff / self.in_diff

        self.clip = clip

    def process(self, input):
        """
        Subtract input minimum, multiple by output/input size ratio, add output minimum
        """
        if isinstance(input, (tuple, list)):
            input = np.array(input)

        input = ((input - self.in_range[0]) * self.ratio) + self.out_range[0]

        if self.clip:
            input = np.clip(input, self.out_range[0], self.out_range[1])
        return input

class Colorspaces(Enum):
    HSV = auto()
    RGB = auto()
    YIQ = auto()
    HLS = auto()



class Color(Transform):
    """
    Convert colors using the colorsys module!!

    .. note::

        All inputs must be scaled (0,1) and all outputs will be (0,1)
    """
    format_in = {'type': tuple}
    format_out = {'type': tuple}

    CONVERSIONS = {}
    CONVERSIONS[Colorspaces.RGB] = {}
    CONVERSIONS[Colorspaces.YIQ] = {}
    CONVERSIONS[Colorspaces.HLS] = {}
    CONVERSIONS[Colorspaces.HSV] = {}
    CONVERSIONS[Colorspaces.RGB][Colorspaces.YIQ] = colorsys.rgb_to_yiq
    CONVERSIONS[Colorspaces.YIQ][Colorspaces.RGB] = colorsys.yiq_to_rgb
    CONVERSIONS[Colorspaces.RGB][Colorspaces.HLS] = colorsys.rgb_to_hls
    CONVERSIONS[Colorspaces.HLS][Colorspaces.RGB] = colorsys.hls_to_rgb
    CONVERSIONS[Colorspaces.RGB][Colorspaces.HSV] = colorsys.rgb_to_hsv
    CONVERSIONS[Colorspaces.HSV][Colorspaces.RGB] = colorsys.hsv_to_rgb

    def __init__(self,
                 convert_from: Colorspaces = Colorspaces.HSV,
                 convert_to: Colorspaces = Colorspaces.RGB,
                 output_scale = 255, *args, **kwargs):
        super(Color, self).__init__(*args, **kwargs)

        self.convert_from = convert_from
        self.convert_to = convert_to

        # select processing function based on colors given
        self.process_fn = self.CONVERSIONS[self.convert_from][self.convert_to]

    def process(self, input, *args):
        if len(args)>0:
            return np.array(self.process_fn(input, args[0], args[1]))
        else:
            return np.array(self.process_fn(*input))




