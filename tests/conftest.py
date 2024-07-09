import pytest
import os

@pytest.fixture(scope='session', autouse=True)
def monkeypatch_cpuinfo(monkeypatch):
    # only patch on github actions
    if "CI" not in os.environ or not os.environ["CI"] or "GITHUB_RUN_ID" not in os.environ:
        return

    def patched_cpuinfo() -> dict:
        return {}

    import cpuinfo
    monkeypatch.setattr(cpuinfo, 'get_cpu_info', patched_cpuinfo)

    import blosc2.core
    monkeypatch.setattr(blosc2.core, 'get_cpu_info', patched_cpuinfo)




