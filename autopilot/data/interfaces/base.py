from abc import abstractmethod
import typing
from typing import Union, Type, Optional
from autopilot.root import Autopilot_Type
from autopilot.data.modeling.base import Schema, Group, Node

class Interface_Map(Autopilot_Type):
    """
    Statement of equivalence between two things, potentially with some
    translation or parameterization, such that a base type can be written
    to.

    """
    equals: typing.Type
    args: Optional[typing.List] = None
    kwargs: Optional[typing.Dict] = None
    conversion: Optional[typing.Callable] = None


class Interface_Mapset(Autopilot_Type):
    """
    Metaclass for mapping base types to another format.

    Each field can be a Type (if it is instantiated without arguments, or
    can use the :class:`.Interface_Map` to specify them.

    The special types ``group`` and ``node`` correspond to
    :class:`~.data.modeling.base.Group` and :class:`~.data.modeling.base.Node`
    classes, for when a given interface needs to do something to create an
    abstract representation of a group or node in a schema's hierarchy.

    .. todo::

        This will need to be generalized, eg. NWB doesn't need a mapping between types and objects,
        but mappings between annotated types and paths (eg. something within the `/data/trial_data` makes
        a behavioral series, etc).
    """
    bool: Union[Interface_Map, Type]
    int: Union[Interface_Map, Type]
    float: Union[Interface_Map, Type]
    str: Union[Interface_Map, Type]
    bytes: Union[Interface_Map, Type]
    datetime: Union[Interface_Map, Type]
    group: Optional[Union[Interface_Map, Type]]
    node: Optional[Union[Interface_Map, Type]]




class Interface(Schema):
    map: Interface_Mapset
    schema: Schema

    @abstractmethod
    def make(self) -> bool:
        """
        Make a given schema using the interface mapping given.

        Returns:
            bool: ``True`` if successful
        """


