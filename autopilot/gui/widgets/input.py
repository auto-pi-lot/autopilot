"""
Widgets for representing input widgets for different types.

The metaclass {class}`.Input` represents the basic structure, which each of the inheriting classes
override. Subclasses can be retrieved and instantiated with the overloaded :meth:`.from_type` method::

    # retrieve the class
    int_input_class = Input.from_type(int)
    # instantiate the class -- some subtypes (see :class:`.LiteralInput` ) need arguments on instantiation.
    int_input = int_input_class()

and can then be used to make and manipulate Qt Widgets::

    # make the literal ``QWidget`` to be used
    widget = int_input.make()
    # get/set the value of the created widget
    value = int_input.value()
    int_input.setValue(value)

This allows the :class:`ModelWidget` class to provide a uniform interface to fill end edit models.

"""

import typing
from abc import ABC, abstractmethod
from ast import literal_eval
from datetime import datetime
from typing import ClassVar, Type, Optional, List, Tuple, Union, overload, Literal

from PySide6 import QtWidgets, QtGui
from PySide6.QtCore import QDateTime, Qt
from pydantic import Field, PrivateAttr

from autopilot.utils.loggers import init_logger


class Input(ABC):
    """
    Metaclass to parametrically spawn a Qt Input widget for a given type.

    Primarily for the purpose of making a unified widget creation and value retreival syntax within the :class:`ModelWidget` class
    """
    # class variables set by subtypes
    widget: ClassVar[Type[QtWidgets.QWidget]] = None
    """The widget that is made with the :meth:`.make` method"""
    validator: ClassVar[Optional[Type[QtGui.QValidator]]] = None
    """The validator applied to the input widget"""
    method_calls: ClassVar[Optional[List[Tuple[str, typing.List]]]] = None
    """Names of methods to call after instantiation, passed as a tuple of (method_name, [method_args])"""
    python_type: ClassVar[Union[Type]]
    """The python type that this input provides interface for"""
    permissiveness: ClassVar[int] = 0
    """
    When a type is annotated with a Union, the more permissive (higher number)
    one will be chosen. Arbitrary units.
    """

    # Instance attributes
    args: Optional[list] = Field(default_factory=list)
    """Args to pass to the widget on creation"""
    kwargs: Optional[dict] = Field(default_factory=dict)
    """Kwargs to pass to the widget on creation"""
    range: Optional[Tuple[Union[int, float], Union[int, float]]] = None
    """Limit numerical types to a specific range"""

    _widget: Optional[QtWidgets.QWidget] = PrivateAttr(None)
    """After creation, keep track of this to be able to get """

    def __init__(self, args:Optional[list]=None,
                 kwargs:Optional[dict]=None,
                 range:Optional[Tuple[Union[int, float], Union[int, float]]]=None,
                 ):
        if args is None:
            args = []
        if kwargs is None:
            kwargs = {}

        self.args = args
        self.kwargs = kwargs
        self.range = range
        self.logger = init_logger(self)

    @overload
    def from_type(cls, type_:Type[bool]) -> Type['BoolInput']: ...

    @overload
    def from_type(cls, type_:Type[int]) -> Type['IntInput']: ...

    @overload
    def from_type(cls, type_:Type[float]) -> Type['FloatInput']: ...

    @overload
    def from_type(cls, type_:Type[str]) -> Type['StrInput']: ...

    @overload
    @classmethod
    def from_type(cls, type_:Type[datetime]) -> Type['DatetimeInput']: ...

    @overload
    def from_type(cls, type_:Type[list]) -> Type['ListInput']: ...

    @classmethod
    def from_type(cls, type_:type) -> Type['Input']:
        """
        Get a subclass of ``Input`` that represents a given type.

        Args:
            type_ (:class:`typing.Type`): The type (eg. ``float``, ``int``) to be represented

        Returns:
            An appropriate ``Input`` subclass

        Raises:
            :class:`ValueError` if either no or more than 1 subclass has been declared for the given type.
        """
        subclass = [c for c in cls.__subclasses__() if c.python_type is type_]
        if len(subclass) == 0:
            raise ValueError(f"No Input widget has been defined for type_ {type_}")
        elif len(subclass) > 1:
            raise ValueError(f"More than one Input subclass defined for type_ {type_}")
        else:
            return subclass[0]

    @abstractmethod
    def setValue(self, value:typing.Any):
        """
        Set a value in the created widget

        After the :meth:`Input.make` method is called, returning a widget, the Input instance will
        store a reference to it. This method then allows its value to be set, doing appropriate
        type conversions and invoking the correct methods.
        """

    @abstractmethod
    def value(self) -> typing.Any:
        """
        Retrieve the value from the widget!

        After the :meth:`Input.make` method is called, returning a widget, the Input instance will
        store a reference to it. This method then returns the value, doing appropriate type conversion.
        """

    def make(self,
             widget_kwargs:Optional[dict]=None,
             validator_kwargs:Optional[dict]=None) -> QtWidgets.QWidget:
        """
        Make the appropriate widget for this input.

        Stores the made widget in the private :attr:`._widget` attr, which is then used
        in subsequent :meth:`.Input.value` and :meth:`.Input.setValue` calls.

        Args:
            widget_kwargs (dict): Optional: kwargs given to the widget on instantiation
            validator_kwargs (dict): Optional: kwargs given to the validator on instantiation

        Returns:
            :class:`PySide6.QtWidgets.QWidget`: Subclass of QWidget according to Input type
        """
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

        self._widget = widget

        return widget

    # class Config:
    #     arbitrary_types_allowed = True


class BoolInput(Input):
    widget = QtWidgets.QCheckBox
    python_type = bool
    _widget: QtWidgets.QCheckBox

    def setValue(self, value:bool):
        self._widget.setChecked(value)

    def value(self) -> bool:
        return self._widget.isChecked()


class IntInput(Input):
    widget=QtWidgets.QLineEdit
    validator = QtGui.QIntValidator
    permissiveness = 1
    python_type = int
    _widget: QtWidgets.QLineEdit

    def setValue(self, value:int):
        self._widget.setText(str(value))

    def value(self) -> Optional[int]:
        if self._widget.text() == '':
            return None
        else:
            return int(self._widget.text())


class FloatInput(Input):
    widget = QtWidgets.QLineEdit
    validator = QtGui.QIntValidator
    permissiveness = 2,
    python_type = float
    _widget: QtWidgets.QLineEdit

    def setValue(self, value: float):
        self._widget.setText(str(value))

    def value(self) -> Optional[float]:
        if self._widget.text() == '':
            return None
        else:
            return float(self._widget.text())


class StrInput(Input):
    widget = QtWidgets.QLineEdit
    permissiveness = 3
    python_type = str
    _widget: QtWidgets.QLineEdit

    def setValue(self, value: str):
        self._widget.setText(str(value))

    def value(self) -> str:
        return str(self._widget.text())


class DatetimeInput(Input):
    widget = QtWidgets.QDateTimeEdit
    method_calls = [('setCalendarPopup', [True])]
    python_type = datetime
    _widget: QtWidgets.QDateTimeEdit

    def setValue(self, value:datetime):
        dt = QDateTime.fromString(value.isoformat(), Qt.ISODate)
        self._widget.setDateTime(dt)

    def value(self) -> datetime:
        return self._widget.dateTime().toPython()


class ListInput(Input):
    widget = QtWidgets.QLineEdit
    python_type = list
    _widget: QtWidgets.QLineEdit

    def setValue(self, value: list):
        self._widget.setText(str(value))

    def value(self) -> list:
        if self._widget.text() == '':
            return []
        else:
            try:
                val = literal_eval(self._widget.text())
                return val
            except ValueError as e:
                self.logger.exception(f"Expected input to be list-like, eg '[1,2,3]', but instead got input: \n{self._widget.text()}")
                raise e


class DictInput(Input):
    widget = QtWidgets.QLineEdit
    python_type = dict
    _widget: QtWidgets.QLineEdit

    def setValue(self, value: dict):
        self._widget.setText(str(value))

    def value(self) -> dict:
        if self._widget.text() == '':
            return {}
        else:
            try:
                val = literal_eval(self._widget.text())
                return val
            except ValueError as e:
                self.logger.exception(f"Expected input to be dict-like, eg \"{{'key': 'val', 'key2': 'val2'}}\", but instead got input: \n{self._widget.text()}")
                raise e


class LiteralInput(Input):
    widget = QtWidgets.QComboBox
    python_type: ClassVar[Type] = typing.Literal
    choices: list
    """Args are not optional for literal input types"""
    default: Optional[typing.Any] = None
    """
    If one of the entries in the literal type should be default, 
    set this on widget creation
    """
    _widget: QtWidgets.QComboBox

    def __init__(self, choices:list,default:Optional[typing.Any]=None, **kwargs):
        super(LiteralInput, self).__init__(**kwargs)
        self.choices = choices
        self.default = default

    def make(self, widget_kwargs:Optional[dict]=None,
             validator_kwargs:Optional[dict]=None) -> QtWidgets.QComboBox:
        """
        Call the superclass make method, but then set the options for the combobox based on
        our :attr:`LiteralInput.args` attribute.

        Args:
            widget_kwargs (dict): Optional: kwargs given to the widget on instantiation
            validator_kwargs (dict): Optional: kwargs given to the validator on instantiation

        Returns:
            :class:`PySide6.QtWidgets.QComboBox`
        """
        widget = super(LiteralInput, self).make(widget_kwargs=widget_kwargs, validator_kwargs=validator_kwargs) # type: QtWidgets.QComboBox
        widget.addItems(self.choices)
        if self.default is not None:
            self.setValue(self.default)
        return widget

    def setValue(self, value: typing.Any):
        idx = self._widget.findText(value)
        self._widget.setCurrentIndex(idx)

    def value(self) -> typing.Any:
        return self._widget.currentText()