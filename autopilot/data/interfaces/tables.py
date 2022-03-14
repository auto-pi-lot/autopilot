"""
Interfaces for pytables and hdf5 generally
"""
from abc import abstractmethod
from typing import Optional

import tables

from autopilot import Autopilot_Type


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