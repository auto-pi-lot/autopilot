import os
import json
import argparse
import uuid
import pprint
import tables


# Check for sudo
if os.getuid() != 0:
    raise Exception("Need to run as root")

# Argument parsing
parser = argparse.ArgumentParser(description='Setup an RPilot')
parser.add_argument('-n', '--name', help="The name for this pilot")
parser.add_argument('-d', '--dir',  help="Base Directory for RPilot resources")
parser.add_argument('-p', '--pushport', help="PUB port for publishing data to terminal. 5560 is default")
parser.add_argument('-s', '--subport', help="SUB port for receiving commands from RPilots. 5555 is default")
parser.add_argument('-i', '--msginport', help="PULL port to receive messages from the Pilot class. 5565 is default")
parser.add_argument('-o', '--msgoutport', help="PUSH port to send messages from the Pilot class. 5565 is default")
parser.add_argument('-t', '--terminalip', help="Local IP of terminal. Default is 192.168.0.100")
parser.add_argument('-m', '--manualpins', help="Assign pin numbers manually")
parser.add_argument('-j', '--jackdstring', help="Specify a custom string to run jackd server")
parser.add_argument('-a', '--naudiochannels', help="Specify the number of audio channels for the pyo server to use. Default is 2")


args = parser.parse_args()

# Parse Arguments and assign defaults
if not args.name:
    name = str(uuid.uuid4())
    Warning("Need to give a name to your RPilot, assigning random unique name: {}".format(name))
else:
    name = args.name

if args.dir:
    basedir = args.dir
else:
    basedir = '/usr/rpilot'

if args.pushport:
    push_port = str(args.pushport)
else:
    push_port = '5560'

if args.subport:
    sub_port = str(args.subport)
else:
    sub_port = '5555'

if args.msginport:
    msg_in_port = str(args.msginport)
else:
    msg_in_port = '5565'

if args.msgoutport:
    msg_out_port = str(args.msgoutport)
else:
    msg_out_port = '5570'

if args.terminalip:
    terminal_ip = str(args.terminalip)
else:
    terminal_ip = '192.168.0.100'

if args.manualpins:
    # TODO: make dialog window to set pins manually
    NotImplementedError()
else:
    pins = {
        'POKES':{
            'L':7,
            'C':8,
            'R':10
        },
        'LEDS':{
            # Three pins for RGB LEDs
            'L': [11, 13, 15],
            'C': [22, 18, 16],
            'R': [19, 21, 23]
        },
        'PORTS':{
            'L':31,
            'C':33,
            'R':37
        }
    }

if args.jackdstring:
    jackd_string = str(args.jackdstring)
else:
    jackd_string = "jackd -P75 -p16 -t2000 -dalsa -dhw:sndrpihifiberry -P -n3 -r128000 -s &"

if args.naudiochannels:
    n_channels = int(args.naudiochannels)
else:
    n_channels = 2

# TODO: Turn this whole thing into a command line dialog and add this to it
pigpio_location = 'pigpiod'
# Need to make a binary mask that excludes the pins needed for hifiberry
# (BCM: 2, 3, 18, 19, 20, 21)
pigpio_mask = '-x 1111110000111111111111110000'
# Also need to use PWM rather than PCM so hifiberry can use it
# see http://abyz.co.uk/rpi/pigpio/faq.html#Sound_isnt_working
pigpio_device = '-t 0'
pigpio_string = ' '.join([pigpio_location, pigpio_mask, pigpio_device])

datadir = os.path.join(basedir,'data')
sounddir = os.path.join(basedir, 'sounds')
logdir = os.path.join(basedir,'logs')

# Check for prereqs
try:
    import pyo
    import zmq
    # TODO: Test for pigpio
    # TODO: Set pigpio to start on startup
    # TODO: don't just test, compile pyo if missing
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
if not os.path.exists(logdir):
    os.makedirs(logdir)
    os.chmod(logdir, 0777)

# make local file
local_data = os.path.join(datadir, 'local.h5')
if not os.path.exists(local_data):
    h5f = tables.open_file(local_data, mode='w')
    h5f.close()
    os.chmod(local_data, 0777)

# Get repo dir
file_loc = os.path.realpath(__file__)
file_loc = file_loc.split(os.sep)[:-2]
repo_loc = os.path.join(os.sep,*file_loc)

# make util scripts executable
util_fns = os.listdir(os.path.join(repo_loc,'utils'))
for fn in util_fns:
    os.chmod(fn, 0444)


# make prefs dict
prefs = {}
prefs['NAME'] = name
prefs['BASEDIR'] = basedir
prefs['DATADIR'] = datadir
prefs['REPODIR'] = repo_loc
prefs['SOUNDDIR'] = sounddir
prefs['LOGDIR'] = logdir
prefs['PUSHPORT'] = push_port
prefs['SUBPORT'] = sub_port
prefs['MSGINPORT'] = msg_in_port
prefs['MSGOUTPORT'] = msg_out_port
prefs['TERMINALIP'] = terminal_ip
prefs['PINS'] = pins
prefs['JACKDSTRING'] = jackd_string
prefs['NCHANNELS'] = n_channels

# save prefs
prefs_file = os.path.join(basedir, 'prefs.json')
with open(prefs_file, 'w') as prefs_file_open:
    json.dump(prefs, prefs_file_open)
os.chmod(prefs_file, 0775)


# Create .sh file to open pilot
# Some performance tweaks (stopping services, etc.) are added from: https://github.com/autostatic/scripts/blob/rpi/jackstart
launch_file = os.path.join(basedir, 'launch_pilot.sh')
with open(launch_file, 'w') as launch_file_open:
    launch_file_open.write('killall jackd\n') # Try to kill any existing jackd processes
    launch_file_open.write('sudo killall pigpiod\n')
    launch_file_open.write('sudo service ntp stop\n')
    launch_file_open.write('sudo service triggerhappy stop\n')
    #launch_file_open.write('sudo service dbus stop\n')
    launch_file_open.write('sudo killall console-kit-daemon\n')
    launch_file_open.write('sudo killall polkitd\n')
    launch_file_open.write('sudo mount -o remount,size=128M /dev/shm\n')
    launch_file_open.write('killall gvfsd\n')
    #launch_file_open.write('killall dbus-daemon\n')
    #launch_file_open.write('killall dbus-launch\n')
    launch_file_open.write('sudo ' + pigpio_string + '\n')
    launch_file_open.write(jackd_string+'\n')    # Then launch ours
    launch_file_open.write('sleep 1\n') # We wait a damn second to let jackd start up
    launch_string = "python " + os.path.join(repo_loc, "core", "pilot.py") + " -f " + prefs_file
    launch_file_open.write(launch_string)

os.chmod(launch_file, 0775)

pp = pprint.PrettyPrinter(indent=4)
print("Pilot set up with prefs:\r")
pp.pprint(prefs)

# TODO: Automatically run launch_pilot.sh on startup
# TODO: Automatically start jack on startup