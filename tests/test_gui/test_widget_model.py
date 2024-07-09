
import pytest
from pytestqt import qt_compat
from pytestqt.qt_compat import qt_api

from typing import Union, List, Optional, Literal
from datetime import datetime

import pdb
from pydantic import BaseModel
from pydantic.main import ModelMetaclass

from autopilot.gui.widgets.model import ModelWidget, ListModelWidget
from ..fixtures import dummy_biography
from autopilot.data.models.biography import Biography

from autopilot.gui.widgets.input import Input, \
    BoolInput, IntInput, FloatInput, StrInput, \
    DatetimeInput, ListInput, DictInput, LiteralInput

pytestmark = pytest.mark.gui

class InnerModel(BaseModel):
    inner_list: List[int]
    inner_int: int

class DummyModel(BaseModel):
    """Dummy model that has the various special conditions we want to make fields for"""
    list: List[int]
    optional_list: Optional[List[int]]
    list_optional: List[Optional[int]]
    list_model: List[InnerModel]
    list_optional_model: Optional[List[InnerModel]]
    literal: Literal[1,2,3]


def test_make_input(qtbot):

    model_widget = ModelWidget(Biography)

    # check that we have an input widget for every field
    # note: only doing one layer of recursion for now, so more deeply nested models aren't necessarily tested!
    for key, field in Biography.__fields__.items():
        assert key in model_widget.inputs.keys()
        if issubclass(field.type_.__class__, ModelMetaclass):
            assert isinstance(model_widget.inputs[key], (ModelWidget, ListModelWidget))

def test_get_set_input(qtbot, dummy_biography):
    """Test that we can do a roundtrip test getting and setting input from the model filler."""
    model_widget = ModelWidget(dummy_biography)

    values = model_widget.value()
    assert values == dummy_biography

def test_optional_fields(qtbot):
    """
    Test that when optional fields are left blank, the inputs don't choke on them.

    Returns:

    """
    model_widget = ModelWidget(Biography)

    # just fill in ID
    model_widget.inputs['id'].setValue('my_cool_id')

    # Our test is super simple, we're just ensuring no exceptions are thrown and that the ID is set.
    # We don't want to assert any of the other values here because that would be an implicit test
    # of the biography model, rather than the widget.
    # We'll test the specific logic of the input widgets elsewhere.
    values = model_widget.value()
    assert isinstance(values, Biography)
    assert values.id == 'my_cool_id'


# --------------------------------------------------
# Test individual input widgets
# --------------------------------------------------
@pytest.mark.parametrize("input_type,widget",(
    (bool, BoolInput),
    (int, IntInput),
    (float, FloatInput),
    (str, StrInput),
    (datetime, DatetimeInput),
    (list, ListInput),
    (dict, DictInput)
))
def test_get_from_type(input_type, widget):
    """
    Test that the individual input widgets can be gotten from the from_type classmethod
    """
    subclass = Input.from_type(input_type)
    made_widget = subclass().make()
    assert subclass is widget
    assert isinstance(made_widget, subclass.widget)

def test_bool_input():
    """
    .. todo::

        Roundtrip set/get bools

    """
    pass

def test_int_input():
    """
    .. todo::

        Roundtrip set/get ints.
        Test unset is returned as None
        Test range set properly

    """
    pass

def test_float_input():
    """
    .. todo::

        Roundtrip set/get
        test unset returned as none
        test range

    Returns:

    """
    pass

def test_str_input():
    """
    .. todo::

        Roundtrip set/get

    Returns:

    """
    pass

def test_datetime_input():
    pass

def test_list_input():
    """
    .. todo::

        Test empty returned as empty list
        Test raise informative error when malformed

    """
    pass

def test_dict_input():
    """
    .. todo::

        Test empty returne as empty dict
        Test raise informative error when malformed

    """
    pass

def test_literal_input():
    pass
