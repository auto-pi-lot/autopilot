from time import sleep
from pathlib import Path
import json

import pytest
from pytestqt import qt_compat
from pytestqt.qt_compat import qt_api

from autopilot.core.terminal import Terminal
from autopilot import prefs


@pytest.fixture
def blank_pilot_db():
    with open(Path(prefs.get('PILOT_DB')), 'w') as dbfile:
        json.dump({"testpilot_1": {
            "ip": "192.168.0.0",
            "subjects": ['subject_1', 'subject_2']
        }}, dbfile)
    return True


@pytest.fixture
def spawn_terminal(qtbot, blank_pilot_db):
    prefs.clear()
    prefs.set('AGENT', 'TERMINAL')
    pilot_db = blank_pilot_db

    app = qt_api.QApplication.instance()
    app.setStyle('GTK+')
    terminal = Terminal()
    qtbot.addWidget(terminal)
    return app, terminal

def test_terminal_launch(qtbot, spawn_terminal):
    app, terminal = spawn_terminal

    sleep(5)

    assert terminal.isVisible()

