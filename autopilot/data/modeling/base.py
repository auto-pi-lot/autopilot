"""
Base classes for data models -- the ``Data`` class itself.
"""
import typing
from datetime import datetime
from typing import Optional, List

import pandas as pd
import tables

from autopilot.root import Autopilot_Type

class Data(Autopilot_Type):
    """
    The top-level container for Data.

    Subtypes will define more specific formats and uses of data, but this is the most general
    form used to represent the type and meaning of data.

    The Data class is not intended to contain individual fields, but collections of data that are collected
    as a unit, whether that be a video frame along with its timestamp and encoding, or a single trial of behavioral data.

    This class is also generally not intended to be used for the literal transport of data when performance is
    necessary: this class by default does type validation on instantiation that takes time (see the `construct <https://pydantic-docs.helpmanual.io/usage/models/#creating-models-without-validation>`_
    method for validation-less creation). It is usually more to specify the type, grouping, and annotation for
    a given unit of data -- though users should feel free to dump their data in a :class:`.Data` object if
    it is not particularly performance sensitive.
    """

class Table(Data):
    """
    Tabular data: each field will have multiple values -- in particular an equal number across fields.

    Used for trialwise data, and can be used to create pytables descriptions.

    .. todo::

        To make this usable as a live container of data, the fields need to be declared as Lists (eg. instead of just
        declaring something an ``int``, it must be specified as a ``List[int]`` to pass validation. We should expand this
        model to relax that constraint and effectively treat every field as containing a list of values.
    """

    @classmethod
    def to_pytables_description(cls) -> typing.Type[tables.IsDescription]:
        """
        Convert the fields of this table to a pytables description.

        See :func:`~.interfaces.tables.model_to_description`
        """
        from autopilot.data.interfaces.tables import model_to_description
        return model_to_description(cls)

    @classmethod
    def from_pytables_description(cls, description:typing.Type[tables.IsDescription]) -> 'Table':
        """
        Create an instance of a table from a pytables description

        See :func:`~.interfaces.tables.description_to_model`

        Args:
            description (:class:`tables.IsDescription`): A Pytables description
        """
        from autopilot.data.interfaces.tables import description_to_model
        return description_to_model(description, cls)

    def to_df(self) -> pd.DataFrame:
        """
        Create a dataframe from the lists of fields

        Returns:
            :class:`pandas.DataFrame`
        """
        return pd.DataFrame(self.dict())




class Attributes(Data):
    """
    A set of attributes that is intended to have a single representation per usage:
    eg. a subject has a single set of biographical information.

    Useful to specify a particular type of storage that doesn't need to include variable
    numbers of each field (eg. the tables interface stores attribute objects as metadata on a node, rather than as a table).
    """

class Schema(Autopilot_Type):
    """
    A special type of type intended to be a representation of an
    abstract structure/schema of data, rather than a live container of
    data objects themselves. This class is used for constructing data containers,
    translating between formats, etc. rather than momentary data handling
    """




class Node(Autopilot_Type):
    """
    Abstract representation of a Node in a treelike or linked data structure.
    This should be extended by interfaces when relevant and needed to implement
    an abstract representation of their structure.

    This class purposely lacks structure like a path or parents pending further
    usage in interfaces to see what would be the best means of implementing them.
    """


class Group(Autopilot_Type):
    """
    A generic representation of a "Group" if present in a given interface.
    Useful for when, for example in a given container format you want to
    make an empty group that will be filled later, or one that has to be
    present for syntactic correctness.

    A children attribute is present because it is definitive of groups, but
    should be overridden by interfaces that use it.
    """
    children: Optional[List[Node]] = None

BASE_TYPES = (
    bool, int, float, str, bytes, datetime
)
"""
Base Python types that should be suppported by every interface
"""