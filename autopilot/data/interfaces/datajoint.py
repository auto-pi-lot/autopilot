"""
Prototype interface to datajoint models using ``datajoint-babel``

This module was not completed and is left as a reference :)

"""

# import typing
# from typing import Optional
# from pydantic import BaseModel
# from datajoint_babel.constants import DATATYPES, TIERS
# from datajoint_babel.model.attribute import Attribute, DJ_Type, Comment
# from datajoint_babel.model.table import Table as DJTable
# from autopilot.data.interfaces.base import Interface_Mapset, Interface_Map, resolve_type
# from autopilot.exceptions import InterfaceError
#
# if typing.TYPE_CHECKING:
#     from autopilot.data.modeling.base import Table
#
# class Datajoint_Field(BaseModel):
#     """
#     Parameters that can be given to a field's ``datajoint`` key to
#     control its conversion to a datajoint model
#     """
#     key: bool = False
#     attribute: Optional[Attribute] = None
#
#
#
# Datajoint_Mapset = Interface_Mapset(
#     bool = Interface_Map(
#         equals=DJ_Type,
#         kwargs={"datatype": "tinyint"},
#         conversion=lambda x: bool(x)
#     ),
#     int = Interface_Map(
#         equals=DJ_Type,
#         kwargs={"datatype":"int"}
#     ),
#     float = Interface_Map(
#         equals=DJ_Type,
#         kwargs={"datatype":"float"}
#     ),
#     str = Interface_Map(
#         equals=DJ_Type,
#         kwargs={"datatype":"varchar", "args":[1024]}
#     ),
#     datetime = Interface_Map(
#         equals=DJ_Type,
#         kwargs={"datatype":"datetime"},
#         conversion=lambda x: x.strftime("%Y-%m-%d %H:%M:%S")
#     )
# )
#
# def model_to_datajoint(table: typing.Type['Table'], tier: TIERS='Manual' ) -> DJTable:
#     """
#     Convert a pydantic Table model to a datajoint Table model!
#     """
#     name = table.__name__
#     keys = []
#     attributes = []
#
#     for key, field in table.__fields__.items():
#
#         dj_kwargs = table.schema()['properties'][key].get('datajoint', {})
#         if 'datatype' in table.schema()['properties'][key].get('datajoint', {}):
#             type_str = table.schema()['properties'][key]['datajoint']['datatype']
#             dj_type = DJ_Type(datatype=type_str, **dj_kwargs.get('kwargs', {}))
#         else:
#             type_ = resolve_type(field.type_)
#             type_str = type_.__name__
#             dj_type = Datajoint_Mapset.get(type_str, kwargs=dj_kwargs.get('kwargs', {}))
#
#         comment = table.schema()['properties'][key].get('description', None)
#         default = field.default
#
#         attribute = Attribute(name=key, datatype=dj_type, comment=comment, default=default)
#
#         if dj_kwargs.get('key', False):
#             keys.append(attribute)
#         else:
#             attributes.append(attribute)
#
#     if len(keys) == 0:
#         raise InterfaceError("Need at least one field to be marked as a key")
#
#
#     model_comment = table.__doc__
#     if model_comment is None:
#         model_comment = ''
#     else:
#         model_comment = model_comment.strip().replace('\n', ' -- ')
#
#     dj_table = DJTable(name=name, tier=tier, comment=Comment(comment=model_comment), keys=keys, attributes=attributes)
#     return dj_table
