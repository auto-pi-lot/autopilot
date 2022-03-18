"""
Base classes for data models -- the ``Data`` class itself.
"""
import typing
from typing import Optional, List

import tables

from autopilot.root import Autopilot_Type

class Data(Autopilot_Type):
    """
    A recursive unit of data.

    We need to have the abstract representation of data: eg. for this experiment
        expect this kind of data in general. It will come in as a series rather than a unit.


    and we also need the instantaneous representation of data: using as an instance,
        link my data to this other data *right here*.

    There is no distinction between trialwise vs continuous data. A unit of data
    is just that collection of things that you would collect in a moment.

    So we need
        * something that can declare data as a particular type (its representation)
        * something that can declare data as a semantic value (this has this particular *meaning*
            of a piece of data, eg. this is a *positional* series or a

    but the relationship between them and it can get especially tricky when you get performance
        needs involved. eg. you want a very thin wrapper around the literal values of things,
        so being able to abstract their implementation from their structure is the whole point:
        use the 'pytables' backend when you want fast local writing, use some database when you want
        reliable storage split async across multiple clients, use nwb to export to but not necessarily
        to write to (but be able to translate data from another representation to it).

    So a data container should yield an active means of interacting with it. The data object
        exposes several APIs
        * type declaration
        * reading/writing routines (mixin? context provider? eg like when used by this object you provide this type?)
        * link structure between different declared data elements.

    Data may have

        * A ``Value`` -- the
    """

class Table(Data):
    """To be made into a table!"""

    @classmethod
    def to_pytables_description(cls) -> typing.Type[tables.IsDescription]:
        """
        Convert the fields of this table to a pytables description
        """
        from autopilot.data.interfaces.tables import model_to_table
        return model_to_table(cls)

    @classmethod
    def from_pytables_description(cls, description:typing.Type[tables.IsDescription]) -> 'Table':
        """
        Create an instance of a table from a pytables description
        """
        from autopilot.data.interfaces.tables import table_to_model
        return table_to_model(description, cls)




class Attributes(Data):
    """A set of attributes that's intended to be singular, rather than made into a table."""

class Schema(Autopilot_Type):
    """
    A special type of type intended to be a representation of an
    abstract structure/schema of data, rather than a live container of
    data objects themselves. This class is used for constructing data containers,
    translating between formats, etc. rather than momentary data handling
    """


class Group(Autopilot_Type):
    """
    A generic representation of a "Group" if present in a given interface.
    Useful for when, for example in a given container format you want to
    make an empty group that will be filled later, or one that has to be
    present for syntactic correctness.
    """
    args: Optional[list] = None
    kwargs: Optional[dict] = None


class Node(Autopilot_Type):
    """
    :class:`.Group`, but for nodes.
    """
    args: Optional[list] = None
    kwargs: Optional[dict] = None
