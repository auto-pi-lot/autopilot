import typing
import warnings

import numpy as np

from autopilot.transform.transforms import Transform
from autopilot.transform.image import DLC


class Slice(Transform):
    """
    Generic selection processor
    """
    format_in = {'type': 'any'}
    format_out = {'type': 'any'}

    def __init__(self, select, *args, **kwargs):
        """


        Args:
            select (slice, tuple[slice], int, tuple[int]): a slice, tuple of slices, int, or tuple of ints! anything you can
                use inside of a pair of [square brackets].
            *args:
            **kwargs:
        """
        super(Slice, self).__init__(*args, **kwargs)

        # self.check_slice(select)

        self.select = select

    # def check_slice(self, select):
    #     if isinstance(select, tuple):
    #         if not all([isinstance(inner, slice) for inner in select]):
    #             raise ValueError('Selections require slices or tuples of slices')
    #     elif not isinstance(select, slice):
    #         raise ValueError('Selections require slices or tuples of slices')



    def process(self, input):
        return input[self.select]


class DLCSlice(Slice):
    """
    Select x,y coordinates of :class:`.DLC` output based on the name of the tracked parts

    note that min_probability is undefined when a list or tuple of part names are defined:
    the form of the returned array is ambiguous (how to tell which part is which when some might be excluded?)

    """
    format_in = {'type': np.ndarray,
                 'parent': DLC}
    format_out = {'type': np.ndarray}

    def __init__(self, select: typing.Union[str, tuple, list],
                 min_probability: float = 0,  *args, **kwargs):
        super(DLCSlice, self).__init__(select, *args, **kwargs)

        self.select_index = None

        if isinstance(select, (tuple, list)) and min_probability > 0:
            warnings.warn('min_probability is undefined when a list or tuple of part names are given, ignoring.')

        self.min_probability = np.clip(min_probability, 0, 1)

    def check_slice(self, select):
        if self._parent:
            # only check if we've already gotten a parent
            if isinstance(select, str):
                if select not in self._parent.live.cfg['all_joints_names']:
                    raise ValueError('DLC selections must be names of joints!')
            elif isinstance(select, (tuple, list)):
                for s in select:
                    if s not in self._parent.live.cfg['all_joints_names']:
                        raise ValueError('DLC selections must be names of joints!')

    def process(self, input: np.ndarray):
        if self.select_index is None:
            if isinstance(self.select, str):
                self.select_index = self._parent.live.cfg['all_joints_names'].index(self.select)
            else:
                self.select_index = np.array([self._parent.live.cfg['all_joints_names'].index(s) for s in self.select])

        point_row = input[self.select_index, :]
        if isinstance(self.select, str):
            if point_row[2] > self.min_probability:
                return point_row[0:2]
            else:
                return False
        else:
            return point_row