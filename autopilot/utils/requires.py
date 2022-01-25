"""
Stub module for specifying dependencies for Autopilot objects.

Draft for now, to be integrated in v0.5.0
"""
import typing
from importlib.util import find_spec
from importlib import metadata
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from packaging.specifiers import SpecifierSet

from autopilot.utils import types


@dataclass
class Requirement(ABC):
    """
    Base class for different kinds of requirements
    """
    name: str
    version: SpecifierSet = field(default=SpecifierSet(''))

    @property
    @abstractmethod
    def met(self) -> bool:
        """
        Check if a requirement is met

        Returns:
            bool: ``True`` if met, ``False`` otherwise
        """

    @abstractmethod
    def resolve(self) -> bool:
        """
        Try and resolve a requirement by getting packages, changing system settings, etc.

        Returns:
            bool: True if successful!
        """


@dataclass
class Git_Spec:
    """
    Specify a git repository or its subcomponents: branch, commit, or tag
    """
    url: types.URL
    branch: typing.Optional[str] = None
    commit: typing.Optional[str] = None
    tag: typing.Optional[str] = None

@dataclass
class Python_Package(Requirement):
    """
    Attributes:
        package_name (str): If a package is named differently in package repositories than it is imported,
            specify the ``package_name`` (default is ``package_name == name``). The ``name`` will be used to test
            whether the package can be imported, and ``package_name`` used to install from the specified ``repository`` if not
        repository (:class:`~.autopilot.utils.types.URL`): The URL of a python package repository to use to install.
            Defaults to pypi
        git (class:`.Git_Spec`): Specify a package comes from a particular git repository, commit, or branch instead of from
            a package repository. If ``git`` is present, ``repository`` is ignored.
    """
    package_name: typing.Optional[str] = None
    repository: types.URL = types.URL("https://pypi.org/simple")
    git: typing.Optional[Git_Spec] = None

    def __post_init__(self):
        if self.package_name is None:
            self.package_name = self.name

    @property
    def met(self) -> bool:
        """
        Return ``True`` if python package is found in the PYTHONPATH that satisfies the ``SpecifierSet``
        """
        importable = False
        version_match = False
        # check if we have an import spec (the package is importable
        spec = find_spec(self.name)

        if spec:
            importable = True

            version = metadata.version(self.package_name)
            version_match = self.version.contains(version)


        if importable and version_match:
            return True
        else:
            return False
        # TODO: add informative messages if present but outdated

    def resolve(self) -> bool:
        raise NotImplementedError


@dataclass
class System_Library(Requirement):
    """
    System-level package

    .. warning::

        not implemented

    """


@dataclass
class Requirements:
    """
    Dataclass for a collection of requirements for a particular object. Each object should have at most
    one ``Requirements`` object, which may have many sub-requirements

    Attributes:
        requirements (list[Requirement]): List of requirements.
            (a singular requirement should have an identical API to requirements, the met and resolve methods)
    """
    requirements: typing.Union[typing.List[Requirement]]

    @property
    def met(self) -> bool:
        """
        Checks if the specified requirements are met

        Returns:
            bool: ``True`` if requirements are met, ``False`` if not
        """
        all_met = [req.met for req in self.requirements]
        return all(all_met)

    def resolve(self) -> bool:
        raise NotImplementedError

    def __add__(self, other):
        """
        Add requirement sets together

        .. warning::

            Not Implemented

        Args:
            other ():

        Returns:

        """
        raise NotImplementedError()