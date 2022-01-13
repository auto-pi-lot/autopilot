import numpy as np

from autopilot.transform.transforms import Transform


class Condition(Transform):
    """
    Compare the input against some condition
    """


    def __init__(self, minimum=None, maximum=None, elementwise=False, *args, **kwargs):
        """

        Args:
            minimum:
            maximum:
            elementwise (bool): if False, return True only if *all* values are within range. otherwise return bool for each tested value
            *args:
            **kwargs:
        """

        if minimum is None and maximum is None:
            raise ValueError("need either a maximum or minimum!")

        super(Condition, self).__init__(*args, **kwargs)

        self._minimum = None
        self._maximum = None
        self._shape = None
        self.elementwise = elementwise

        if minimum is not None:
            self.minimum = minimum

        if maximum is not None:
            self._maximum = maximum


    def process(self, input):

        if self.minimum is not None:
            is_greater = np.greater(input, self.minimum)
            if self.maximum is None:
                combined = is_greater

        if self.maximum is not None:
            is_lesser = np.less(input, self.maximum)
            if self.minimum is None:
                combined = is_lesser

        if self.minimum is not None and self.maximum is not None:
            combined = np.logical_and(is_greater, is_lesser)

        if not self.elementwise:
            combined = np.all(combined)

        return combined






    @property
    def minimum(self) -> [np.ndarray, float]:
        return self._minimum

    @minimum.setter
    def minimum(self, minimum: [np.ndarray, float]):

        if isinstance(minimum, list):
            minimum = np.array(minimum)

        if isinstance(minimum, float) or isinstance(minimum, int):
            shape = (1,)
        elif isinstance(minimum, np.ndarray):
            shape = minimum.shape
        else:
            raise ValueError('minimum must be a float or ndarray')

        if self._shape:
            if shape != self._shape:
                raise ValueError('cant change shape!')


        self._shape = shape
        self._minimum = minimum

    @property
    def maximum(self) -> [np.ndarray, float]:
        return self._maximum

    @maximum.setter
    def maximum(self, maximum: [np.ndarray, float]):
        if isinstance(maximum, list):
            minimum = np.array(maximum)

        if isinstance(maximum, float) or isinstance(maximum, int):
            shape = (1,)
        elif isinstance(maximum, np.ndarray):
            shape = maximum.shape
        else:
            raise ValueError('maximum must be a float or ndarray')

        if self._shape:
            if shape != self._shape:
                raise ValueError('cant change shape!')

        self._shape = shape
        self._maximum = maximum

    @property
    def format_in(self) -> dict:
        if self._shape == (1,):
            ret = {
                'type': float,

            }
        else:
            ret = {
                'type': np.ndarray
            }

        ret['shape'] = self._shape

        return ret


    @property
    def format_out(self) -> dict:
        if self._shape == (1,):
            ret = {
                'type': bool,
            }
        else:
            ret = {
                'type': np.ndarray
            }

        if self.elementwise:
            ret['shape'] = self._shape
        else:
            ret['type'] = bool
            ret['shape'] = (1,)

        return ret


class Compare(Transform):
    """
    Compare processed values using some function that returns a boolean

    ie. process will ``return compare_fn(*args)`` from ``process``.

    it is expected that ``input`` will be an iterable with len > 1
    """
    def __init__(self, compare_fn:callable, *args, **kwargs):
        """
        Args:
            compare_fn (callable): Function used to compare the values given to :meth:`.Compare.process`
            *args ():
            **kwargs ():
        """
        super(Compare, self).__init__(*args, **kwargs)

        self.compare_fn = compare_fn

    def process(self, input):
        return self.compare_fn(*input)