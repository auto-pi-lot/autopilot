import pytest
import re
from pathlib import Path

from autopilot.setup.setup_autopilot import make_alias

def test_make_alias():
    fake_launch_path = '/some/fake/path.sh'

    def check_profile(profile_file):
        """check if a bash profile has the autopilot alias"""
        with open(profile_file, 'r') as pfile:
            profile = pfile.read()
        return bool(re.search('\n# autopilot alias.*\nalias autopilot.*', profile))

    # find the bash profile as the function does
    bash_profile = None
    if (Path.home() / '.bashrc').exists():
        bash_profile = Path.home() / '.bashrc'
    elif (Path.home() / '.bash_profile').exists():
        bash_profile = Path.home() / '.bash_profile'

    # test automatically discovered profile has the alias (or else raises the expected ValueError)
    if bash_profile is None:
        with pytest.raises(ValueError):
            make_alias(fake_launch_path)
    else:
        make_alias(fake_launch_path)
        assert check_profile(bash_profile)

def test_quiet_mode():
    """
    Autopilot can be setup programmatically by calling setup_autopilot with --quiet and passing
    prefs and scripts manually
    """
    pass
