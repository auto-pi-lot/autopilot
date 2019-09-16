from autopilot import prefs

from autopilot.stim.managers import Stim_Manager, Proportional, init_manager

if prefs.AGENT == "pilot":
    if prefs.CONFIG == "AUDIO":
        from autopilot.stim.sound import sounds
