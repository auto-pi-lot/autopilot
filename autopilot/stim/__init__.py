from autopilot import prefs

from autopilot.stim.managers import Stim_Manager, Proportional, init_manager


class Stim(object):
    """
    Placeholder stimulus meta-object until full implementation
    """


if prefs.get('AGENT') == "pilot":
    if 'AUDIO' in prefs.get('CONFIG'):
        from autopilot.stim.sound import sounds


