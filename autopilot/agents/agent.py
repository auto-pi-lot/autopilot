"""
Draft: Base class for agents. At the moment, just some unused hooks
for the purpose of putting them in the place they should be.
"""

from autopilot.root import Autopilot_Type
from autopilot.external import Process
from abc import abstractmethod
import typing
from typing import List, Optional, Union, Type

class Agent(Autopilot_Type):
    """
    Metaclass for autopilot agents. Currently draft status.

    Private methods are placeholders.
    When formalizing, transition private methods to abstract methods
    """

    def __init__(self):




    def _preinit_external(self, processes:Union[List[Type[Process]], Type[Process]]) -> :
        """
        Initialize external processes needed before the agent is spawned
        """


    def _preinit(self):
        """
        Preinitialization for the agent itself
        """

    # TODO continue checking existing agents for lifecycle methods