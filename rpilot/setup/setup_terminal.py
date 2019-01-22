import npyscreen as nps
from collections import OrderedDict as odict
import pprint
import json
import os

class TerminalSetupForm(nps.SplitForm):
    def create(self):
        self.input = odict({
            'BASEDIR': self.add(nps.TitleText, name="Base Directory:", value="/usr/rpilot"),
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



    ##############################
    # Compute derived values
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
        json.dump(params, prefs_file_open)
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

