"""
After initial setup, configure autopilot: create an autopilot directory and a prefs.json file

"""

import npyscreen as nps
import _curses
from collections import OrderedDict as odict
import pprint
import json
import os
import subprocess
import argparse
import sys
import inspect
import pkgutil
import ast
import importlib

from autopilot import hardware
from autopilot.setup.run_script import call_series, run_script, list_scripts
from autopilot.setup.scripts import ENV_PILOT, PILOT_ENV_CMDS

# CLI Options

parser = argparse.ArgumentParser(description="Setup an Autopilot Agent")
parser.add_argument('-f', '--prefs', help="Location of .json prefs file (default: ~/autopilot/prefs.json")
parser.add_argument('-d', '--dir', help="Autopilot directory (default: ~/autopilot)")
parser.add_argument('-s', '--script', help="Run a setup script without entering a full setup routine. for available scripts see -l")
parser.add_argument('-l', '--list_scripts', help="list available setup scripts!", action='store_true')

AGENTS = ('TERMINAL', 'PILOT', 'CHILD')

BASE_PREFS = odict({
    'NAME'       : {'type': 'str', "text": "Agent Name:"},
    'BASEDIR'    : {'type': 'str', "text":"Base Directory:", "default":os.path.join(os.path.expanduser("~"),"autopilot")},
    'PUSHPORT'   : {'type': 'int',"text":"Push Port - Router port used by the Terminal or upstream agent:", "default":"5560"},
    'MSGPORT'    : {'type': 'int', "text":"Message Port - Router port used by this agent to receive messages:", "default":"5565"},
    'TERMINALIP' : {'type': 'str', "text":"Terminal IP:", "default":"192.168.0.100"},
    'LOGLEVEL'   : {'type': 'choice', "text": "Log Level:", "choices":("DEBUG", "INFO", "WARNING", "ERROR"), "default": "WARNING"},
    'CONFIG'     : {'type': 'list', "text": "System Configuration", 'hidden': True}
})

PILOT_PREFS = odict({
    'PIGPIOMASK': {'type': 'str', 'text': 'Binary mask controlling which pins pigpio controls according to their BCM numbering, see the -x parameter of pigpiod',
                   'default': "1111110000111111111111110000"},
    'PIGPIOARGS': {'type': 'str', 'text': 'Arguments to pass to pigpiod on startup',
                   'default': '-t 0 -l'},
    'PULLUPS'   : {'type': 'list', 'text': 'Pins to pull up on system startup? (list of form [1, 2]'},
    'PULLDOWNS'   : {'type': 'list', 'text': 'Pins to pull down on system startup? (list of form [1, 2]'}
})

LINEAGE_PREFS = odict({
    'LINEAGE':     {'type': 'choice', "text": "Are we a parent or a child?", "choices": ("NONE", "PARENT", "CHILD")},
    'CHILDID'    : {'type': 'str', "text":"Child ID:", "depends":("LINEAGE", "PARENT")},
    'PARENTID'   : {'type': 'str', "text":"Parent ID:", "depends":("LINEAGE", "CHILD")},
    'PARENTIP'   : {'type': 'str', "text":"Parent IP:", "depends":("LINEAGE","CHILD")},
    'PARENTPORT' : {'type': 'str', "text":"Parent Port:", "depends":("LINEAGE", "CHILD")},
})

AUDIO_PREFS = odict({
    'AUDIOSERVER': {'type': 'bool', 'text':'Enable jack audio server?'},
    'NCHANNELS': {'type': 'int', 'text': "Number of Audio channels", 'default':1, 'depends': 'AUDIOSERVER'},
    'OUTCHANNELS': {'type': 'list', 'text': 'List of Audio channel indexes to connect to', 'default': '[1]', 'depends': 'AUDIOSERVER'},
    'FS': {'type': 'int', 'text': 'Audio Sampling Rate', 'default': 192000, 'depends': 'AUDIOSERVER'},
    'JACKDSTRING': {'type': 'str', 'text': 'Arguments to pass to jackd, see the jackd manpage',
                    'default': 'jackd -P75 -p16 -t2000 -dalsa -dhw:sndrpihifiberry -P -rfs -n3 -s &', 'depends': 'AUDIOSERVER'},
})

TERMINAL_PREFS = odict({
    'DRAWFPS': {'type': 'int', "text": "FPS to draw videos displayed during acquisition",
                "default": "20"},
    'PILOT_DB': {'type': 'str', 'text': "filename to use for the .json pilot_db that maps pilots to subjects (relative to BASEDIR)",
                 "default": "pilot_db.json"}
})

DIRECTORY_STRUCTURE = {
    'DATADIR': 'data',
    'SOUNDDIR': 'sounds',
    'LOGDIR': 'logs',
    'VIZDIR': 'viz',
    'PROTOCOLDIR': 'protocols',
}

"""
performance: 
    * disable startup script that changes cpu governor,
    * change cpu governor to "performance" on boot
    * increase memlock and realtime priority limits for audio group

hifiberry:
    * turn onboard audio off
    * enable hifiberry stuff in /boot/config.txt
    * edit alsa config so hifiberry is default sound card

viz:

.. todo::

    Need to find a more elegant way to do this, for now see lines 160-200 in the presetup_pilot.sh legacy script

"""



class Autopilot_Form(nps.Form):

    def __init__(self, *args, **kwargs):
        self.input = odict()
        self.depends = {}
        super(Autopilot_Form, self).__init__(*args, **kwargs)

        if 'params' in kwargs.keys():
            self.populate_form(kwargs['params'])

    def populate_dependencies(self, params):
        # first find any options that other options depend on
        for param_name, param in params.items():
            if 'depends' in param.keys():
                if isinstance(param['depends'], str):
                    depends_on = param['depends']
                    depend_value = True
                elif isinstance(param['depends'], tuple):
                    depends_on = param['depends'][0]
                    depend_value = param['depends'][1]

                if depends_on in self.depends.keys():
                    self.depends[depends_on].append((param_name, depend_value))
                else:
                    self.depends[depends_on] = [(param_name, depend_value)]

    def populate_form(self, params):

        # check for existing values in global prefs
        global prefs

        self.populate_dependencies(params)

        # create widgets depending on parameter type
        for param_name, param in params.items():
            if param['type'] == 'bool':
                widget = self.add(nps.CheckBox, name=param['text'])
            elif param['type'] in ('str', 'int', 'list'):
                # try to get default from prefs, otherwise use the hardcoded default if present. otherwise blank
                if param_name in prefs.keys():
                    default = prefs[param_name]
                else:
                    try:
                        default = param['default']
                    except KeyError:
                        default = ''

                widget = self.add(nps.TitleText, name=param['text'], value = str(default))
            elif param['type'] == 'choice':
                if param_name in prefs.keys():
                    try:
                        default_ind = [param['choices'].index(prefs[param_name])]
                    except ValueError:
                        default_ind = [0]
                else:
                    try:
                        default = param['default']
                        default_ind = [param['choices'].index(default)]
                    except KeyError:
                        default_ind = [0]

                widget = self.add(nps.TitleSelectOne,
                                  name = param['text'],
                                  values = param['choices'],
                                  max_height=len(param['choices'])+1,
                                  value = default_ind,
                                  scroll_exit = True)
            else:
                raise Warning("Not sure what to do with param {} with type {}".format(param_name, param['type']))

            # if this widget depends on another, initially make it uneditable
            if 'depends' in param.keys():
                widget.editable = False
                widget.color = 'NO_EDIT'
                widget.labelColor = 'NO_EDIT'


            if param_name in self.depends.keys():

                widget.when_value_edited = lambda pname=param_name: self.update_depends(pname)

            self.input[param_name] = widget

    def update_depends(self, param_name):

        #pdb.set_trace()

        # get value
        param_value = self.input[param_name].value
        if hasattr(self.input[param_name], 'values'):
            param_value = self.input[param_name].values[param_value[0]]

        if param_name in self.depends.keys():
            for dependent in self.depends[param_name]:
                if param_value == dependent[1]:
                    self.input[dependent[0]].editable = True
                    self.input[dependent[0]].color = 'DEFAULT'
                    self.input[dependent[0]].labelColor = 'LABEL'
                else:
                    self.input[dependent[0]].editable = False
                    self.input[dependent[0]].color = 'NO_EDIT'
                    self.input[dependent[0]].labelColor = 'NO_EDIT'


class Hardware_Form(nps.FormWithMenus):
    def __init__(self, *args, **kwargs):
        self.input = odict()
        self.altrely = 4
        super(Hardware_Form, self).__init__(*args, **kwargs)


    def create(self):
        self.add(nps.FixedText, value="Use the ctrl+X menu to add new hardware", editable=False, color="VERYGOOD")

        hardware_objs = self.list_hardware()

        for module, hardware_classes in hardware_objs.items():

            mod_menu = self.add_menu(module)
            for class_name in hardware_classes:
                mod_menu.addItem(text=class_name, onSelect=self.add_hardware, arguments=[module, class_name])

    #
    # def init_hardware(self):
    #     global prefs
    #     if 'HARDWARE' in prefs.keys():
    #         for hw_group, hardware_name in prefs
    #
    # def add_hardware_widget(self, sigs):
    #


    def list_hardware(self):
        # start at the top of the autopilot hardware package and work down
        # get all classes that are defined within the hardware module
        base_hardware = [m[0]for m in inspect.getmembers(hardware, inspect.isclass) if m[1].__module__ == hardware.__name__]

        hardware_path = os.path.dirname(hardware.__file__)

        # get names of modules
        submodules = [mod for _, mod, _ in pkgutil.iter_modules([hardware_path])]
        submod_paths = [os.path.join(hardware_path, mod)+'.py' for mod in submodules]

        # we don't want to have to import all the hardware modules just to get a list of them,
        # and only want to try to import them if the user wants to add one to their system
        # so we have to parse the files to get the names of the classes

        hardware_objs = {}
        for submod_name, submod in zip(submodules, submod_paths):
            with open(submod, 'r') as submod_f:
                submod_ast = ast.parse(submod_f.read())

            submod_classes = [n.name for n in submod_ast.body if isinstance(n, ast.ClassDef) and n.name not in hardware.META_CLASS_NAMES]
            hardware_objs[submod_name] = submod_classes

        return hardware_objs




    def add_hardware(self, module, class_name):
        #self.nextrely = 1
        self.DISPLAY()

        # import the class
        hw_class = getattr(importlib.import_module("autopilot.hardware."+module), class_name)
        # get its parent classes (which includes class itself)
        hw_parents = inspect.getmro(hw_class)
        # get signatures for each
        # go in reverse order so top classes options come first
        sigs = []
        # list to keep track of parameter names to remove duplicates
        param_names = []
        for cls in reversed(hw_parents):
            # get signature
            sig = inspect.signature(cls)
            # get parameter names and defaults
            for param_name, param in sig.parameters.items():
                param_default = param.default
                if param_default == inspect._empty:
                    param_default = None
                if param_name in ('kwargs', 'args'):
                    continue

                if param_name not in param_names:
                    # check if we already have a parameter with this name,
                    # if we don't add it.
                    sigs.append((param_name, param_default))
                    param_names.append(param_name)

        MODULE = module.upper()
        # create title and input widgets for arguments

        #pdb.set_trace()

        self.add(nps.FixedText, value="{}.{}".format(module, class_name), rely=self.altrely, editable=False, color="VERYGOOD")

        self.altrely+=1

        hw_widgets = {}
        hw_widgets['type'] = "{}.{}".format(module, class_name)
        for sig in sigs:
            if sig[1] is None:
                sig = (sig[0], '')


            #if isinstance(sig[1], bool):
            #    hw_widgets.append(self.add(nps.CheckBox, name=sig[0], value=sig[1], rely=self.altrely))
            #else:
            hw_widgets[sig[0]] = self.add(nps.TitleText, name=sig[0], value=str(sig[1]), rely=self.altrely)

            self.altrely+=1
        self.altrely+=1

        if MODULE not in self.input.keys():
            self.input[MODULE] = []

        self.input[MODULE].append(hw_widgets)

    def afterEditing(self):
        self.parentApp.setNextForm(None)








class Agent_Form(nps.Form):
    def create(self):
        # self.input = odict({
        #     'AGENT': self.add(nps.TitleSelectOne, max_height=len(AGENTS)+1, value=[0,],
        #                       name="Select an Agent. If this is a Raspberry Pi you should select either 'PILOT' or 'CHILD', and if this is the computer you will be using to control Autopilot you should select 'TERMINAL'", values = AGENTS, scroll_exit=True)
        # })

        if os.path.exists(os.path.join(os.path.dirname(__file__),'welcome_msg.txt')):
            with open(os.path.join(os.path.dirname(__file__),'welcome_msg.txt'), 'r') as welcome_f:
                welcome = welcome_f.read()
                for line in welcome.split('\n'):self.add(nps.FixedText, value=line, editable=False)

        self.input = odict({
            'AGENT': self.add(nps.TitleSelectOne, max_height=len(AGENTS)+1, value=0,
                              name="Select an Autopilot Agent", values=AGENTS, scroll_exit=True)
        })

    def afterEditing(self):
        # terminal
        global prefs

        if self.input['AGENT'].value[0] == 0:
            prefs['AGENT'] = 'TERMINAL'
            self.parentApp.setNextForm('TERMINAL')
        elif self.input['AGENT'].value[0] == 1:
            prefs['AGENT'] = 'PILOT'
            self.parentApp.setNextForm('ENV_PILOT')
        elif self.input['AGENT'].value[0] == 2:
            prefs['AGENT'] = 'CHILD'
            self.parentApp.setNextForm('CHILD')
        else:
            self.parentApp.setNextForm(None)


class Pilot_Env_Form(Autopilot_Form):
    def create(self):
        self.populate_form(ENV_PILOT)

    def afterEditing(self):
        self.parentApp.setNextForm('CONFIG_PILOT_1')

class Pilot_Config_Form_1(Autopilot_Form):
    def create(self):
        self.add(nps.FixedText, value='Base Prefs', editable=False, color="VERYGOOD")
        self.populate_form(BASE_PREFS)
        self.add(nps.FixedText, value='Pilot Prefs', editable=False, color="VERYGOOD")
        self.populate_form(PILOT_PREFS)

    def afterEditing(self):
        self.parentApp.setNextForm('CONFIG_PILOT_2')

class Pilot_Config_Form_2(Autopilot_Form):
    def create(self):
        self.add(nps.FixedText, value='Lineage Prefs', editable=False, color="VERYGOOD")
        self.populate_form(LINEAGE_PREFS)
        self.add(nps.FixedText, value='Audio Prefs', editable=False, color="VERYGOOD")
        self.populate_form(AUDIO_PREFS)

    def afterEditing(self):
        self.parentApp.setNextForm('HARDWARE')



class Terminal_Form(Autopilot_Form):
    def create(self):
        self.add(nps.FixedText, value='Base Prefs', editable=False, color="VERYGOOD")
        self.populate_form(BASE_PREFS)
        self.add(nps.FixedText, value='Terminal Prefs', editable=False, color="VERYGOOD")
        self.populate_form(TERMINAL_PREFS)

    def afterEditing(self):
        self.parentApp.setNextForm(None)



class Autopilot_Setup(nps.NPSAppManaged):
    def __init__(self, prefs):
        super(Autopilot_Setup, self).__init__()
        self.prefs = prefs

    def onStart(self):
        self.agent = self.addForm('MAIN', Agent_Form, name="Select Agent")
        self.env_pilot = self.addForm('ENV_PILOT', Pilot_Env_Form, name="Configure Pilot Environment")
        self.pilot_1 = self.addForm('CONFIG_PILOT_1', Pilot_Config_Form_1, name="Setup Pilot Agent - 1/2")
        self.pilot_2 = self.addForm('CONFIG_PILOT_2', Pilot_Config_Form_2, name="Setup Pilot Agent - 2/2")
        self.hardware = self.addForm('HARDWARE', Hardware_Form, name="Hardware Configuration")
        self.terminal = self.addForm('TERMINAL', Terminal_Form, name="Terminal Configuration")

def unfold_values(v):
    """
    Unfold nested values from the SetupForm. Called recursively.

    Args:
        v (dict): unfolded values
    """
    if isinstance(v, dict):
        # recurse
        v = {k: unfold_values(v) for k, v in v.items()}
    elif isinstance(v, list):
        v = [unfold_values(v) for v in v]
    elif isinstance(v, str):
        # do nothing since this is what we want yno
        pass
    else:
        #pdb.set_trace()

        if hasattr(v, 'values'):
            # if it's an object that has mutiple values, ie. a choice box, value is inside a list.
            v = v.values[v.value[0]]
        elif hasattr(v, 'value'):
            # if it isn't a list, but is still a widget object, get the value
            v = v.value


        try:
            # convert ints to ints, lists to lists, etc. from strings
            v = ast.literal_eval(v)
        except:
            # fine, just a string that can't be evaluated into another type
            pass
    return v


def make_dir(adir):
    """
    Make a directory if it doesn't exist and set its permissions to `0777`

    Args:
        adir (str): Path to the directory
    """
    if not os.path.exists(adir):
        os.makedirs(adir)

    os.chmod(adir, 0o774)

if __name__ == "__main__":
    env = {}
    env_params = {}
    prefs = {}
    error_msgs = []
    config_msgs = []

    args = parser.parse_args()

    if args.list_scripts:
        list_scripts()
        sys.exit()
    elif args.script:
        run_script(args.script)
        sys.exit()

    if args.dir:
        autopilot_dir = args.dir

    else:
        # check for a ~/.autopilot file that should point us to the autopilot directory if it exists
        autopilot_conf_fn = os.path.join(os.path.expanduser('~'), '.autopilot')
        if os.path.exists(autopilot_conf_fn):
            with open(autopilot_conf_fn, 'r') as aconf:
                autopilot_dir = aconf.read()
                # autopilot_dir = autopilof_conf['AUTOPILOTDIR']
        else:
            autopilot_dir = os.path.join(os.path.expanduser('~'), 'autopilot', '')

    make_dir(autopilot_dir)


    # attempt to load .prefs from standard location (~/autopilot/prefs.json)
    if args.prefs:
        prefs_fn = args.prefs
    else:
        prefs_fn = os.path.join(autopilot_dir, 'prefs.json')

    if os.path.exists(prefs_fn):
        with open(prefs_fn, 'r') as prefs_f:
            prefs = json.load(prefs_f)

    ###################################3
    # Run the npyscreen prompt

    try:
        setup = Autopilot_Setup(prefs)
        setup.run()
    except (_curses.error, nps.wgwidget.NotEnoughSpaceForWidget) as e:
        # get minimum column count
        try:
            min_cols = setup.getForm(setup.STARTING_FORM).min_c
            print(f'Problem opening the Setup GUI!\nThis is most likely due to this window not being wide enough\n' + \
                  'The minimum width for the setup GUI is:\n\033[0;32;40m' + \
                  "-"*min_cols + '\u001b[0m\n\n' + f'Got error:\n{e}')

        except:
            print(f'Problem opening the Setup GUI!\nThis is most likely due to this window not being wide enough\n\nGot Error:\n{e}')

        sys.exit()

    ####################################
    # Collect values

    agent = {k:unfold_values(v) for k, v in setup.agent.input.items()}
    prefs['AGENT'] = agent['AGENT']
    if agent['AGENT'] in ('PILOT', 'CHILD'):
        pilot = odict({k: unfold_values(v) for k, v in setup.pilot_1.input.items()})
        pilot.update(odict({k: unfold_values(v) for k, v in setup.pilot_2.input.items()}))
        hardware_flat = odict({k: unfold_values(v) for k, v in setup.hardware.input.items()})

        # have to un-nest hardware a bit
        # currently is hardware['CAMERAS'] = [{config 1}, {config 2]
        # want         hardware['CAMERAS']['cam_name_1'] = {config}
        hardware = {}
        for hardware_group, hardware_list in hardware_flat.items():
            hardware[hardware_group] = {}
            for hardware_config in hardware_list:
                hardware[hardware_group][hardware_config['name']] = hardware_config

        # get env commands to run
        env_params = odict({k: unfold_values(v) for k, v in setup.env_pilot.input.items()})
        for env_param, result in env_params.items():
            if env_param in PILOT_ENV_CMDS.keys() and result == 1:
                env[env_param] = PILOT_ENV_CMDS[env_param]

        # merge with any existing prefs
        prefs.update(pilot)
        if 'HARDWARE' not in prefs.keys():
            prefs['HARDWARE'] = hardware
        else:
            prefs['HARDWARE'].update(hardware)
    elif agent['AGENT'] == 'TERMINAL':
        # unpack prefs

        terminal = odict({k: unfold_values(v) for k, v in setup.terminal.input.items()})


        # create the pilot_db if it doesn't exist
        terminal['PILOT_DB'] = os.path.join(terminal['BASEDIR'], terminal['PILOT_DB'])
        if not os.path.exists(terminal['PILOT_DB']):
            with open(terminal['PILOT_DB'], 'w') as pilot_db_file:
                json.dump({}, pilot_db_file)

        os.chmod(terminal['PILOT_DB'], 0o775)

        # merge with any existing prefs
        prefs.update(terminal)




    ####################################
    # Configure Environment

    # detect if we are in a virtual environment
    venv_path = ''
    if hasattr(sys, 'real_prefix') or (sys.base_prefix != sys.prefix):
        # virtualenv and pyenv populate these system attrs
        venv_path = sys.prefix
        prefs['VENV'] = venv_path
    else:
        prefs['VENV'] = False

    # get repo directory
    file_loc = os.path.realpath(__file__)
    file_loc = file_loc.split(os.sep)[:-3]
    prefs['REPODIR'] = os.path.join(os.sep, *file_loc)

    # run any environment configuration commands
    env_results = {}
    for env_config, env_command in env.items():
        env_results[env_config] = call_series(env_command, env_config)

    # Create directory structure if needed
    #pdb.set_trace()
    for dir_name, dir_path in DIRECTORY_STRUCTURE.items():
        prefs[dir_name] = os.path.join(prefs['BASEDIR'], dir_path)
        make_dir(prefs[dir_name])

    # Create a launch script
    prefs_fn = os.path.join(prefs['BASEDIR'], 'prefs.json')
    launch_file = os.path.join(prefs['BASEDIR'], 'launch_autopilot.sh')

    if prefs['AGENT'] in ('PILOT', 'CHILD'):
        with open(launch_file, 'w') as launch_file_open:
            launch_file_open.write('#!/bin/bash\n')
            launch_file_open.write('killall jackd\n')
            launch_file_open.write('sudo killall pigpiod\n')
            launch_file_open.write('sudo mount -o remount,size=128M /dev/shm\n')
            if prefs['VENV']:
                launch_file_open.write("source " + os.path.join(prefs['VENV'], 'bin', 'activate')+'\n')
            launch_file_open.write('python3 -m autopilot.core.pilot -f {}'.format(prefs_fn))

    elif prefs['AGENT'] == 'TERMINAL':
        with open(launch_file, 'w') as launch_file_open:
            launch_file_open.write('#!/bin/bash\n')
            if prefs['VENV']:
                launch_file_open.write("source " + os.path.join(prefs['VENV'], 'bin', 'activate')+'\n')
            launch_file_open.write("python3 -m autopilot.core.terminal -f " + prefs_fn + "\n")


    config_msgs.append("Launch file created at {}".format(launch_file))
    os.chmod(launch_file, 0o775)

    # install as systemd service if requested
    if 'systemd' in env_params.keys():
        if env_params['systemd'] in (1, True):
            systemd_string = '''
[Unit]
Description=autopilot
After=multi-user.target

[Service]
Type=idle
ExecStart={launch_pi}

Restart=on-failure

[Install]
WantedBy=multi-user.target'''.format(launch_pi=launch_file)

            try:
                unit_loc = '/lib/systemd/system/autopilot.service'

                subprocess.call('sudo sh -c \"echo \'{}\' > {}\"'.format(systemd_string, unit_loc), shell=True)
                # enable the service
                subprocess.call(['sudo', 'systemctl', 'daemon-reload'])
                sysd_result = subprocess.call(['sudo', 'systemctl', 'enable', 'autopilot.service'])

                if sysd_result != 0:
                    error_msgs.append('Systemd service could not be enabled :(')
                else:
                    env_results['systemd'] = True
                    config_msgs.append('Systemd service installed and enabled, unit file written to {}'.format(unit_loc))

            except PermissionError:
                error_msgs.append("systemd service could not be installed due to a permissions error.\n"+\
                                  "create a unit file containing the following at {}\n\n{}".format(unit_loc, systemd_string))
                env_results['systemd'] = False



    ####################################
    # save prefs and finalize environment


    # save prefs
    #prefs_json = json.dumps(prefs, indent=4, separators=(',', ': '), sort_keys=True)
    #prefs_ret = subprocess.call('sudo sh -c \"echo \'{}\' > {}\"'.format(shlex.quote(prefs_json), shlex.quote(prefs_fn)), shell=True)
    # if prefs_ret != 0:
    #     error_msgs.append('Couldnt create prefs file :(')
    with open(prefs_fn, 'w') as prefs_f:
       json.dump(prefs, prefs_f, indent=4, separators=(',', ': '), sort_keys=True)

    # save basedir in autopilot user file
    with open(os.path.join(os.path.expanduser('~'), '.autopilot'), 'w') as autopilot_f:
        autopilot_f.write(prefs['BASEDIR'])





    #####################################3
    # User feedback

    env_result = "\033[0;32;40m\n--------------------------------\nEnvironment Configuration:\n"
    for config, result in env_results.items():
        if result:
            env_result += "  [ SUCCESS ] "
        else:
            env_result += "  [ FAILURE ] "

        env_result += config
        env_result += '\n'

    if venv_path:
        env_result += "  [ SUCCESS ] virtualenv detected, path: {}\n".format(venv_path)
    else:
        env_result += "  [ CMONDOG ] no virtualenv detected, running autopilot outside a venv is not recommended but it might work who knows\n"


    if len(config_msgs)>0:
        env_result += '\nAdditional Messages:'
        for msg in config_msgs:
            env_result += '  '
            env_result += msg
            env_result += '\n'



    env_result += '--------------------------------\u001b[0m'


    print('\n----------------------------------------')
    print('prefs.json has been created and saved to {}'.format(prefs_fn))
    pprint.pprint(prefs)
    print('----------------------------------------\n')

    print(env_result)

    if len(error_msgs)>0:
        for i, msg in enumerate(error_msgs):
            print('\033[1;37;41mSomething went wrong during setup, this is wrong thing #{}\u001b[0m'.format(i))
            print('\033[0;31;40m\n{}\n\u001b[0m'.format(msg))









    # TODO: After setup, create .autopilot file in user dir to point to autopilot dir

