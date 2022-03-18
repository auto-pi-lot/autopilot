"""
Abstract Root Objects from which all other autopilot objects inherit from.

These objects are not intended to be instantiated on their own,
and this module should not import from any other autopilot module
"""
import logging
from logging import Logger
import typing

from pydantic import BaseModel, BaseSettings, PrivateAttr

def no_underscore_all_caps(input: str) -> str:
    """
    prefs used to be ``'ALLCAPS'`` instead of ``'ALL_CAPS'``. In general, these
    should be considered degenerate, and no future prefs should be declared that depend
    on the presence of the underscore.


    Args:
        input (str): input string

    Returns:
        str: without underscores and in allcaps.
    """
    return input.replace('_', '').upper()


class Autopilot_Type(BaseModel):
    """
    Root autopilot model for types
    """
    _logger: typing.Optional[Logger] = PrivateAttr()


    def _init_logger(self):
        from autopilot.core.loggers import init_logger
        self._logger = init_logger(self)



class Autopilot_Pref(BaseSettings):
    """
    Root autopilot model for prefs

    All settings can be declared with an environment variable
    prefixed with ``'AUTOPILOT_'``
    """

    class Config:
        env_prefix = "AUTOPILOT_"
        alias_generator = no_underscore_all_caps