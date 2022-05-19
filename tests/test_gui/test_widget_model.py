
import pytest
from pytestqt import qt_compat
from pytestqt.qt_compat import qt_api

import pdb
from pydantic.main import ModelMetaclass

from autopilot.gui.widgets.model import Model_Filler
from autopilot.utils.common import flatten_dict
from ..fixtures import dummy_biography
from autopilot.data.models.biography import Biography
from autopilot.data.modeling.base import Data
from PySide2.QtWidgets import QLineEdit, QDateTimeEdit, QComboBox
from PySide2.QtCore import QDateTime, Qt


def fill_model(widget: Model_Filler, model: Data) -> Model_Filler:
    """
    Fill a model widget with values from the model!

    Args:
        widget (:class:`.Model_Filler`): Widget to fille
        model (:class:`.Data`): Model to fill it with!

    Returns:
        The filled widget!
    """
    # hack -- until we handle multiple input on the form, just handle one
    if hasattr(model, 'genotype') and isinstance(model.genotype.genes, list):
        model.genotype.genes = model.genotype.genes[0]

    model_flat = flatten_dict(model.dict(), skip=('tags',))
    widget_flat = flatten_dict(widget._inputs)

    for key, value in model_flat.items():
        try:
            in_widget = widget_flat[key]
        except KeyError:
            pdb.set_trace()
        # enable any disabled groups
        if in_widget.parent().isCheckable() and not in_widget.parent().isChecked():
            in_widget.parent().setChecked(True)

        if isinstance(in_widget, QLineEdit):
            in_widget.setText(str(value))
        elif isinstance(in_widget, QComboBox):
            in_widget.setCurrentText(value)
        elif isinstance(in_widget, QDateTimeEdit):
            dt = QDateTime.fromString(value.isoformat(), Qt.ISODate)
            in_widget.setDateTime(dt)
        else:
            raise NotImplementedError(f"Widget type {in_widget} not implemented")

    return widget


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

def test_get_input(qtbot, dummy_biography):
    """Test that we can get input from all the fields"""
    model_widget = Model_Filler(Biography)

    # fill widget
    model_widget = fill_model(model_widget, dummy_biography)

    values = model_widget.value(make=False)

    # check that we have an input widget for every field
    # note: only doing one layer of recursion for now, so more deeply nested models aren't necessarily tested!
    for key, field in Biography.__fields__.items():
        assert key in values.keys()
        if issubclass(field.type_.__class__, ModelMetaclass):
            assert isinstance(values[key], dict)
            for subkey, subfield in field.type_.__fields__.items():
                assert subkey in values[key].keys()

    assert flatten_dict(dummy_biography.dict()) == flatten_dict(model_widget.value(make=True).dict())