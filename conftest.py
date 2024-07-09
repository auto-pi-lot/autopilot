import pytest
import os
import sys

def on_gh_actions() -> bool:
    return "CI" in os.environ or os.environ["CI"] or "GITHUB_RUN_ID" in os.environ

# patch cpuinfo which doesn't work on github actions
# (and actually isn't needed by blosc2 or pytables, but they
# call it at the module level so their imports fail and we need
# to monkeypatch in this janky way
module = type(sys)('cpuinfo')
module.get_cpu_info = lambda: {}
sys.modules['cpuinfo'] = module

def pytest_collection_modifyitems(config, items):

    skip_gui = pytest.mark.skip('GUI is not working with pyside6 atm')
    for item in items:
        if item.get_closest_marker('gui'):
            item.add_marker(skip_gui)

