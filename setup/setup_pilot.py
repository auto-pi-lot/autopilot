import os
import json
import argparse


# Check for sudo
if os.getuid() != 0:
    raise Exception("Need to run as root")

# Argument parsing
parser = argparse.ArgumentParser(description='Setup an RPilot')
parser.add_argument('-n', '--name', help="The name for this pilot")
parser.add_argument('-d', '--dir',  help="Base Directory for RPilot resources")
parser.add_argument('-p', '--pubport', help="PUB port for publishing data to terminal. 5560 is default")
parser.add_argument('-s', '--subport', help="SUB port for receiving commands from RPilots. 5555 is default")
parser.add_argument('-y', '--syncport', help="REQ port to synchronize RPilot subscriptions. 5565 is default")



args = parser.parse_args()

# Parse Arguments and assign defaults
if not args.name:
    Exception("Need to give a name to your RPilot")
else:
    name = args.name

if args.dir:
    basedir = args.dir
else:
    basedir = '/usr/rpilot'

if args.pubport:
    pub_port = str(args.pubport)
else:
    pub_port = '5560'

if args.subport:
    sub_port = str(args.subport)
else:
    sub_port = '5555'

if args.syncport:
    sync_port = str(args.syncport)
else:
    sync_port = '5565'


datadir = os.path.join(basedir,'data')
sounddir = os.path.join(basedir, 'sounds')

# Check for prereqs
try:
    import pyo
except:
    print("Error importing prerequisite packages!")

# Make folders
if not os.path.exists(basedir):
    try:
        os.makedirs(basedir)
        os.chmod(basedir, 0777)
    except:
        print("Error making basedir: {}".format(basedir))
if not os.path.exists(datadir):
    os.makedirs(datadir)
    os.chmod(datadir, 0777)
if not os.path.exists(sounddir):
    os.makedirs(sounddir)
    os.chmod(sounddir, 0777)

# Get repo dir
file_loc = os.path.realpath(__file__)
file_loc = file_loc.split(os.sep)[:-2]
repo_loc = os.path.join(os.sep,*file_loc)


# make prefs dict
prefs = {}
prefs['BASEDIR'] = basedir
prefs['DATADIR'] = datadir
prefs['REPODIR'] = repo_loc
prefs['SOUNDDIR'] = sounddir
prefs['PUBPORT'] = pub_port
prefs['SUBPORT'] = sub_port
prefs['SYNCPORT'] = sync_port

# save prefs
prefs_file = os.path.join(basedir, 'prefs.json')
with open(prefs_file, 'w') as prefs_file_open:
    json.dump(prefs, prefs_file_open)


# Create .sh file to open pilot
launch_file = os.path.join(basedir, 'launch_pilot.sh')
with open(launch_file, 'w') as launch_file_open:
    launch_string = "python " + os.path.join(repo_loc, "core", "pilot.py") + " -p " + prefs_file
    launch_file_open.write(launch_string)

os.chmod(launch_file, 0775)

# TODO: Automatically run launch_pilot.sh on startup
