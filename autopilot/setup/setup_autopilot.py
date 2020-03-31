"""
After initial setup, configure autopilot: create an autopilot directory and a prefs.json file

"""

import npyscreen as nps
from collections import OrderedDict as odict
import pprint
import json
import os
import subprocess
import argparse
import sys
import pdb
from copy import copy
import inspect
import pkgutil
import ast
import importlib
import threading

sys.path.append('/home/jonny/git/autopilot')

from autopilot import hardware

# CLI Options
parser = argparse.ArgumentParser(description="Setup an Autopilot Agent")
parser.add_argument('-f', '--prefs', help="Location of .json prefs file (default: /usr/autopilot/prefs.json")
parser.add_argument('-d', '--dir', help="Autopilot directory (default: /usr/autopilot)")

AGENTS = ('TERMINAL', 'PILOT', 'CHILD')


ENV_PILOT = odict({
    'change_pw': {'type': 'bool',
                  'text': "If you haven't, you should change the default raspberry pi password or you _will_ get your identity stolen. Change it now?"},
    'set_locale': {'type': 'bool',
                   'text': 'Would you like to set your locale?'},
    'hifiberry' : {'type': 'bool',
                   'text': 'Setup Hifiberry DAC/AMP?'},
    'viz'       : {'type': 'bool',
                   'text': 'Install X11 server and psychopy for visual stimuli?'},
    'bluetooth' : {'type': 'bool',
                   'text': 'Disable Bluetooth?'}

})

BASE_PREFS = odict({
    'AGENT'      : {'type': 'choice', "text": "Agent type", "choices":("PILOT", "TERMINAL", "CHILD")},
    'NAME'       : {'type': 'str', "text": "Agent Name:"},
    'BASEDIR'    : {'type': 'str', "text":"Base Directory:", "default":"~/autopilot"},
    'PUSHPORT'   : {'type': 'int',"text":"Push Port - Router port used by the Terminal or upstream agent:", "default":"5560"},
    'MSGPORT'    : {'type': 'int', "text":"Message Port - Router port used by this agent to receive messages:", "default":"5565"},
    'TERMINALIP' : {'type': 'str', "text":"Terminal IP:", "default":"192.168.0.100"},
    'LOGLEVEL'   : {'type': 'choice', "text": "Log Level:", "choices":("DEBUG", "INFO", "WARNING", "ERROR"), "default": "WARNING"},
    'CONFIG'     : {'type': 'list', "text": "System Configuration", 'hidden': True}
})

PILOT_PREFS = odict({
    'PIGPIOMASK': {'type': 'str', 'text': 'Binary mask controlling which pins pigpio controls according to their BCM numbering, see the -x parameter of pigpiod',
                   'default': "1111110000111111111111110000"}
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
        self.add(nps.FixedText, value="Use the ctrl+X menu to add new hardware")

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
                sigs.append((param_name, param_default))

        MODULE = module.upper()
        # create title and input widgets for arguments

        #pdb.set_trace()

        self.add(nps.FixedText, value="{}.{}".format(module, class_name), rely=self.altrely)

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
        self.parentApp.setNextForm('CONFIG_PILOT')

class Pilot_Config_Form(Autopilot_Form):
    def create(self):
        self.add(nps.FixedText, value='Base Prefs')
        self.populate_form(BASE_PREFS)
        self.add(nps.FixedText, value='Pilot Prefs')
        self.populate_form(PILOT_PREFS)
        self.add(nps.FixedText, value='Lineage Prefs')
        self.populate_form(LINEAGE_PREFS)
        self.add(nps.FixedText, value='Audio Prefs')
        self.populate_form(AUDIO_PREFS)

    def afterEditing(self):
        self.parentApp.setNextForm('HARDWARE')






class Autopilot_Setup(nps.NPSAppManaged):
    def __init__(self, prefs):
        super(Autopilot_Setup, self).__init__()
        self.prefs = prefs

    def onStart(self):
        self.agent = self.addForm('MAIN', Agent_Form, name="Select Agent")
        self.env_pilot = self.addForm('ENV_PILOT', Pilot_Env_Form, name="Configure Pilot Environment")
        self.pilot = self.addForm('CONFIG_PILOT', Pilot_Config_Form, name="Setup Pilot Agent")
        self.hardware = self.addForm('HARDWARE', Hardware_Form, name="Hardware Configuration")

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
    else:

        try:
            v = int(v.value)
        except:
            if hasattr(v, 'values'):
                v = v.values[v.value[0]]
            else:
                v = v.value
    return v

if __name__ == "__main__":
    args = parser.parse_args()

    if args.dir:
        autopilot_dir = args.dir

    else:
        # check for a ~/.autopilot file that should point us to the autopilot directory if it exists
        autopilot_conf_fn = os.path.join(os.path.expanduser('~'), '.autopilot')
        if os.path.exists(autopilot_conf_fn):
            with open(autopilot_conf_fn, 'r') as aconf:
                autopilof_conf = json.load(aconf)
                autopilot_dir = autopilof_conf['AUTOPILOTDIR']
        else:
            autopilot_dir = '/usr/autopilot/'

    # attempt to load .prefs from standard location (/usr/autopilot/prefs.json)
    prefs = {}

    if args.prefs:
        prefs_fn = args.prefs
    else:
        prefs_fn = os.path.join(autopilot_dir, 'prefs.json')

    if os.path.exists(prefs_fn):
        with open(prefs_fn, 'r') as prefs_f:
            prefs = json.load(prefs_f)

    setup = Autopilot_Setup(prefs)
    setup.run()

    agent = {k:unfold_values(v) for k, v in setup.agent.input.items()}
    if agent['AGENT'] in ('PILOT', 'CHILD'):
        pilot = odict({k: unfold_values(v) for k, v in setup.pilot.input.items()})
        hardware = odict({k: unfold_values(v) for k, v in setup.hardware.input.items()})




    # TODO: After setup, create .autopilot file in user dir to point to autopilot dir

