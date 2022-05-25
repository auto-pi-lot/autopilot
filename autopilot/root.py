"""
Abstract Root Objects from which all other autopilot objects inherit from.

These objects are not intended to be instantiated on their own,
and this module should not import from any other autopilot module
"""
from logging import Logger
import typing
from typing import Optional
from pprint import pformat
from abc import ABC


from pydantic import BaseModel, BaseSettings, PrivateAttr

def no_underscore_all_caps(input: str) -> str:
    """
    prefs used to be ``'ALLCAPS'`` instead of ``'ALL_CAPS'``. In general, these
    should be considered degenerate, and no future prefs should be declared that depend
    on the presence of the underscore.

    Used by :class:`.Autopilot_Pref` to generate Aliases

    Args:
        input (str): input string

    Returns:
        str: without underscores and in allcaps.
    """
    return input.replace('_', '').upper()

class Autopilot_Type(BaseModel, ABC):
    """
    Root autopilot model for types
    """
    _logger: typing.Optional[Logger] = PrivateAttr()

    def _init_logger(self):
        from autopilot.utils.loggers import init_logger
        self._logger = init_logger(self)

    def __str__(self):
        return pformat(self.dict(), indent=2, compact=True)

# remove default __init__ docstring that propagates down to all submodels
Autopilot_Type.__init__.__doc__ = ""

class Autopilot_Pref(BaseSettings):
    """
    Root autopilot model for prefs

    All settings can be declared with an environment variable
    prefixed with ``'AUTOPILOT_'``
    """

    class Config:
        env_prefix = "AUTOPILOT_"
        alias_generator = no_underscore_all_caps


class Autopilot_Object(ABC):
    """
    Meta-object for autopilot object types
    """

    def __init__(self, id:Optional[str]=None):
        super(Autopilot_Object, self).__init__()
        self.id = id
        self.logger = self._init_logger()

    def _init_logger(self) -> Logger:
        from autopilot.utils.loggers import init_logger
        return init_logger(self)