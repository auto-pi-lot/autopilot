import ast
import inspect
import os
import typing
from collections import OrderedDict as odict

import npyscreen as nps

import autopilot
from autopilot.prefs import _DEFAULTS, Scopes
from autopilot.setup.scripts import SCRIPTS

# --------------------------------------------------
# split up prefs
# --------------------------------------------------

BASE_PREFS = odict({
    k:v for k, v in _DEFAULTS.items() if v["scope"] == Scopes.COMMON
})
PILOT_PREFS = odict({
    k:v for k, v in _DEFAULTS.items() if v["scope"] == Scopes.PILOT
})
LINEAGE_PREFS = odict({
    k:v for k, v in _DEFAULTS.items() if v["scope"] == Scopes.LINEAGE
})
AUDIO_PREFS = odict({
    k:v for k, v in _DEFAULTS.items() if v["scope"] == Scopes.AUDIO
})
TERMINAL_PREFS = odict({
    k:v for k, v in _DEFAULTS.items() if v["scope"] == Scopes.TERMINAL
})
DIRECTORY_STRUCTURE = odict({
    k:v for k, v in _DEFAULTS.items() if v["scope"] == Scopes.DIRECTORY
})

AGENTS = ('TERMINAL', 'PILOT', 'CHILD')

# --------------------------------------------------
# base class
# --------------------------------------------------

class Autopilot_Form(nps.Form):
    """
    Base class for Autopilot setup forms

    Each subclass needs to override the :meth:`.create` method to add the graphical elements for the form,
    typically by using :meth:`.populate_form` with a standardized description from :mod:`autopilot.prefs` , and
    the NAME attribute. The DESCRIPTION attribute provides title text for the form
    """

    NAME = "" # type: str
    DESCRIPTION = "" # type: str

    def __init__(self, prefs:dict, *args, **kwargs):
        self.prefs = prefs
        self.exports = {} # put any programmatically declared prefs here.
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
                elif isinstance(param['depends'], (tuple, list)):
                    depends_on = param['depends'][0]
                    depend_value = param['depends'][1]

                if depends_on in self.depends.keys():
                    self.depends[depends_on].append((param_name, depend_value))
                else:
                    self.depends[depends_on] = [(param_name, depend_value)]

    def populate_form(self, params):

        # check for existing values in global prefs

        self.populate_dependencies(params)

        # create widgets depending on parameter type
        for param_name, param in params.items():
            if param['type'] == 'bool':
                widget = self.add(nps.CheckBox, name=param['text'])
            elif param['type'] == 'choice':
                if param_name in self.prefs.keys():
                    try:
                        default_ind = [param['choices'].index(self.prefs[param_name])]
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
                # params that just need a textbox, will attempt to be coerced
                # in unfold_values with ast.literal_eval.
                # eg. type in ('str', 'int', 'list', 'float')
                # try to get default from prefs, otherwise use the hardcoded default if present. otherwise blank
                if param_name in self.prefs.keys():
                    default = self.prefs[param_name]
                else:
                    try:
                        default = param['default']
                    except KeyError:
                        default = ''

                widget = self.add(nps.TitleText, name=param['text'], value=str(default))

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

    def afterEditing(self):
        self.parentApp.next_form_in_path(self)

# --------------------------------------------------
# individual forms
# --------------------------------------------------

class Hardware_Form(nps.FormWithMenus, Autopilot_Form):
    NAME = "HARDWARE"
    DESCRIPTION = "Configure Hardware Objects"

    def __init__(self, *args, **kwargs):
        self.input = odict()
        self.altrely = 4
        super(Hardware_Form, self).__init__(*args, **kwargs)


    def create(self):
        self.add(nps.FixedText, value="Use the ctrl+X menu to add new hardware", editable=False, color="VERYGOOD")

        # hardware_objs = self.list_hardware()
        hardware_objs = autopilot.get_hardware()
        # make dict, grouping by module
        hardware_dict = {}
        for hw_class in hardware_objs:
            module_name = hw_class.__module__.split('.')[-1]
            if module_name not in hardware_dict.keys():
                hardware_dict[module_name] = []
            hardware_dict[module_name].append(hw_class)

        for module, hardware_classes in hardware_dict.items():

            mod_menu = self.add_menu(module)
            for class_name in hardware_classes:
                mod_menu.addItem(text=class_name.__name__,
                                 onSelect=self.add_hardware,
                                 arguments=[class_name])

    def add_hardware(self, class_name):
        #self.nextrely = 1
        self.DISPLAY()

        # import the class
        if isinstance(class_name, str):
            hw_class = autopilot.get_hardware(class_name)
        else:
            hw_class = class_name
            class_name = hw_class.__name__
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

        module = hw_class.__module__.split('.')[-1]
        MODULE = module.upper()
        # create title and input widgets for arguments

        #pdb.set_trace()

        self.add(nps.FixedText,
                 value="{}.{}".format(module, class_name),
                 rely=self.altrely,
                 editable=False,
                 color="VERYGOOD")

        self.altrely+=1

        hw_widgets = {}
        hw_widgets['type'] = "{}.{}".format(module, class_name)
        for sig in sigs:
            if sig[1] is None:
                sig = (sig[0], '')

            hw_widgets[sig[0]] = self.add(nps.TitleText,
                                          name=sig[0],
                                          value=str(sig[1]),
                                          rely=self.altrely)

            self.altrely+=1
        self.altrely+=1

        if MODULE not in self.input.keys():
            self.input[MODULE] = []

        self.input[MODULE].append(hw_widgets)


class Agent_Form(nps.Form):
    NAME="AGENT"
    DESCRIPTION = "Select an Agent"

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

        if self.input['AGENT'].value[0] == 0:
            agent_name = "TERMINAL"
        elif self.input['AGENT'].value[0] == 1:
            agent_name = 'PILOT'
        elif self.input['AGENT'].value[0] == 2:
            agent_name = 'CHILD'
        else:
            self.parentApp.setNextForm(None)
            return

        self.parentApp.agent = agent_name
        self.parentApp.path = self.parentApp.PATHS[agent_name]
        self.parentApp.next_form_in_path(self)


class Directory_Form(Autopilot_Form):
    NAME='DIRECTORIES'
    DESCRIPTION = "Configure directory structure"

    def create(self):
        self.add(nps.FixedText, value="Directory Structure", editable=False, color="VERYGOOD")
        self.populate_form(DIRECTORY_STRUCTURE)


class Common_Form(Autopilot_Form):
    NAME="COMMON"
    DESCRIPTION = "Configure common prefs"
    def create(self):
        self.add(nps.FixedText, value="Common Prefs", editable=False, color="VERYGOOD")
        self.populate_form(BASE_PREFS)


class Scripts_Form(Autopilot_Form):
    NAME="SCRIPTS"
    DESCRIPTION = "Choose environment configuration scripts to run"
    def create(self):
        self.populate_form(SCRIPTS)


class Pilot_Config_Form_1(Autopilot_Form):
    NAME="PILOT"
    DESCRIPTION = "Configure Pilot-specific prefs"
    def create(self):
        self.add(nps.FixedText, value='Pilot Prefs', editable=False, color="VERYGOOD")
        self.populate_form(PILOT_PREFS)
        self.add(nps.FixedText, value='Lineage Prefs', editable=False, color="VERYGOOD")
        self.populate_form(LINEAGE_PREFS)
        self.add(nps.FixedText, value='Audio Prefs', editable=False, color="VERYGOOD")
        self.populate_form(AUDIO_PREFS)


class Terminal_Form(Autopilot_Form):
    NAME="TERMINAL"
    DESCRIPTION = "Configure Terminal-specific prefs"
    def create(self):
        self.add(nps.FixedText, value='Terminal Prefs', editable=False, color="VERYGOOD")
        self.populate_form(TERMINAL_PREFS)

# --------------------------------------------------
# Combined app object
# --------------------------------------------------

class Autopilot_Setup(nps.NPSAppManaged):
    PATHS = {
        'TERMINAL': ['AGENT', 'DIRECTORIES', 'COMMON', 'TERMINAL', 'SCRIPTS'],
        'PILOT': ['AGENT', 'DIRECTORIES', 'COMMON', 'PILOT', 'HARDWARE', 'SCRIPTS']
    }
    """
    Allow different agents to have different paths through setup
    
    For each Agent, a list of forms to call in order using :meth:`.next_form_in_path`
    
    Setup always starts with the :class:`.Agent_Form` which populates the :attr:`.agent` and :attr:`.path` attributes
    """

    def __init__(self, prefs):
        super(Autopilot_Setup, self).__init__()
        self.prefs = prefs
        self.agent = "" # type: str
        self.forms = {} # type: typing.Dict[str, Autopilot_Form]
        self.path = []



    def onStart(self):
        """
        Add forms by gathering subclasses of :class:`.Autopilot_Form`

        Set the :class:`.Agent_Form` as the ``'MAIN'`` form -- opened first.
        """
        self.forms['AGENT'] = self.addForm('MAIN', Agent_Form, name="Select Agent", prefs=self.prefs)

        # then iterate through subclasses and add
        for form_class in Autopilot_Form.__subclasses__():
            self.forms[form_class.NAME] = self.addForm(form_class.NAME, form_class, name=form_class.DESCRIPTION, prefs=self.prefs)

    def next_form_in_path(self, calling_form: Autopilot_Form):
        """
        Call :meth:`.setNextForm` to set the next form in the :attr:`.path`
        :attr:`.path` and :attr:`.agent` will be set by :class:`.Agent_Form`

        Args:
            calling_form (:class:`.Autopilot_Form`): The currently active form
        """
        # path = self.PATHS[self.agent]
        next_ind = self.path.index(calling_form.NAME) + 1
        if next_ind >= len(self.path):
            self.setNextForm(None)
        else:
            self.setNextForm(self.path[next_ind])

    def unpack_prefs(self):
        """
        Unpack the prefs from the forms and return them complete

        Returns:
            dict - your prefs!
        """

        out_prefs = odict()
        for form_name in self.path:
            # skip scripts, it's not exactly prefs
            if form_name == 'SCRIPTS':
                continue

            new_prefs = odict({k: unfold_values(v) for k, v in self.forms[form_name].input.items()})

            # hardware needs a little extra unpacking
            if form_name == "HARDWARE":
                hardware = {}
                for hardware_group, hardware_list in new_prefs.items():
                    hardware[hardware_group] = {}
                    for hardware_config in hardware_list:
                        hardware[hardware_group][hardware_config['name']] = hardware_config
                out_prefs['HARDWARE'] = hardware
            else:
                out_prefs.update(new_prefs)

        return out_prefs

    @property
    def active_scripts(self) -> typing.List[str]:
        """
        Get list of scripts that were selected to be run

        Returns:
            list:  script_name: script_commands
        """
        out_scripts = []

        script_names = odict({k: unfold_values(v) for k, v in self.forms['SCRIPTS'].input.items()})
        for script_name, result in script_names.items():
            if script_name in SCRIPTS.keys() and result == 1:
                out_scripts.append(script_name)

        return out_scripts


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

