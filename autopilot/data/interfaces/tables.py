"""
Interfaces for pytables and hdf5 generally
"""
import typing
from abc import abstractmethod
from typing import Optional, List
from datetime import datetime

if typing.TYPE_CHECKING:
    from datetime import datetime

import tables

from autopilot import Autopilot_Type
from autopilot.data.interfaces.base import Interface, Interface_Mapset, Interface_Map, Interface
if typing.TYPE_CHECKING:
    from autopilot.data.modeling.base import Table

_datetime_conversion: typing.Callable[[datetime], str] = lambda x: x.isoformat()


class H5F_Node(Autopilot_Type):
    """
    Base class for H5F Nodes
    """
    path:str
    title:Optional[str]=''
    filters:Optional[tables.filters.Filters]=None
    attrs:Optional[dict]=None

    @property
    def parent(self) -> str:
        """
        The parent node under which this node hangs.

        Eg. if ``self.path`` is ``/this/is/my/path``, then
        parent will be ``/this/is/my``

        Returns:
            str
        """
        return '/'.join(self.path.split('/')[:-1])

    @property
    def name(self) -> str:
        """
        Our path without :attr:`.parent`

        Returns:
            str
        """
        return self.path.split('/')[-1]

    @abstractmethod
    def make(self, h5f:tables.file.File):
        """
        Abstract method to make whatever this node is
        """

    class Config:
        arbitrary_types_allowed = True


class H5F_Group(H5F_Node):
    """
    Description of a pytables group and its location
    """
    children: Optional[List[H5F_Node]] = None

    def make(self, h5f:tables.file.File):
        """
        Make the group, if it doesn't already exist.

        If it exists, do nothing

        Args:
            h5f (:class:`tables.file.File`): The file to create the table in
        """

        try:
            node = h5f.get_node(self.path)
            # if no exception, already exists
            if not isinstance(node, tables.group.Group):
                raise ValueError(f'{self.path} already exists, but it isnt a group! instead its a {type(node)}')
        except tables.exceptions.NoSuchNodeError:
            group = h5f.create_group(self.parent, self.name,
                             title=self.title, createparents=True,
                             filters=self.filters)
            if self.attrs is not None:
                group._v_attrs.update(self.attrs)

        if self.children is not None:
            for c in self.children:
                c.make(h5f)


class H5F_Table(H5F_Node):
    description: tables.description.MetaIsDescription
    expectedrows:int=10000

    def make(self,  h5f:tables.file.File):
        """
        Make this table according to its description

        Args:
            h5f (:class:`tables.file.File`): The file to create the table in
        """
        try:
            node = h5f.get_node(self.path)
            if not isinstance(node, tables.table.Table):
                raise ValueError(f'{self.path} already exists, but it isnt a Table! instead its a {type(node)}')
        except tables.exceptions.NoSuchNodeError:
            tab = h5f.create_table(self.parent, self.name, self.description,
                             title=self.title, filters=self.filters,
                             createparents=True,expectedrows=self.expectedrows)
            if self.attrs is not None:
                tab._v_attrs.update(self.attrs)

    class Config:
        fields = {'description': {'exclude': True}}


Tables_Mapset = Interface_Mapset(
    bool = tables.BoolCol,
    int = tables.Int64Col,
    float = tables.Float64Col,
    str = Interface_Map(
        equals=tables.StringCol,
        args=[1024]
    ),
    bytes = Interface_Map(
        equals=tables.StringCol,
        args=[1024]
    ),
    datetime = Interface_Map(
        equals=tables.StringCol,
        args=[1024],
        conversion = _datetime_conversion
    ),
    group = H5F_Group
)

class Tables_Interface(Interface):
    map = Tables_Mapset

    def make(self, h5f:tables.file.File) -> bool:
        pass


def model_to_table(table: typing.Type['Table']) -> typing.Type[tables.IsDescription]:
    """
    Make a table description from the type annotations in a model

    Args:
        table (:class:`.modeling.base.Table`): Table description

    Returns:
        :class:`tables.IsDescription`
    """
    # get column descriptions
    cols = {}
    for key, field in table.__fields__.items():
        type_str = field.type_.__name__
        cols[key] = Tables_Mapset.get(type_str)

    description = type(table.__name__, (tables.IsDescription,), cols) # type: typing.Type[tables.IsDescription]
    return description


