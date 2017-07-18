#!/usr/bin/env python

'''
This script defines the names of inputs and outputs, the type of state
machine and sound server, the data directories, and other parameters.

*This file is a template, do not modify it.* Make a copy of this file
and name it 'rigsettings.py'. Modify this new file to define the
appropriate settings for the rig.

'''

__version__ = '0.2'
__author__ = 'Santiago Jaramillo <sjara@uoregon.edu>'
__created__ = '2013-03-18'


#: Type of state machine. Either 'arduino_due' or 'dummy'
#STATE_MACHINE_TYPE = 'arduino_due'
#STATE_MACHINE_TYPE = 'dummy'
STATE_MACHINE_TYPE = 'emulator'

#: Serial port for the state machine.
STATE_MACHINE_PORT = '/dev/ttyACM0'

#: Parameters for triggering sounds.
SOUND_TRIGGER_PORT = '/dev/ttyACM1'

#: File that defines the calibration of speakers
SPEAKER_CALIBRATION = None
#SPEAKER_CALIBRATION = '/home/jarauser/src/taskontrol/settings/speaker_calibration.h5'

#: Computer volume level [0-100%]
SOUND_VOLUME_LEVEL = 82

DATA_DIR = '/var/tmp/data/'
REMOTE_DIR = '/mnt/jarahubdata/'

DEFAULT_PARAMSFILE = './params.py'

#: Name for each input line.
# -- The following must match the state machine settings --
INPUTS = {
    'C'  :0,
    'L'  :1,
    'R'  :2,
}

#: Name for each output line.
OUTPUTS = {
    'centerWater':0,
    'centerLED'  :1,
    'leftWater'  :2,
    'leftLED'    :3,
    'rightWater' :4,
    'rightLED'   :5,
    'stim1'      :6,
    'stim2'      :7,
}

