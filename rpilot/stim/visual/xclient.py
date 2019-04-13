"""
Start and manage an X server to display visual stimuli
"""

WIN = None

from psychopy import visual

def boot_visuals():
    global XCLIENT


