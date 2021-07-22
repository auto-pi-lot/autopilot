import pytest
from pathlib import Path
from autopilot import prefs
from autopilot.utils.registry import get
from tests.fixtures import default_dirs


@pytest.fixture
def hardware_plugin(default_dirs):
    """
    Make a basic plugin that inherits from the Hardware class,
    clean it up on exit

    Returns:
        Path: path to created plugin file
    """
    plugin_dir = Path(prefs.get('PLUGINDIR'))
    hw_fn = plugin_dir / "test_hardware_plugin.py"
    hardware_plugin_test = """
    from autopilot.hardware import Hardware
    
    class Test_Hardware_Plugin(Hardware):
        def __init__(*args, **kwargs):
            name="Test_Hardware_Plugin"
            super(Test_Hardware_Plugin, self).__init__(name=name, *args, **kwargs)
            
    """

    with open(hw_fn, 'w') as hw_file:
        hw_file.write(hardware_plugin_test)

    yield hw_fn

    # cleanup
    hw_fn.unlink()

def test_hardware_plugin(hardware_plugin):
    pass

def test_autoplugin():
    """
    the :func:`autopilot.utils.registry.get` function should automatically load
    plugins if the pref ``AUTOPLUGIN`` is ``True`` and the ``plugins`` argument is True
    """
    pass




