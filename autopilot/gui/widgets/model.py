"""
Widget to fill fields for a pydantic model
"""
import typing
from typing import Union, List, Optional, Tuple, Type
from pydantic import BaseModel, Field
from datetime import datetime

from PySide2 import QtWidgets, QtGui

from autopilot.root import Autopilot_Type

class _Input(BaseModel):
    """
    Container for holding a widget and any applicable validators
    """
    widget: typing.Type
    validator: Optional[typing.Type] = None
    args: Optional[list] = Field(default_factory=list)
    kwargs: Optional[dict] = Field(default_factory=dict)
    range: Optional[Tuple[Union[int, float], Union[int, float]]] = None
    method_calls: Optional[List[Tuple[str, typing.List]]] = None
    """
    Names of methods to call after instantiation, passed as a tuple of (method_name, [method_args])
    """
    permissiveness: int = 0
    """
    When a type is annotated with a Union, the more permissive (higher number) 
    one will be chosen. Arbitrary units.
    """

    def make(self,
             widget_kwargs:Optional[dict]=None,
             validator_kwargs:Optional[dict]=None) -> QtWidgets.QWidget:
        if widget_kwargs is not None:
            kwargs = widget_kwargs
        else:
            kwargs = self.kwargs

        if validator_kwargs is not None:
            v_kwargs = validator_kwargs
        else:
            v_kwargs = {}

        widget = self.widget(*self.args, **kwargs)
        if self.validator:
            validator = self.validator(**v_kwargs)
            widget.setValidator(validator)

        if self.method_calls is not None:
            for methname, meth_args in self.method_calls:
                getattr(widget, methname)(*meth_args)

        return widget



_INPUT_MAP = {
    bool: _Input(widget=QtWidgets.QCheckBox),
    int: _Input(widget=QtWidgets.QLineEdit, validator=QtGui.QIntValidator, permissiveness=1),
    float: _Input(widget=QtWidgets.QLineEdit, validator=QtGui.QIntValidator, permissiveness=2),
    str: _Input(widget=QtWidgets.QLineEdit, permissiveness=3),
    datetime: _Input(widget=QtWidgets.QDateTimeEdit, method_calls=[('setCalendarPopup', [True])]),
    list: _Input(widget=QtWidgets.QLineEdit),
    typing.Literal: _Input(widget=QtWidgets.QComboBox)
}


class Model_Filler(QtWidgets.QWidget):
    """
    A widget to fill the parameters of a :class:`~.root.Autopilot_Type`
    """

    def __init__(self, model: Union[Type[Autopilot_Type], Type[BaseModel]], **kwargs):
        super(Model_Filler, self).__init__(**kwargs)
        self.model = model # type: Union[Type[Autopilot_Type], Type[BaseModel]]

        self.label = QtWidgets.QLabel(self.model.__name__)
        self.layout = QtWidgets.QFormLayout()
        self.layout.addRow(self.label, QtWidgets.QLabel(''))
        self.setLayout(self.layout)

        self._inputs = {}

        self._make_fields()

    def _make_fields(self):
        for key, field in self.model.__fields__.items():
            optional = not field.required

            type_ = field.type_
            # handle special cases
            if type_ in _INPUT_MAP.keys():
                widget = _INPUT_MAP[type_].make()
            elif type_.__origin__ == Union:
                widget = self._resolve_union(type_)
            elif type_.__origin__ == Optional:
                optional = True
                widget = self._resolve_union(type_)
            elif type_.__origin__ == typing.Literal:
                widget = _INPUT_MAP[typing.Literal].make()
                widget.addItems(type_.__args__)
                if field.default:
                    idx = widget.findText(field.default)
                    widget.setCurrentIndex(idx)
            else:
                widget = QtWidgets.QLineEdit()

            # Make the label using the schema titel and description
            title = self.schema()['properties'][key]['title']

            if optional:
                title += " (Optional)"

            description = self.schema()['properties'][key]['description']
            label = QtWidgets.QLabel(title)
            label.setToolTip(description)

            # save and add to layout
            self._inputs[key] = widget
            self.layout.addRow(label,  widget)

    def _resolve_union(self, type_) -> QtWidgets.QWidget:
        subtypes = [t for t in type_.__args__ if t in _INPUT_MAP.keys()]
        # sort by permissiveness
        widgets = [_INPUT_MAP[t] for t in subtypes]
        widgets.sort(key=lambda x: x.permissiveness)
        widget = widgets[-1].make()
        return widget

    def value(self) -> Union[Autopilot_Type, BaseModel]:
        """
        Retrieve the values!

        Returns:

        """
        kwargs = {}
        for key, widget in self._inputs.items():
            if isinstance(widget, QtWidgets.QLineEdit):
                value = widget.text()
            elif isinstance(widget, QtWidgets.QCheckBox):
                value = widget.isChecked()
            elif isinstance(widget, QtWidgets.QComboBox):
                value = widget.currentText()
            elif isinstance(widget, QtWidgets.QDateTimeEdit):
                value = widget.dateTime().toPython()
            else:
                raise ValueError(f"Dont know how to handle widget type {widget}")

            kwargs[key] = value

        return self.model(**kwargs)
            







