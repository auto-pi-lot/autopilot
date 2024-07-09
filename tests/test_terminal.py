from time import sleep
from pathlib import Path
import json

import pytest
from pytestqt import qt_compat
from pytestqt.qt_compat import qt_api

from autopilot.agents.terminal import Terminal
from autopilot import prefs

pytestmark = pytest.mark.gui

@pytest.fixture
def blank_pilot_db():
    pilot_db_fn = Path(prefs.get('PILOT_DB')).with_name('pilot_db_temp.json')
    with open(pilot_db_fn, 'w') as dbfile:
        json.dump({"testpilot_1": {
            "ip": "192.168.0.0",
            "subjects": ['subject_1', 'subject_2']
        }}, dbfile)
    prefs.set('PILOT_DB', str(pilot_db_fn))

    yield str(pilot_db_fn)

    pilot_db_fn.unlink()


@pytest.fixture
def spawn_terminal(qtbot, blank_pilot_db):
    prefs.clear()
    prefs.set('AGENT', 'TERMINAL')
    pilot_db_fn = blank_pilot_db
    prefs.set('PILOT_DB', pilot_db_fn)

    #app = qt_api.QtWidgets.QApplication.instance()
    #qapp.setStyle('GTK+')
    terminal = Terminal()
    qtbot.addWidget(terminal)
    return  terminal

def test_terminal_launch(qtbot, spawn_terminal):
    terminal = spawn_terminal

    sleep(5)

    assert terminal.isVisible()

