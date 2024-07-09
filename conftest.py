import pytest
import os
import sys

def on_gh_actions() -> bool:
    return "CI" in os.environ or os.environ["CI"] or "GITHUB_RUN_ID" in os.environ
#
# @pytest.fixture(scope='session', autouse=True)
# def monkeypatch_cpuinfo(monkeypatch):
#     # only patch on github actions
#     # if not on_gh_actions():
#     #     return
#
#     def patched_cpuinfo() -> dict:
#         return {}
#
#     class PatchedModule():
#         get_cpu_info = patched_cpuinfo
#
#     import cpuinfo
#     monkeypatch.setattr(cpuinfo, 'get_cpu_info', patched_cpuinfo)
#
#     import blosc2.core
#     monkeypatch.setattr(blosc2.core, 'get_cpu_info', patched_cpuinfo)
#
#     import tables.leaf
#     monkeypatch.setattr(tables.leaf, 'cpuinfo', PatchedModule)
    #
    # mocker.patch('cpuinfo.get_cpu_info', return_value={})
    # mocker.patch('blosc2.core.get_cpu_info', return_value={})
    # mocker.patch('tables.leaf.cpuinfo.get_cpu_info', return_value={})


# @pytest.fixture(scope='session', autouse=True)
# def do_monkeypatch(mocker):
#     monkeypatch_cpuinfo(mocker)

module = type(sys)('cpuinfo')
module.get_cpu_info = lambda: {}
sys.modules['cpuinfo'] = module




