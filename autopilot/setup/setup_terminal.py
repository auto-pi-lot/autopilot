"""
Run as a module as root.

Run as a module as root.

Creates a :class:`npyscreen.SplitForm` to prompt the user in the command line
for parameters to set up a :class:`~.terminal.Terminal` .

Sets the following prefs:

* **BASEDIR** - Base directory for all local autopilot data, typically `/usr/autopilot`
* **MSGPORT** - Port to use for our ROUTER listener, default `5560`
* **DATADIR** -  `os.path.join(params['BASEDIR'], 'data')`
* **SOUNDDIR** - `os.path.join(params['BASEDIR'], 'sounds')`
* **PROTOCOLDIR** - `os.path.join(params['BASEDIR'], 'protocols')`
* **LOGDIR** - `os.path.join(params['BASEDIR'], 'logs')`
* **REPODIR** - Path to autopilot git repo
* **PILOT_DB** - Location of `pilot_db.json` used to populate :attr:`~.Terminal.pilots`



"""

import npyscreen as nps
from collections import OrderedDict as odict
import pprint
import json
import os
from sys import platform
import subprocess

class TerminalSetupForm(nps.SplitForm):
    def create(self):
        self.input = odict({
            'BASEDIR': self.add(nps.TitleText, name="Base Directory:", value="/usr/autopilot"),
            'MSGPORT': self.add(nps.TitleText, name="Message Port - Our router port:", value="5560"),
        })
        #self.inName = self.add(nps.)


    # after we're done editing, close the input program
    def afterEditing(self):
        self.parentApp.setNextForm(None)

class SetupApp(nps.NPSAppManaged):
    def onStart(self):
        self.form = self.addForm('MAIN', TerminalSetupForm, name='Setup Terminal')


def unfold_values(v):
    """
    Unfold nested values from the SetupForm. Called recursively.

    Args:
        v (dict): unfolded values
    """
    if isinstance(v, dict):
        # recurse
        v = {k: unfold_values(v) for k, v in v.items()}
    else:
        try:
            v = int(v.value)
        except:
            v = v.value
    return v


def make_dir(adir):
    """
    Make a directory if it doesn't exist and set its permissions to `0777`

    Args:
        adir (str): Path to the directory
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



    ##############################
    # Compute derived values

    # we are known as a terminal
    params['AGENT'] = 'terminal'

    # try making basedir, if we can't do it, modify and alert
    try:
        make_dir(params['BASEDIR'])
    except OSError:
        params['BASEDIR'] = os.path.join(os.path.expanduser('~'), 'autopilot')
        make_dir(params['BASEDIR'])
        print('Permissions error making base directory, instead using {}'.format(params['BASEDIR']))



    # define and make directory structure
    params['DATADIR'] = os.path.join(params['BASEDIR'], 'data')
    params['SOUNDDIR'] = os.path.join(params['BASEDIR'], 'sounds')
    params['PROTOCOLDIR'] = os.path.join(params['BASEDIR'], 'protocols')
    params['LOGDIR'] = os.path.join(params['BASEDIR'], 'logs')

    for adir in [params['BASEDIR'], params['DATADIR'], params['SOUNDDIR'], params['LOGDIR'], params['PROTOCOLDIR']]:
        make_dir(adir)

    # Get repo dir
    file_loc = os.path.realpath(__file__)
    file_loc = file_loc.split(os.sep)[:-2]
    params['REPODIR'] = os.path.join(os.sep, *file_loc)

    # If it doesn't exist, make a blank pilot database
    pilot_db = os.path.join(params['BASEDIR'], 'pilot_db.json')
    params['PILOT_DB'] = pilot_db
    if not os.path.exists(pilot_db):
        with open(pilot_db, 'w') as pilot_db_file:
            json.dump({}, pilot_db_file)

    os.chmod(pilot_db, 0777)

    # save prefs
    prefs_file = os.path.join(params['BASEDIR'], 'prefs.json')
    with open(prefs_file, 'w') as prefs_file_open:
        json.dump(params, prefs_file_open, indent=4, separators=(',', ': '), sort_keys=True)
    os.chmod(prefs_file, 0775)

    print('params saved to {}\n'.format(prefs_file))

    ###############################
    # Install service or create runfile
    launch_string = "python " + os.path.join(params['REPODIR'], "core", "terminal.py") + " -f " + prefs_file
    launch_file = os.path.join(params['BASEDIR'], 'launch_terminal.sh')
    with open(launch_file, 'w') as launch_file_open:
        launch_file_open.write(launch_string)
    os.chmod(launch_file, 0775)

    pp = pprint.PrettyPrinter(indent=4)
    print('Terminal set up with prefs written to:\n{}\n'.format(launch_file))
    pp.pprint(params)

    # create alias
    if platform == 'darwin':
        prof_file = os.path.join(os.path.expanduser('~'), '.bash_profile')
    else:
        prof_file = os.path.join(os.path.expanduser('~'), '.profile')

    alias_cmd = "\n#autopilot terminal alias\n\nalias terminal='{}'".format(launch_file)

    with open(prof_file, 'a+') as profile:
        profile.write(alias_cmd)

    subprocess.call(['alias', 'terminal=\'{}\''.format(launch_file)])

    print('Attempted to create alias \'terminal\' to launch file {}'.format(launch_file))



