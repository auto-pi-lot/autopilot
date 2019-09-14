from rpilot import prefs

from rpilot.stim.managers import Stim_Manager, Proportional, init_manager

if prefs.CONFIG == "AUDIO":
    from rpilot.stim.sound import sounds
