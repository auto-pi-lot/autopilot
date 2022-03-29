"""
Interfaces for pytables and hdf5 generally
"""
import typing
from abc import abstractmethod
from typing import Optional, List
from pydantic import create_model

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

    def __init__(self, **data):
        self._init_logger()
        super().__init__(**data)

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
            self._logger.debug(f"Made group {'/'.join([self.parent, self.name])}")
            if self.attrs is not None:
                group._v_attrs.update(self.attrs)

        if self.children is not None:
            for c in self.children:
                c.make(h5f)
        h5f.flush()


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
            elif set(node.description._v_names) != set(list(self.description.columns.keys())):
                self._logger.warning(f"Found existing table with columns {node.description._v_names}, but requested a table with {list(self.description.columns.keys())}, remaking.")
                self._remake_table(h5f)

        except tables.exceptions.NoSuchNodeError:
            tab = h5f.create_table(self.parent, self.name, self.description,
                             title=self.title, filters=self.filters,
                             createparents=True,expectedrows=self.expectedrows)
            self._logger.debug(f"Made table {'/'.join([self.parent, self.name])}")
            if self.attrs is not None:
                tab._v_attrs.update(self.attrs)
        h5f.flush()

    def _remake_table(self, h5f:tables.file.File):
        """Remake an existing table, preserving original data. Mostly for adding new columns"""
        # existing table
        old_tab = h5f.get_node(self.path)

        # new table

        tmp_name = f"{self.name}_tmp"
        try:
            node = h5f.get_node('/'.join([self.parent, tmp_name]))
            node.remove()
        except tables.NoSuchNodeError:
            pass
        new_tab = h5f.create_table(self.parent, tmp_name, self.description,
                                   title=self.title, filters=self.filters,
                                   createparents=True,expectedrows=self.expectedrows)

        # check which columns to read and whether we should keep the old table
        old_cols = old_tab.colnames
        new_cols = new_tab.colnames
        remove_old = False
        would_lose = list(set(old_cols)-set(new_cols))
        to_keep = list(set(old_cols).intersection(new_cols))
        backup_name = f'{self.name}_bak--0'
        if len(would_lose) > 0:
            while backup_name in old_tab._v_parent._v_children.keys():
                name_pieces = backup_name.split('--')
                backup_name = '--'.join([*name_pieces[:-1],str(int(name_pieces[-1])+1)])

            self._logger.warning(f"Updating table would delete columns {would_lose}, keeping as {backup_name}")

        else:
            remove_old = True

        # create new rows
        for i in range(old_tab.nrows):
            new_tab.row.append()
        new_tab.flush()

        # copy columns
        for add_column in to_keep:
            getattr(new_tab.cols, add_column)[:] = getattr(old_tab.cols, add_column)[:]
        new_tab.flush()

        # move or delete old table
        if remove_old:
            self._logger.debug(f'Removing table {old_tab}')
            old_tab.remove()
        else:
            old_tab.move(self.parent, backup_name)

        # move new table
        new_tab.move(self.parent, self.name)

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

_permissiveness = {
    bool:0,
    int:1,
    float:2,
    str:3,
    dict:0,
    datetime:0
}

def _resolve_type(type_) -> typing.Type:
    """
    Get the "inner" type of a model field, sans Optionals and Unions and the like
    """
    if not hasattr(type_, '__args__') or (hasattr(type_, '__origin__') and type_.__origin__ == typing.Literal):
        # already resolved
        return type_

    subtypes = [t for t in type_.__args__ if t in _permissiveness.keys()]
    if len(subtypes) == 0:
        raise ValueError(f'Dont know how to resolve type {type_}')

    # sort by permissiveness
    types = [(t, _permissiveness[t]) for t in subtypes]
    types.sort(key=lambda x: x[1])
    return types[-1][0]

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
        type_ = _resolve_type(field.type_)
        type_str = type_.__name__
        cols[key] = Tables_Mapset.get(type_str)

    description = type(table.__name__, (tables.IsDescription,), cols) # type: typing.Type[tables.IsDescription]
    return description


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
"""
Mapping between dtype.kind and builtin types

see https://numpy.org/doc/stable/reference/generated/numpy.dtype.kind.html#numpy.dtype.kind

"""

def table_to_model(description: typing.Type[tables.IsDescription], cls:typing.Type['Table']) -> 'Table':
    """
    Make a pydantic :class:`.modeling.base.Table` from a :class:`tables.IsDescription`

    Args:
        description (:class:`tables.IsDescription`): to convert
        cls (:class:`.modeling.base.Table`): Subclass of Table to make

    Returns:
        Subclass of Table
    """
    description_dict = {}
    for key, col in description.columns.items():
        python_type = _NUMPY_TO_BUILTIN[col.dtype.kind]
        description_dict[key] = (python_type, ...)

    model = create_model(cls.__name__, __base__=cls, **description_dict)
    return model
