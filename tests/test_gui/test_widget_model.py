
import pytest
from pytestqt import qt_compat
from pytestqt.qt_compat import qt_api

import pdb
from pydantic.main import ModelMetaclass

from autopilot.gui.widgets.model import Model_Filler
# from ..fixtures import dummy_biography
from autopilot.data.models.biography import Biography

def test_make_input(qtbot):

    model_widget = Model_Filler(Biography)

    # check that we have an input widget for every field
    # note: only doing one layer of recursion for now, so more deeply nested models aren't necessarily tested!
    for key, field in Biography.__fields__.items():
        assert key in model_widget._inputs.keys()
        if issubclass(field.type_.__class__, ModelMetaclass):
            assert isinstance(model_widget._inputs[key], dict)
            for subkey, subfield in field.type_.__fields__.items():
                assert subkey in model_widget._inputs[key].keys()

def test_get_input(qtbot):
    """Test that we can get input from all the fields"""
    model_widget = Model_Filler(Biography)

    values = model_widget.value(make=False)

    # check that we have an input widget for every field
    # note: only doing one layer of recursion for now, so more deeply nested models aren't necessarily tested!
    for key, field in Biography.__fields__.items():
        assert key in values.keys()
        if issubclass(field.type_.__class__, ModelMetaclass):
            assert isinstance(values[key], dict)
            for subkey, subfield in field.type_.__fields__.items():
                assert subkey in values[key].keys()