import pdb
from abc import abstractmethod
import typing
from datetime import datetime
from typing import Union, Type, Optional

from autopilot.root import Autopilot_Type
from autopilot.data.modeling.base import Schema
from autopilot.data.units.base import Autopilot_Unit
from pydantic import Field


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
    bytes: Optional[Union[Interface_Map, Type]]
    datetime: Union[Interface_Map, Type]
    group: Optional[Union[Interface_Map, Type]]
    node: Optional[Union[Interface_Map, Type]]

    def get(self, key, args:Optional[list]=None, kwargs:Optional[dict]=None):
        ret = getattr(self, key)
        if isinstance(ret, Interface_Map):
            _args = ret.args
            if _args is None:
                _args = []
            if args is not None:
                _args = args

            _kwargs = ret.kwargs
            if _kwargs is None:
                _kwargs = {}
            if kwargs is not None:
                _kwargs.update(kwargs)
            return ret.equals(*_args, **_kwargs)
        else:
            return ret()





class Interface(Autopilot_Type):
    """
    Create a representation of a given Schema
    """
    map: Interface_Mapset
    schema_: Schema = Field(..., alias='schema')

    @abstractmethod
    def make(self, input:typing.Any) -> bool:
        """
        Make a given schema using the interface mapping given.

        Returns:
            bool: ``True`` if successful
        """


def resolve_type(type_, resolve_literal=False) -> typing.Type:
    """
    Get the "inner" type of a model field, sans Optionals and Unions and the like

    Args:
        resolve_literal (bool): If ``True``, return the type of the inside of Literals, rather than the Literal type itself.
    """
    if not hasattr(type_, '__args__') or (hasattr(type_, '__origin__') and type_.__origin__ == typing.Literal and not resolve_literal):
        # not an extended typing object.
        try:
            if issubclass(type_, Autopilot_Unit):
                type_ = type_._base_class()
        except TypeError:
            # Not a class, pass
            pass
        return type_

    if getattr(type_, '__origin__', False) is typing.Literal:
        subtypes = [type(t) for t in type_.__args__ if type(t) in _permissiveness.keys()]
    elif getattr(type_, '__origin__', False) is typing.Union:
        subtypes = [resolve_type(t) for t in type_.__args__]
    else:
        # # check if this is just a list of a data type
        # if len(type_.__args__) == 1 and isinstance(type_.__args__[0], ModelMetaclass):
        #     # list of a model type!
        #     return type_.__args__[0]
        subtypes = [t for t in type_.__args__ if t in _permissiveness.keys()]

    if len(subtypes) == 0:
        # if we only have one type, there's no ambiguity to resolve.
        if len(type_.__args__) == 1:
            return type_.__args__[0]
        pdb.set_trace()
        raise ValueError(f'Dont know how to resolve type {type_}')
    # elif any([isinstance(t, ModelMetaclass) for t in subtypes]):
    #     subtypes = [t for t in subtypes if isinstance(t, ModelMetaclass)]
    #     return subtypes[0]

    # sort by permissiveness
    types = [(t, _permissiveness[t]) for t in subtypes]
    types.sort(key=lambda x: x[1])
    return types[-1][0]


_permissiveness = {
    type(None):-1,
    bool:0,
    int:1,
    float:2,
    str:3,
    dict:0,
    datetime:0
}
_NUMPY_TO_BUILTIN = {
    'b': bool,
    'i': int,
    'u': int,
    'f': float,
    'c': complex,
    'M': datetime,
    'O': str,
    'S': str,
    'U': str
}