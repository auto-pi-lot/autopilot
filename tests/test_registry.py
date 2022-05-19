import pytest
import inspect

import logging

import autopilot
from autopilot.utils import registry
from autopilot.utils.loggers import init_logger
from autopilot.hardware import Hardware
from autopilot.hardware.gpio import GPIO

_EXPECTED_HARDWARE = (
 "autopilot.hardware.cameras.Camera",
 "autopilot.hardware.cameras.Camera_CV",
 "autopilot.hardware.cameras.Camera_Spinnaker",
 "autopilot.hardware.gpio.Digital_In",
 "autopilot.hardware.gpio.Digital_Out",
 "autopilot.hardware.gpio.GPIO",
 "autopilot.hardware.gpio.LED_RGB",
 "autopilot.hardware.gpio.PWM",
 "autopilot.hardware.gpio.Solenoid",
 "autopilot.hardware.i2c.I2C_9DOF",
 "autopilot.hardware.i2c.MLX90640",
 "autopilot.hardware.usb.Scale",
 "autopilot.hardware.usb.Wheel"
)
"""A list of all the hardware we expect to have at the moment.

This doesn't need to be maintained *exactly*, but is just used as an
independent source of expectation for which Hardware objects we can expect.

So in all tests that use it, this tests a **minimal** expectation, ie. that we get all
the values that we should get if this were up to date, knowing that it might not be."""

@pytest.fixture
def logger_registry_get(caplog):
    logger = init_logger(module_name='registry', class_name='get')
    caplog.set_level(logging.DEBUG, logger='registry.get')
    return logger


@pytest.mark.parametrize(
    "base_class,class_name",
    [
        ('hardware', 'PWM'),
        ('task', 'Nafc'),
        (registry.REGISTRIES.HARDWARE, 'LED_RGB'),
        (registry.REGISTRIES.TASK, 'Free_Water'),
        (Hardware, 'Digital_In')
    ])
def test_get_one(base_class, class_name):
    """
    Get one autopilot object with a specified base class and class name using a string,
    an enum in :ref:`autopilot.utils.registry.REGISTRIES`, or an object itself
    """
    got_class = autopilot.get(base_class, class_name)
    assert inspect.isclass(got_class)
    assert got_class.__name__ == class_name

@pytest.mark.parametrize("base_class",['hardware','task',*registry.REGISTRIES])
def test_get_all(base_class):
    """
    Test that calling ``get`` with no ``class_name`` argument returns all the objects for that registry
    """
    # test that we get them
    got_classes = autopilot.get(base_class)
    assert isinstance(got_classes, list)
    assert len(got_classes)>1

    # then for the manually specified ones, test if we have the minimum classes we expect
    if isinstance(base_class, str) and base_class == 'hardware':
        class_names = ['.'.join([cls.__module__, cls.__name__]) for cls in got_classes]
        assert all([expected in class_names for expected in _EXPECTED_HARDWARE])
        assert all([issubclass(cls, Hardware) or cls is Hardware for cls in got_classes])\

def test_get_subtree(logger_registry_get, caplog):
    """
    Test that calling ``get`` with a child of a top-level object (eg ``GPIO`` rather than ``Hardware``)
    gets all its children, (using GPIO as the test case)
    """
    minimum_expected = [cls for cls in _EXPECTED_HARDWARE if 'hardware.gpio' in cls]

    # assert we haven't gotten any warnings yet
    assert all([record.levelname != "WARNING" for record in caplog.records])
    gpio_subclasses = autopilot.get('autopilot.hardware.gpio.GPIO', include_base=True)
    # we should be warned about doing this because it's in a very generic 'else' clause for now
    # pdb.set_trace()
    # assert sum([record.levelname == "WARNING" for record in caplog.records]) == 1
    # assert any(['Attempting to get subclasses' in record.getMessage() for record in caplog.records])

    # then test that we actually got them
    got_names = ['.'.join([cls.__module__, cls.__name__]) for cls in gpio_subclasses]

    assert all([testcls in got_names for testcls in minimum_expected])
    assert all([('hardware.gpio' in clsname) or ('autopilot.plugins' in clsname) for clsname in got_names])
    for got_cls in gpio_subclasses:
        assert issubclass(got_cls, GPIO) or got_cls is GPIO
        



def test_get_hardware():
    """
    use the :func:`autopilot.utils.registry.get_hardware` alias

    mostly a formality to keep it working since the underlying function is tested elsewhere
    """
    got_class = autopilot.get_hardware('GPIO')
    assert got_class is GPIO

def test_get_task():
    """
    use the :func:`autopilot.utils.registry.get_task` alias

    mostly a formality to keep it working since the underlying function is tested elsewhere
    """
    got_class = autopilot.get_task('Nafc')
    assert inspect.isclass(got_class)
    assert got_class.__name__ == "Nafc"

def test_get_equivalence():
    """
    Test that the same object is gotten regardless of method of specifying base_class
    """
    with_object = autopilot.get(Hardware, 'Digital_In')
    with_str = autopilot.get('hardware', 'Digital_In')
    with_enum = autopilot.get(registry.REGISTRIES.HARDWARE, 'Digital_In')

    assert with_object is with_str
    assert with_str is with_enum

def test_except_on_failure():
    """
    Ensure a exceptions are raised for nonsense
    """
    with pytest.raises(ImportError):
        autopilot.get('plausible.but.fake.module')

    with pytest.raises(ValueError):
        autopilot.get('IMPLAUSIBLE AND FAKE MODULEGgasregiluh')

    with pytest.raises(ValueError):
        autopilot.get('hardware', 'Real_Base_Class_But_Fake_But_Plausible_Class_Name')

    with pytest.raises(ValueError):
        autopilot.get('task', 'Real_Base_Class_But implwaug0219048iuhl')



