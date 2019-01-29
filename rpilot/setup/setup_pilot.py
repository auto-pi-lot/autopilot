import npyscreen as nps
from collections import OrderedDict as odict
import pprint
import json
import os
import subprocess

class PilotSetupForm(nps.SplitForm):
    def create(self):
        """

        """
        self.input = odict({
            'NAME': self.add(nps.TitleText, name="Pilot Name:", value=""),
            'BASEDIR': self.add(nps.TitleText, name="Base Directory:", value="/usr/rpilot"),
            'PUSHPORT': self.add(nps.TitleText, name="Push Port - Router port used by the Terminal:", value="5560"),
            'MSGPORT': self.add(nps.TitleText, name="Message Port - Our router port:", value="5565"),
            'TERMINALIP': self.add(nps.TitleText, name="Terminal IP:", value="192.168.0.100"),
            'PINS':{
                'POKES':{
                    'L':self.add(nps.TitleText, name="PINS - POKES - L", value="24"),
                    'C': self.add(nps.TitleText, name="PINS - POKES - C", value="8"),
                    'R': self.add(nps.TitleText, name="PINS - POKES - R", value="10"),
                },
                'LEDS': {
                    'L': self.add(nps.TitleText, name="PINS - LEDS - L", value="[11, 13, 15]"),
                    'C': self.add(nps.TitleText, name="PINS - LEDS - C", value="[22, 18, 16]"),
                    'R': self.add(nps.TitleText, name="PINS - LEDS - R", value="[19, 21, 23]"),
                },
                'PORTS': {
                    'L': self.add(nps.TitleText, name="PINS - PORTS - L", value="31"),
                    'C': self.add(nps.TitleText, name="PINS - PORTS - C", value="33"),
                    'R': self.add(nps.TitleText, name="PINS - PORTS - R", value="37"),
                }},
            'AUDIOSERVER':self.add(nps.TitleSelectOne,max_height=4,value=[0,], name="Audio Server:",
                                   values=["jack", "pyo", "none"], scroll_exit=True),
            'NCHANNELS':self.add(nps.TitleText, name="N Audio Channels", value="1"),
            'FS': self.add(nps.TitleText, name="Audio Sampling Rate", value="192000"),
            'JACKDSTRING': self.add(nps.TitleText, name="Command used to launch jackd - note that \'fs\' will be replaced with above FS",
                                    value="jackd -P75 -p16 -t2000 -dalsa -dhw:sndrpihifiberry -P -rfs -n3 -s &"),
            'PIGPIOMASK': self.add(nps.TitleText, name="Binary mask to enable pigpio to access pins according to the BCM numbering",
                                    value="1111110000111111111111110000"),
            'PULLUPS': self.add(nps.TitleText, name="Pins to pull up on boot",
                                    value="[7]"),
            'PULLDOWNS': self.add(nps.TitleText, name="Pins to pull down on boot",
                                value="[]")


        })
        #self.inName = self.add(nps.)


    # after we're done editing, close the input program
    def afterEditing(self):
        """

        """
        self.parentApp.setNextForm(None)

class SetupApp(nps.NPSAppManaged):
    def onStart(self):
        """

        """
        self.form = self.addForm('MAIN', PilotSetupForm, name='Setup Pilot')

def unfold_values(v):
    """
    Args:
        v:
    """
    if isinstance(v, dict):
        # recurse
        v = {k:unfold_values(v) for k, v in v.items()}
    else:
        try:
            v = int(v.value)
        except:
            v = v.value
    return v

def make_dir(adir):
    """
    Args:
        adir:
    """
    if not os.path.exists(adir):
        os.makedirs(adir)
        os.chmod(adir, 0777)


if __name__ == "__main__":
    # Check for sudo
    if os.getuid() != 0:
        raise Exception("Need to run as root")

    setup = SetupApp()
    setup.run()

    # extract params
    params = {k:unfold_values(v) for k, v in setup.form.input.items()}

    ############################
    # some inelegant manual formatting
    # convert numerical audio server index to string
    params['AUDIOSERVER'] = ['jack', 'pyo', 'none'][params['AUDIOSERVER'][0]]

    # convert string LED pin specifier to list
    for k, v in params['PINS']['LEDS'].items():
        params['PINS']['LEDS'][k] = json.loads(v)

    # replace fs in jackd string
    params['JACKDSTRING'] = params['JACKDSTRING'].replace('fs', str(params['FS']))

    # pigpio should be a string
    params['PIGPIOMASK'] = str(params['PIGPIOMASK'])

    # make the string a dict
    # print(params['PULLPINS'])
    params['PULLUPS'] = json.loads(params['PULLUPS'])
    params['PULLDOWNS'] = json.loads(params['PULLDOWNS'])


    ##############################
    # Compute derived values
    pigpio_string = 'pigpiod -t 0 -x {}'.format(params['PIGPIOMASK'])

    # define and make directory structure
    params['DATADIR'] = os.path.join(params['BASEDIR'], 'data')
    params['SOUNDDIR'] = os.path.join(params['BASEDIR'], 'sounds')
    params['LOGDIR'] = os.path.join(params['BASEDIR'], 'logs')

    for adir in [params['BASEDIR'], params['DATADIR'], params['SOUNDDIR'], params['LOGDIR']]:
        make_dir(adir)

    # Get repo dir
    file_loc = os.path.realpath(__file__)
    file_loc = file_loc.split(os.sep)[:-2]
    params['REPODIR'] = os.path.join(os.sep, *file_loc)

    # save prefs
    prefs_file = os.path.join(params['BASEDIR'], 'prefs.json')
    with open(prefs_file, 'w') as prefs_file_open:
        json.dump(params, prefs_file_open, indent=4, separators=(',', ': '), sort_keys=True)
    os.chmod(prefs_file, 0775)

    print('params saved to {}\n'.format(prefs_file))

    ###############################
    # Install -  create runfile and optionally make service
    launch_file = os.path.join(params['BASEDIR'], 'launch_pilot.sh')
    with open(launch_file, 'w') as launch_file_open:
        launch_file_open.write('#!/bin/sh\n')
        launch_file_open.write('killall jackd\n')  # Try to kill any existing jackd processes
        launch_file_open.write('sudo killall pigpiod\n')
        launch_file_open.write('sudo mount -o remount,size=128M /dev/shm\n') # refresh shared memory
        launch_file_open.write('sudo ' + pigpio_string + '\n')
        launch_file_open.write(params['JACKDSTRING'] + '\n')  # Then launch ours
        launch_file_open.write('sleep 2\n')  # We wait a damn second to let jackd start up
        launch_string = "python " + os.path.join(params['REPODIR'], "core", "pilot.py") + " -f " + prefs_file
        launch_file_open.write(launch_string)

    os.chmod(launch_file, 0775)

    print('executable file created:\n     {}\n'.format(launch_file))

    answer = str(raw_input('Install as Systemd service? (y/n)> '))

    if answer == 'y':
        # open pilot on startup using systemd
        systemd_string = '''[Unit]
Description=RPilot
After=multi-user.target

[Service]
Type=idle
ExecStart={launch_pi}

Restart=on-failure

[Install]
WantedBy=multi-user.target'''.format(launch_pi=launch_file)

        unit_loc = '/lib/systemd/system/rpilot.service'
        with open(unit_loc, 'w') as rpilot_service:
            rpilot_service.write(systemd_string)

        # enable the service
        subprocess.call(['sudo', 'systemctl', 'daemon-reload'])
        subprocess.call(['sudo', 'systemctl', 'enable', 'rpilot.service'])
        print('\nrpilot service installed and enabled, unit file located at:\n     {}\n'.format(unit_loc))




    pp = pprint.PrettyPrinter(indent=4)
    print('Pilot set up with prefs:\r')
    pp.pprint(params)

