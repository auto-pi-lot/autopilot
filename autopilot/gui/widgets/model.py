"""
Widget to fill fields for a pydantic model
"""
import typing
from typing import Union, List, Optional, Tuple, Type, Dict, ClassVar
from abc import ABC, abstractmethod
from pprint import pformat
from datetime import datetime

from ast import literal_eval

from pydantic import BaseModel, Field, PrivateAttr
from pydantic.fields import ModelField
from pydantic.error_wrappers import ValidationError
from pydantic.main import ModelMetaclass

from PySide2 import QtWidgets, QtGui

from autopilot.root import Autopilot_Type
from autopilot.gui.dialog import pop_dialog
from autopilot.utils.loggers import init_logger
from autopilot.data.interfaces.base import resolve_type




class Input(BaseModel, ABC):
    """
    Metaclass to parametrically spawn a Qt Input widget for a given type.

    Primarily for the purpose of making a unified widget creation and value retreival syntax within the :class:`ModelWidget` class
    """
    # class variables set by subtypes
    widget: ClassVar[Type[QtWidgets.QWidget]]
    """The widget that is made with the :meth:`.make` method"""
    validator: ClassVar[Optional[Type[QtGui.QValidator]]] = None
    """The validator applied to the input widget"""
    method_calls: ClassVar[Optional[List[Tuple[str, typing.List]]]] = None
    """Names of methods to call after instantiation, passed as a tuple of (method_name, [method_args])"""
    python_type: Type
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

    @classmethod
    def from_type(cls, type_:typing.Type) -> 'Input':
        # TODO: Use @overload to make from_types for all subtypes.
        # TODO2: No, actually just make a class attirbute with the return type
        # and return that????? https://stackoverflow.com/questions/58089300/python-how-to-override-type-hint-on-an-instance-attribute-in-a-subclass
        pass

    @abstractmethod
    def setValue(self, value:typing.Any):
        """
        Set a value in the created widget
        """

    @abstractmethod
    def value(self) -> typing.Any:
        """Retreive the value from the widget!"""

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

class BoolInput(Input):
    widget = QtWidgets.QCheckBox
    python_type = bool

class IntInput(Input):
    widget=QtWidgets.QLineEdit
    validator = QtGui.QIntValidator,
    permissiveness = 1,
    python_type = int

class FloatInput(Input):
    widget = QtWidgets.QLineEdit,
    validator = QtGui.QIntValidator,
    permissiveness = 2,
    python_type = float

class StrInput(Input):
    widget = QtWidgets.QLineEdit,
    permissiveness = 3,
    python_type = str

class DatetimeInput(Input):
    widget = QtWidgets.QDateTimeEdit,
    method_calls = [('setCalendarPopup', [True])],
    python_type = datetime

class ListInput(Input):
    widget = QtWidgets.QLineEdit
    python_type = list

class LiteralInput(Input):
    widget = QtWidgets.QComboBox
    python_type = typing.Literal

_INPUT_MAP = {
    bool: Input(
        widget=QtWidgets.QCheckBox,
        python_type=bool),
    int:  Input(
        widget=QtWidgets.QLineEdit,
        validator=QtGui.QIntValidator,
        permissiveness=1,
        python_type=int),
    float: Input(
        widget=QtWidgets.QLineEdit,
        validator=QtGui.QIntValidator,
        permissiveness=2,
        python_type=float),
    str: Input(
        widget=QtWidgets.QLineEdit,
        permissiveness=3,
        python_type=str),
    datetime: Input(
        widget=QtWidgets.QDateTimeEdit,
        method_calls=[('setCalendarPopup', [True])],
        python_type=datetime
    ),
    list: Input(
        widget=QtWidgets.QLineEdit,

    ),
    typing.Literal: Input(widget=QtWidgets.QComboBox)
}


class ModelWidget(QtWidgets.QWidget):
    """
    Recursive collection of all inputs for a given model.

    Each attribute that has a single input (eg. a single number, string, and so on)
    that can be resolved by :func:`~.interfaces.base.resolve_type` is represented
    by a :class:`.Model_Input`.

    Otherwise, attributes that are themselves other models are recursively added
    additional :class:`.ModelWidget`s.

    Each ``ModelWidget`` has a few meta-options that correspond to special python types:

    * :class:`typing.Optional` - :attr:`.Model_Form.optional` - The groupbox for the model has
      a checkbox. WHen it is unchecked, the model fields are inactive and it is returned by :meth:`.value` as ``None``.
      Cannot be used with a top-level model.
    * :class:`typing.List` - :attr:`.Model_Form.list` - The widget can return multiple entries of itself in a list.
    """

    def __init__(self, model:Union[BaseModel, Type[BaseModel]],optional:bool=False, list:bool=False, parent=None):
        """

        Args:
            model (:class:`pydantic.BaseModel`): The model to represent. Can either be a model class or an instantiated
                model. If an instantiated model, the fields are filled with the current values.
            optional:
            list:
            parent:
        """

        self.optional = False
        self.parent = None
        self.inputs: Dict[str, Input] = {}

    def setValue(self, model):
        """Set all values of the form given an instantiated.

        To set values of individual inputs, use :meth:`Input.setValue`
        """
        pass

    def value(self):
        pass




class Model_Filler(QtWidgets.QWidget):
    """
    A widget to fill the parameters of a :class:`~.root.Autopilot_Type`
    """

    def __init__(self, model: Union[Type[Autopilot_Type], Type[BaseModel]], **kwargs):
        super(Model_Filler, self).__init__(**kwargs)
        self.model = model # type: Union[Type[Autopilot_Type], Type[BaseModel]]

        self.label = QtWidgets.QLabel(self.model.__name__)
        self.layout = QtWidgets.QVBoxLayout()
        self.layout.addWidget(self.label)
        self.setLayout(self.layout)

        self._inputs = {}

        self._inputs, container = self._make_fields(self.model)
        self.layout.addWidget(container)

    def value(self, make:bool=True) -> Union[dict, Autopilot_Type, BaseModel]:
        """
        Attempt to retrieve an instance of the model given the input in the widget

        Args:
            make (bool): If ``True``, default, try to instantiate the model. Otherwise return a
                dict of the values

        Returns:

        """
        value = self._value(self._inputs)
        if make:
            value = self.model(**value)
        return value

    def _make_fields(self, model: Type[Union[BaseModel, Autopilot_Type]]) -> Tuple[dict, QtWidgets.QGroupBox]:
        # make container
        container = QtWidgets.QGroupBox(model.__name__)
        layout = QtWidgets.QVBoxLayout()
        container.setLayout(layout)
        inputs = {}

        for key, field in model.__fields__.items():

            if issubclass(field.type_.__class__, ModelMetaclass):
                # handle nested models recursively
                subinputs, subcontainer = self._make_fields(field.type_)
                inputs[key] = subinputs
                if not field.required:
                    # make optional, selectable by check!
                    subcontainer.setCheckable(True)
                    subcontainer.setChecked(False)
                layout.addWidget(subcontainer)

            else:
                widget = self._make_field(field)
                label = self._make_label(field, model)
                # save and add to layout
                horiz_layout = QtWidgets.QHBoxLayout()
                horiz_layout.addWidget(label)
                horiz_layout.addWidget(widget)
                inputs[key] = widget
                layout.addLayout(horiz_layout)

        return inputs, container

    def _make_field(self, field: ModelField) -> QtWidgets.QWidget:
        """
        Given a model field, make an input widget!

        Args:
            field ():

        Returns:

        """
        # type_ = self._resolve_type(field.type_)
        type_ = resolve_type(field.type_)

        # handle special cases
        if type_ in _INPUT_MAP.keys():
            widget = _INPUT_MAP[type_].make()
        elif hasattr(type_, '__origin__') and type_.__origin__ == typing.Literal:
            widget = _INPUT_MAP[typing.Literal].make()
            widget.addItems(type_.__args__)
            if field.default:
                idx = widget.findText(field.default)
                widget.setCurrentIndex(idx)
        else:
            widget = QtWidgets.QLineEdit()

        return widget


    def _make_label(self, field:ModelField, model:Type[BaseModel]) -> QtWidgets.QLabel:
        """
        Given a model field key, make a label widget with a tooltip!
        """
        optional = not field.required

        # Make the label using the schema titel and description
        title = model.schema()['properties'][field.name]['title']

        if optional:
            title += " (Optional)"

        description = model.schema()['properties'][field.name]['description']
        label = QtWidgets.QLabel(title)
        label.setToolTip(description)
        return label

    def _resolve_type(self, type_) -> typing.Type:
        """
        Get the "inner" type of a model field, sans Optionals and Unions and the like
        """
        if not hasattr(type_, '__args__') or (hasattr(type_, '__origin__') and type_.__origin__ == typing.Literal):
            # already resolved
            return type_

        subtypes = [t for t in type_.__args__ if t in _INPUT_MAP.keys()]
        if len(subtypes) == 0:
            raise ValueError(f'Dont know how to make widget for {type_}')

        # sort by permissiveness
        widgets = [(t, _INPUT_MAP[t]) for t in subtypes]
        widgets.sort(key=lambda x: x[1].permissiveness)
        return widgets[-1][0]

    def _value(self, inputs:Dict[str, QtWidgets.QWidget]) -> dict:
        """
        Retrieve a dictionary of the values!
        """
        kwargs = {}
        for key, widget in inputs.items():
            if isinstance(widget, QtWidgets.QLineEdit):
                value = widget.text()
            elif isinstance(widget, QtWidgets.QCheckBox):
                value = widget.isChecked()
            elif isinstance(widget, QtWidgets.QComboBox):
                value = widget.currentText()
            elif isinstance(widget, QtWidgets.QDateTimeEdit):
                value = widget.dateTime().toPython()
            elif isinstance(widget, dict):
                value = self._value(widget)
            else:
                raise ValueError(f"Dont know how to handle widget type {widget}")

            # filter values from unchecked groupboxes
            if not isinstance(widget, dict):
                if widget.parent().isCheckable() and not widget.parent().isChecked():
                    continue
            else:
                if len(value) == 0:
                    continue

            # try to do a literal value in case we are trying to enter dicts or lists as strings
            try:
                value = literal_eval(value)
            except (ValueError, SyntaxError):
                # no problem, doing it speculatively anyway
                pass

            kwargs[key] = value

        return kwargs

    def validate(self, kwargs:Optional[dict] = None, dialog:bool=False) -> Union[List[dict], Autopilot_Type, BaseModel]:
        """
        Test whether the given inputs pass model validation, and if not return which fail

        Args:
            dialog (bool): Whether or not to pop a dialogue showing which fields failed to validate
        """
        if kwargs is None:
            kwargs = self._value(self._inputs)

        try:
            instance = self.model(**kwargs)
            return instance
        except ValidationError as e:
            # get errors and return!
            errors = e.errors()
            if dialog:
                pop_dialog("Validation Error!",
                           details=f"Validation errors with the following fields:\n{pformat(errors)}",
                           msg_type='error', modality='modal').exec_()

            return errors


class Model_Filler_Dialogue(QtWidgets.QDialog):
    """
    Dialogue wrapper around :class:`.Model_Filler`
    """
    def __init__(self, model: Union[Type[Autopilot_Type], Type[BaseModel]], **kwargs):
        super(Model_Filler_Dialogue, self).__init__(**kwargs)
        self.model = model
        self.filler = Model_Filler(model)
        self.logger = init_logger(self)

        self.value = None

        buttonBox = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        buttonBox.accepted.connect(self._accept)
        buttonBox.rejected.connect(self.reject)

        mainLayout = QtWidgets.QVBoxLayout()
        mainLayout.addWidget(self.filler)
        mainLayout.addWidget(buttonBox)
        self.setLayout(mainLayout)

    def _accept(self):
        """
        Pre-wrapper before :meth:`.accept`, check that the model validates. If not, raise error dialogue
        """
        self.logger.debug('Clicked OK button')
        model = self.filler.validate()
        if isinstance(model, self.model):
            self.value = model
            self.accept()
            self.logger.debug("Accepted model input")
        else:
            pop_dialog("Validation Error!",
                       details=f"Validation errors with the following fields:\n{model}",
                       msg_type='error')














