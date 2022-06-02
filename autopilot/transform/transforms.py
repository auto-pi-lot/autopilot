"""
Data transformations.

Experimental module.

Reusable transformations from one representation of data to another.
eg. converting frames of a video to locations of objects,
or locations of objects to area labels

.. todo::

    This is a preliminary module and it purely synchronous at the moment. It will be expanded to ...
    * support multiple asynchronous processing rhythms
    * support automatic value coercion

    The following design features need to be added
    * recursion checks -- make sure a child hasn't already been added to a processing chain.
"""

import types
import typing
from enum import Enum, auto
from autopilot.utils.loggers import init_logger

class TransformRhythm(Enum):
    """
    Attributes:
        FIFO: First-in-first-out, process inputs as they are received, potentially slowing down the transformation pipeline
        FILO: First-in-last-out, process the most recent input, ignoring previous (lossy transformation)
    """
    FIFO = auto()
    FILO = auto()

class Transform(object):
    """
    Metaclass for data transformations

    Each subclass should define the following

    * :meth:`.process` - a method that takes the input of the transoformation as its single argument and returns the transformed output
    * :attr:`.format_in` - a `dict` that specifies the input format
    * :attr:`.format_out` - a `dict` that specifies the output format

    Arguments:
        rhythm (:class:`TransformRhythm`): A rhythm by which the transformation object processes its inputs

    Attributes:
        child (class:`Transform`): Another Transform object chained after this one
    """

    def __init__(self, rhythm : TransformRhythm = TransformRhythm.FILO, *args, **kwargs):
        self._child = None
        self._check = None
        self._rhythm = None
        self._process = None
        self._format_in = None
        self._parent = None
        self._coerce = None


        self.rhythm = rhythm

        self.logger = init_logger(self)

        # self._wrap_process()

    @property
    def rhythm(self) -> TransformRhythm:
        return self._rhythm

    @rhythm.setter
    def rhythm(self, rhythm: TransformRhythm):
        if rhythm not in TransformRhythm:
            raise ValueError(f'rhythm must be one of TransformRhythm, got {rhythm}')
        self._rhythm = rhythm

    @property
    def format_in(self) -> dict:
        raise NotImplementedError('Every subclass of Transform must define format_in!')

    @format_in.setter
    def format_in(self, format_in: dict):
        raise NotImplementedError('Every subclass of Transform must define format_in!')

    @property
    def format_out(self) -> dict:
        raise NotImplementedError('Every subclass of Transform must define format_out!')

    @format_out.setter
    def format_out(self, format_out: dict):
        raise NotImplementedError('Every subclass of Transform must define format_out!')

    @property
    def parent(self) -> typing.Union['Transform', None]:
        """
        If this Transform is in a chain of transforms, the transform that precedes it

        Returns:
            :class:`.Transform`, ``None`` if no parent.
        """
        return self._parent

    @parent.setter
    def parent(self, parent):
        if not issubclass(type(parent), Transform):
            raise TypeError('parents must be subclasses of Transform')
        self._parent = parent


    def process(self, input):
        raise NotImplementedError('Every subclass of Transform must define its own process method!')

    def reset(self):
        """
        If a transformation is stateful, reset state.
        """
        raise Warning('reset method not explicitly overridden in transformation, doing nothing!')

    def check_compatible(self, child: 'Transform'):
        """
        Check that this Transformation's :attr:`.format_out` is compatible with another's :attr:`.format_in`

        .. todo::

            Check for types that can be automatically coerced into one another and set :attr:`_coercion` to appropriate function

        Args:
            child (:class:`Transform`): Transformation to check compatibility

        Returns:
            bool
        """

        ret = False

        if isinstance(child.format_in['type'], (list, tuple)):
            if self.format_out['type'] in child.format_in['type']:
                ret = True
        elif child.format_in['type'] == 'any':
            ret = True
        elif self.format_out['type'] == child.format_in['type']:
            ret = True


        # if child has a specific requirement of parent transform class, ensure
        parent_req = child.format_in.get('parent', False)
        if parent_req:
            if not isinstance(self, parent_req):
                ret = False

        return ret

        # if self.format_out['type'] in (int, np.int, )

    def __add__(self, other):
        """
        Add another Transformation in the chain to make a processing pipeline

        Args:
            other (:class:`Transformation`): The transformation to be chained
        """
        if not issubclass(type(other), Transform):
            raise RuntimeError('Can only add subclasses of Transform to other Transforms!')

        if self._child is None:
            # if we haven't been chained at all yet, claim the child
            # first check if it aligns

            #if not self.check_compatible(other):
            #    raise ValueError(f'Incompatible transformation formats: \nOutput: {self.format_out},\nInput: {other.format_in}')


            self._child = other
            self._child.parent = self

            # override our process method with one that calls recursively
            # back it up first
            self._process = self.process

            def new_process(self, input):
                return self._child.process(self._process(input))

            self.process = types.MethodType(new_process, self)

        else:
            # we already have a child,
            # add it to our child instead (potentially recursively)
            self._child = self._child + other

        return self


