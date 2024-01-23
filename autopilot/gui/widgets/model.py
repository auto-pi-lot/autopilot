"""
Widget to fill fields for a pydantic model
"""
from typing import Union, List, Optional, Tuple, Type, Dict, Literal
from pprint import pformat

from pydantic import BaseModel
from pydantic.fields import ModelField
from pydantic.error_wrappers import ValidationError
from pydantic.main import ModelMetaclass

from PySide6 import QtWidgets

from autopilot.gui.widgets.input import Input
from autopilot.root import Autopilot_Type
from autopilot.gui.dialog import pop_dialog
from autopilot.utils.loggers import init_logger
from autopilot.data.interfaces.base import resolve_type


class ModelWidget(QtWidgets.QWidget):
    """
    Recursive collection of all inputs for a given model.

    Each attribute that has a single :class:`.Input` (eg. a single number, string, and so on)
    that can be resolved by :func:`~.interfaces.base.resolve_type` is represented
    by a :class:`.Model_Input`.

    Otherwise, attributes that are themselves other models are recursively added
    additional :class:`.ModelWidget` s.

    When a model's field is :class:`typing.Optional`, passed as :attr:`.ModelWidget.optional` ,
    The groupbox for the model has a checkbox. When it is unchecked,
    the model fields are inactive and it is returned by :meth:`.ModelWidget.value` as ``None``.
    (Shouldn't be used with a top-level model.)
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

        self.logger = init_logger(self)

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
        self.inputs: Dict[str, Union[Input, 'ModelWidget']] = self._make_fields()

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

        # if our value is set with non-empty values, checked should be true
        if self.optional:
            self.checked = any([val not in (None, '', {}, []) for val in dict_.values()])


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
        if not self.checked:
            return None

        for key, input in self.inputs.items():
            try:
                if isinstance(input, (ModelWidget, ListModelWidget)):
                    kwargs[key] = input.dict()
                else:
                    kwargs[key] = input.value()
            except Exception as e:
                self.logger.exception(f"Could not parse field '{key}' with input type {type(input)}")
                raise e

        return kwargs

    @property
    def checked(self) -> bool:
        """
        If ``self.optional``, whether or not this widget is checked/enabled.

        If not ``self.optional``, returns ``True`` (since it is required, it is always enabled)

        Returns:
            bool
        """
        if not self.optional or not self.container.isCheckable():
            return True

        return self.container.isChecked()

    @checked.setter
    def checked(self, checked: bool):
        if not self.optional or not self.container.isCheckable():
            # give a warning, but otherwise don't do anything.
            self.logger.warning(f"Attempted to set checked on a model that is not optional. Doing nothing (since checked is logically required to be true for required models)")
        else:
            self.container.setChecked(checked)

    def _make_container(self, model) -> (QtWidgets.QGroupBox, QtWidgets.QVBoxLayout):
        container = QtWidgets.QGroupBox(model.__name__)
        layout = QtWidgets.QVBoxLayout()
        container.setLayout(layout)

        if self.optional:
            container.setCheckable(True)
            container.setChecked(False)

        return container, layout

    def _make_fields(self) -> Dict[str, Union[Input, 'ModelWidget']]:
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
    Container class to make lists of :class:`.ModelWidget` s for when a field is a ``List``
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
                probably be ``False`` for child models
            **kwargs:

        Attributes:
            model_layout (:class:`~PySide6.QtWidgets.QVBoxLayout`): Layout containing model widgets
            add_button (:class:`~PySide6.QtWidgets.QPushButton`): Button pressed to add new models
            remove_button (:class:`~PySide6.QtWidgets.QPushButton`): Button pressed to remove the bottom-most model
        """

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
        """A list of instantiated models"""
        return [m.value() for m in self.model_widgets]

    def add_model(self, checked:bool=False, model:Optional[BaseModel]=None):
        """
        When the :attr:`.add_button` is pressed, add an additional :class:`.ModelWidget`

        Args:
            checked (bool): Whether the button is checked (from the ``clicked`` signal)
            model (:class:`pydantic.BaseModel`): Manually override the model to construct.
                (default is to use the ``.model`` attribute)
        """
        if model is None:
            model = self.model
        widget = ModelWidget(model=model, scroll=False)
        self.model_widgets.append(widget)
        self.model_layout.addWidget(widget)

    def remove_model(self, checked:bool=False):
        """
        When the :attr:`.remove_button` is pressed, remove the last-added :class:`.ModelWidget`

        Args:
            checked (bool): Whether the button is checked (from the ``clicked`` signal)
        """
        w = self.model_layout.takeAt(len(self.model_widgets)-1)
        w.widget().deleteLater()
        self.model_widgets = self.model_widgets[:-1]


    def setValue(self, value: List[BaseModel]):
        """
        Create and set values for a list of instantiated data models.

        First clears any existing models that have been made.

        Args:
            value (list[BaseModel]): List of instantiated base models.
        """
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
    Dialogue wrapper around :class:`.ModelWidget`
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














