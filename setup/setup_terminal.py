# Routines for initially setting up a terminal

import os
import json
import argparse
import pprint

# Check for sudo

if os.getuid() != 0:
    raise Exception("Need to run as root")


# Argument parsing
parser = argparse.ArgumentParser(description="Setup an RPilot Terminal")
parser.add_argument('-d', '--dir', help="Base Directory for RPilot")

args = parser.parse_args()

if args.dir:
    basedir = args.dir
else:
    basedir = '/usr/rpilot'

datadir = os.path.join(basedir,'data')
protocoldir = os.path.join(basedir,'protocols')

# Check for prereqs
try:
   import PySide
   import pyo
except:
   print("Error importing prerequisite packages!")

#TODO: Handle permissions better than this...
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
if not os.path.exists(protocoldir):
    os.makedirs(protocoldir)
    os.chmod(protocoldir, 0777)



# Get repo dir
file_loc = os.path.realpath(__file__)
file_loc = file_loc.split(os.sep)[:-2]
repo_loc = os.path.join(os.sep,*file_loc)


# make prefs dict
prefs = {}
prefs['BASEDIR'] = basedir
prefs['DATADIR'] = datadir
prefs['REPODIR'] = repo_loc
prefs['PROTOCOLDIR'] = protocoldir


# If it doesn't exist, make a blank pilot database
pilot_db = os.path.join(basedir,'pilot_db.json')
prefs['PILOT_DB'] = pilot_db
if not os.path.exists(pilot_db):
    with open(pilot_db, 'w') as pilot_db_file:
        json.dump({}, pilot_db_file)

os.chmod(pilot_db, 0777)

# save prefs
prefs_file = os.path.join(basedir, 'prefs.json')
with open(prefs_file, 'w') as prefs_file_open:
    json.dump(prefs, prefs_file_open)


# Create .sh file to open terminal
launch_file = os.path.join(basedir, 'launch_terminal.sh')
with open(launch_file, 'w') as launch_file_open:
    launch_string = "python " + os.path.join(repo_loc, "core", "terminal.py") + " -p " + prefs_file
    launch_file_open.write(launch_string)

os.chmod(launch_file, 0775)


pp = pprint.PrettyPrinter(indent=4)
print("Terminal set up with prefs:\r")
pp.pprint(prefs)







