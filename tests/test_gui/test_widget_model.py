
import pytest
from pytestqt import qt_compat
from pytestqt.qt_compat import qt_api

from typing import Union, List, Optional, Literal

import pdb
from pydantic import BaseModel
from pydantic.main import ModelMetaclass

from autopilot.gui.widgets.model import ModelWidget, ListModelWidget
from ..fixtures import dummy_biography
from autopilot.data.models.biography import Biography

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
