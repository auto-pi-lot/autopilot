import pytest
import pdb
import inspect
from typing import Tuple
from pathlib import Path
import autopilot
from autopilot import prefs
from autopilot.hardware import Hardware
from autopilot.utils.registry import get
from autopilot.utils.plugins import _IMPORTED
from tests.fixtures import default_dirs


@pytest.fixture
def hardware_plugin(default_dirs) -> Tuple[Path, str]:
    """
    Make a basic plugin that inherits from the Hardware class,
    clean it up on exit

    Returns:
        Path: path to created plugin file
    """
    plugin_dir = Path(prefs.get('PLUGINDIR'))
    prefs.set('AUTOPLUGIN', True)
    hw_fn = plugin_dir / "test_hardware_plugin.py"
    class_name = "Test_Hardware_Plugin"
    hardware_plugin_test = f"""
from autopilot.hardware import Hardware

class {class_name}(Hardware):
    def __init__(self, *args, **kwargs):
        name="Test_Hardware_Plugin"
        super(Test_Hardware_Plugin, self).__init__(name=name, *args, **kwargs)
    
    def im_alive(self):
        return True
        
    def release(self):
        pass
        
    """

    with open(hw_fn, 'w') as hw_file:
        hw_file.write(hardware_plugin_test)
    _IMPORTED.value = False

    yield (hw_fn, class_name)

    # cleanup
    if hw_fn.exists():
        hw_fn.unlink()

def test_hardware_plugin(hardware_plugin):
    """
    A subclass of :class:`autopilot.hardware.Hardware` in the ``PLUGINDIR`` can be
    accessed with :func:`autopilot.get`.

    For example, for the following class declared in some ``.py`` file in the plugin dir::

        from autopilot.hardware import Hardware

        class Test_Hardware_Plugin(Hardware):
            def __init__(self, *args, **kwargs):
                super(Test_Hardware_Plugin, self).__init__(*args, **kwargs)

            def release(self):
                pass

    one would be able to access it throughout autopilot with::

        autopilot.get('hardware', 'Test_Hardware_Plugin')
        # or
        autopilot.get_hardware('Test_Hardware_Plugin')

    """
    hw_path, class_name = hardware_plugin

    assert hw_path.exists()

    plugin_class = autopilot.get('hardware', class_name)

    assert inspect.isclass(plugin_class)
    assert issubclass(plugin_class, Hardware)
    assert plugin_class().im_alive()

def test_autoplugin():
    """
    the :func:`autopilot.utils.registry.get` function should automatically load
    plugins if the pref ``AUTOPLUGIN`` is ``True`` and the ``plugins`` argument is True
    """
    pass




