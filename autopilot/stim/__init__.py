from autopilot import prefs

from autopilot.stim.stim import Stim
from autopilot.stim.managers import Stim_Manager, Proportional, init_manager


if prefs.get('AGENT') == "pilot":
    if 'AUDIO' in prefs.get('CONFIG'):
        from autopilot.stim.sound import sounds


