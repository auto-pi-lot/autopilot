"""
Widget to fill fields for a pydantic model
"""
import typing
from typing import Union, List, Optional, Tuple, Type, Dict, ClassVar, Literal, overload
from abc import ABC, abstractmethod
from pprint import pformat
from datetime import datetime

from ast import literal_eval

from pydantic import BaseModel, Field, PrivateAttr
from pydantic.fields import ModelField
from pydantic.error_wrappers import ValidationError
from pydantic.main import ModelMetaclass

from PySide2 import QtWidgets, QtGui
from PySide2.QtCore import Qt, QDateTime

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

    @overload
    @classmethod
    def from_type(cls, type_:Type[bool]) -> Type['BoolInput']: pass

    @overload
    @classmethod
    def from_type(cls, type_:Type[int]) -> Type['IntInput']: pass

    @overload
    @classmethod
    def from_type(cls, type_:Type[float]) -> Type['FloatInput']: pass

    @overload
    @classmethod
    def from_type(cls, type_:Type[str]) -> Type['StrInput']: pass

    @overload
    @classmethod
    def from_type(cls, type_:Type[datetime]) -> Type['DatetimeInput']: pass

    @overload
    @classmethod
    def from_type(cls, type_:Type[list]) -> Type['ListInput']: pass

    @overload
    @classmethod
    def from_type(cls, type_:type(Literal)) -> Type['LiteralInput']: pass

    @classmethod
    def from_type(cls, type_):
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
        """

    @abstractmethod
    def value(self) -> typing.Any:
        """Retreive the value from the widget!"""

    def make(self,
             widget_kwargs:Optional[dict]=None,
             validator_kwargs:Optional[dict]=None) -> QtWidgets.QWidget:
        """
        Make the appropriate widget for this input.

        Stores the made widget in the private :attr:`._widget` attr, which is then used
        in subsequent :meth:`.value` and :meth:`.setValue` calls.

        Args:
            widget_kwargs (dict): Optional: kwargs given to the widget on instantiation
            validator_kwargs (dict): Optional: kwargs given to the validator on instantiation

        Returns:
            :class:`PySide2.QtWidgets.QWidget`: Subclass of QWidget according to Input type
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

    class Config:
        arbitrary_types_allowed = True


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

    def value(self) -> int:
        return int(self._widget.text())


class FloatInput(Input):
    widget = QtWidgets.QLineEdit
    validator = QtGui.QIntValidator
    permissiveness = 2,
    python_type = float
    _widget: QtWidgets.QLineEdit

    def setValue(self, value: float):
        self._widget.setText(str(value))

    def value(self) -> float:
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
        return literal_eval(self._widget.text())

class DictInput(Input):
    widget = QtWidgets.QLineEdit
    python_type = dict
    _widget: QtWidgets.QLineEdit

    def setValue(self, value: dict):
        self._widget.setText(str(value))

    def value(self) -> dict:
        return literal_eval(self._widget.text())

class LiteralInput(Input):
    widget = QtWidgets.QComboBox
    python_type: ClassVar[type(typing.Literal)] = typing.Literal
    choices: list
    """Args are not optional for literal input types"""
    default: Optional[typing.Any] = None
    """
    If one of the entries in the literal type should be default, 
    set this on widget creation
    """
    _widget: QtWidgets.QComboBox

    def make(self, widget_kwargs:Optional[dict]=None,
             validator_kwargs:Optional[dict]=None) -> QtWidgets.QComboBox:
        """
        Call the superclass make method, but then set the options for the combobox based on
        our :attr:`LiteralInput.args` attribute.

        Args:
            widget_kwargs (dict): Optional: kwargs given to the widget on instantiation
            validator_kwargs (dict): Optional: kwargs given to the validator on instantiation

        Returns:
            :class:`PySide2.QtWidgets.QComboBox`
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
    """

    def __init__(self, model:Union[BaseModel, Type[BaseModel]],
                 optional:bool=False,
                 scroll:bool=True,
                 **kwargs):
        """

        Args:
            model (:class:`pydantic.BaseModel`): The model to represent. Can either be a model class or an instantiated
                model. If an instantiated model, the fields are filled with the current values.
            optional (bool): If ``True``, the enclosing groupbox has a checkbox that when unchecked causes :meth:`ModelWidget.value` to return ``None``.
                If ``False``, :meth:`ModelWidget.value` always attempts to return the model
            scroll (bool): Whether the widget should be within a scrollbar. ``True`` by default, but should
                probably be ``False`` for child models.
            **kwargs: passed to superclass
        """
        super(ModelWidget, self).__init__(**kwargs)

        if isinstance(model, BaseModel):
            # given instantiated model to prefill with
            self._model = model
            self.model = self._model.__class__
        elif isinstance(model, type) and issubclass(model, BaseModel):
            self._model = None
            self.model = model
        else:
            raise ValueError(f"Need either an instantiated model or a model class, got {model}")

        self.optional = optional

        # make an outer layout to contain inner containers for individual model instances
        self._outer_layout = QtWidgets.QVBoxLayout()
        self._outer_layout.setContentsMargins(0,0,0,0)
        self.setLayout(self._outer_layout)

        # make a container for the instance of the model
        self.container, self.layout = self._make_container(self.model)

        # make scrollable
        if scroll:
            scroll = QtWidgets.QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setWidget(self.container)
            self._outer_layout.addWidget(scroll)
        else:
            self._outer_layout.addWidget(self.container)

        # make input widgets
        self.inputs: Dict[str, Union[Input,'ModelWidget']] = self._make_fields()

        if self._model is not None:
            self.setValue(self._model)



    def setValue(self, model: Union[BaseModel, dict]):
        """
        Set all values of the form given an instantiated model.

        To set values of individual inputs, use :meth:`Input.setValue`
        """
        if isinstance(model, dict):
            dict_ = model
        else:
            dict_ = model.dict()

        for key, value in dict_.items():
            self.inputs[key].setValue(value)

    def value(self) -> ['BaseModel', None]:
        """
        Return an instance of the model populated with values from :meth:`.dict`

        If model fails to validate, pop a dialog with the validation errors and return None
        (see :meth:`.validate`)

        Returns:
            :class:`pydantic.BaseModel` of the type specified in :attr:`ModelWidget.model`
        """
        validated = self.validate()
        if isinstance(validated, self.model):
            return validated
        else:
            return None

    def dict(self) -> Union[dict,None]:
        """
        Return a (recursive) dictionary of all current model values.

        Returns:
            dict
            None: if model is optional and unchecked.
        """
        kwargs = {}
        if self.optional and self.container.isChecked():
            return None

        for key, input in self.inputs.items():
            if isinstance(input, (ModelWidget, ListModelWidget)):
                kwargs[key] = input.dict()
            else:
                kwargs[key] = input.value()

        return kwargs


    def _make_container(self, model) -> (QtWidgets.QGroupBox, QtWidgets.QVBoxLayout):
        container = QtWidgets.QGroupBox(model.__name__)
        layout = QtWidgets.QVBoxLayout()
        container.setLayout(layout)

        if self.optional:
            container.setCheckable(True)
            container.setChecked(False)

        return container, layout

    def _make_fields(self) -> Dict[str, Union[Input,'ModelWidget']]:
        """
        Make fields, using :class:`.Input` subclasses to create the widgets and query values
        """
        inputs = {}
        for key, field in self.model.__fields__.items():
            is_list = False

            if hasattr(field, 'outer_type_') and getattr(field.outer_type_, '__origin__', False) is list:
                is_list= True

            if issubclass(field.type_.__class__, ModelMetaclass):
                # handle nested models recursively
                if is_list:
                    widget = ListModelWidget(model=field.type_, optional=not field.required, scroll=False)
                else:
                    widget = ModelWidget(model=field.type_, optional=not field.required,scroll=False)

                inputs[key] = widget
                self.layout.addWidget(widget)

            else:
                input, widget = self._make_field(field)
                inputs[key] = input
                label = self._make_label(field, self.model)
                h_layout = QtWidgets.QHBoxLayout()
                h_layout.addWidget(label)
                h_layout.addWidget(widget)
                self.layout.addLayout(h_layout)

        return inputs


    def _make_field(self, field:ModelField) -> Tuple[Input, QtWidgets.QWidget]:
        type_ = resolve_type(field.type_)

        if hasattr(field, 'outer_type_') and getattr(field.outer_type_, '__origin__', None) is list:
            input_class = Input.from_type(list)
            input = input_class()
        elif hasattr(field, 'outer_type_') and getattr(field.outer_type_, '__origin__', None) is Literal:
            input_class = Input.from_type(Literal)
            choices = field.outer_type_.__args__
            default = field.default
            input = input_class(choices=choices, default=default)
        else:
            input_class = Input.from_type(type_)
            input = input_class()

        widget = input.make()

        return input, widget


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

    def validate(self, kwargs:Optional[dict] = None, dialog:bool=False) -> Union[List[dict], Autopilot_Type, BaseModel]:
        """
        Test whether the given inputs pass model validation, and if not return which fail

        Args:
            dialog (bool): Whether or not to pop a dialogue showing which fields failed to validate
        """
        if kwargs is None:
            kwargs = self.dict()

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



class ListModelWidget(QtWidgets.QWidget):
    """
    Container class to make lists of :class:`.ModelWidget`s
    """

    def __init__(self, model:Union[BaseModel, Type[BaseModel]],
                 optional:bool=False,
                 scroll:bool=True,
                 **kwargs):

        super(ListModelWidget, self).__init__(**kwargs)
        if isinstance(model, BaseModel):
            # given instantiated model to prefill with
            self._model = model
            self.model = self._model.__class__
        elif isinstance(model, type) and issubclass(model, BaseModel):
            self._model = None
            self.model = model

        self.optional = optional


        self.layout = QtWidgets.QVBoxLayout()
        self.setLayout(self.layout)
        self.model_layout = QtWidgets.QVBoxLayout()

        self.container = QtWidgets.QGroupBox(self.model.__name__)
        self.container.setLayout(self.model_layout)


        if scroll:
            scroll = QtWidgets.QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setWidget(self.container)
            self.layout.addWidget(scroll)
        else:
            self.layout.addWidget(self.container)

        if self.optional:
            self.container.setCheckable(True)
            self.container.setChecked(False)

        self.add_button = QtWidgets.QPushButton("+")
        self.remove_button = QtWidgets.QPushButton('-')
        self.add_button.clicked.connect(self.add_model)
        self.remove_button.clicked.connect(self.remove_model)
        hlayout = QtWidgets.QHBoxLayout()
        hlayout.addWidget(self.remove_button)
        hlayout.addWidget(self.add_button)
        self.layout.addLayout(hlayout)

        self.model_widgets = [] # type: List[ModelWidget]
        if not self.optional:
            self.model_widgets.append(ModelWidget(self.model,optional=False))

    def dict(self) -> List[dict]:
        """Sort of a misnomer, but return a list of dictionaries that contain the values to be used in the model"""
        return [m.dict() for m in self.model_widgets]

    def value(self) -> List[BaseModel]:
        return [m.value() for m in self.model_widgets]

    def add_model(self, checked:bool=False, model:Optional[BaseModel]=None):
        if model is None:
            model = self.model
        widget = ModelWidget(model=model, scroll=False)
        self.model_widgets.append(widget)
        self.model_layout.addWidget(widget)

    def remove_model(self, checked:bool=False):
        w = self.model_layout.takeAt(len(self.model_widgets)-1)
        w.widget().deleteLater()
        self.model_widgets = self.model_widgets[:-1]


    def setValue(self, value: List[BaseModel]):
        self._clear_widgets()

        for model in value:
            if isinstance(model, dict):
                model = self.model(**model)
            self.add_model(model=model)

    def _clear_widgets(self):
        while True:
            widget = self.model_layout.takeAt(0)
            if widget is None:
                break
            widget.widget().deleteLater()
        self.model_widgets = []


class Model_Filler_Dialogue(QtWidgets.QDialog):
    """
    Dialogue wrapper around :class:`.Model_Filler`
    """
    def __init__(self, model: Union[Type[Autopilot_Type], Type[BaseModel]], **kwargs):
        super(Model_Filler_Dialogue, self).__init__(**kwargs)
        self.model = model
        self.filler = ModelWidget(model)
        self.logger = init_logger(self)

        self.value = None

        buttonBox = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        buttonBox.accepted.connect(self._accept)
        buttonBox.rejected.connect(self.reject)

        mainLayout = QtWidgets.QVBoxLayout()
        mainLayout.addWidget(scroll)
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














