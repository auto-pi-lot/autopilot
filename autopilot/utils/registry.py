"""
Registry for programmatic access to autopilot classes and plugins

When possible, rather than importing and using an object directly, access it
using the ``get`` methods in this module. This makes it possible for plugins to
be integrated across the system.

"""
import pdb
from enum import Enum
import multiprocessing as mp
from typing import TYPE_CHECKING, Union, Optional, List
import inspect


from autopilot.utils.common import find_class, recurse_subclasses, list_classes
from autopilot.utils.plugins import import_plugins, _IMPORTED
from autopilot import prefs
from autopilot.core.loggers import init_logger
if TYPE_CHECKING:
    from autopilot.hardware import Hardware
    from autopilot.tasks import Task

_IMPORT_LOCK = mp.Lock()
"""
Lock to ensure that another call to :func:`.registry.get` doesn't call :func:`.utils.plugins.import_plugins` twice
"""


class REGISTRIES(str, Enum):
    """
    Types of registries that are currently supported,
    ie. the possible values of the first argument of :func:`.registry.get`

    Values are the names of the autopilot classes that are searched for
    inheriting classes, eg. ``HARDWARE == "autopilot.hardware.Hardware"`` for :class:`autopilot.Hardware`
    """
    HARDWARE = "autopilot.hardware.Hardware"
    TASK = "autopilot.tasks.Task"

# TODO: Update return type hint when unified Autopilot Object class made
def get(base_class:Union[REGISTRIES,str, type], class_name:Optional[str]=None, plugins:bool=True, ast:bool=True) -> Union["Task", "Hardware", List["Task"], List["Hardware"]]:
    """
    Get an autopilot object.

    Args:
        base_class (:class:`.REGISTRIES`, str, type): Class to search its subclasses for the indicated object. One of the values in the :class:`.REGISTRIES` enum,
           or else one of its keys (eg. ``'HARDWARE'``). If given a full module.ClassName string
           (eg. ``"autopilot.tasks.Task"``) attempt to get the indicated object. If given an object,
           use that.
       class_name (str, None): Name of class that inherits from base_class that is to be returned.
           if ``None`` (default), return all found subclasses of ``base_class``
       plugins (bool): If ``True`` (default), ensure contents of PLUGINDIR are loaded (with :func:`~.utils.plugins.import_plugins`)
           and are included in results. If ``False``, plugins are not explicitly imported, but if any
           have been imported elsewhere, they will be included anyway because we can't control all the
           different ways to subclass in Python.
       ast (bool): If ``True`` (default), if an imported object isn't found that matches ``class_name``,
           parse the syntax trees of submodules of ``base_class`` with :func:`.utils.common.list_classes`
           without importing to try and find it. If a match is found, it is imported and checked whether
           or not it is indeed a subclass of the ``base_class``. if ``False``, do not parse ast trees
           (will miss any modules that aren't already imported).

    Returns:
        Either the requested items, or a list of all the relevant items
    """
    logger = init_logger(module_name='registry', class_name='get')

    if isinstance(base_class, REGISTRIES):
        base_class = base_class.value
    elif isinstance(base_class, str) and base_class.upper() in REGISTRIES.__members__.keys():
        base_class = REGISTRIES[base_class.upper()].value
    elif base_class in REGISTRIES.__members__.values():
        # already have the value, which is what we use to get the object
        pass
    elif inspect.isclass(base_class):
        # fine! we'll just use it
        pass
    else:
        logger.warning(f'Attempting to get subclasses from {base_class}, but it isn\'t in the REGISTRIES enum.\nPossible Values:\n{REGISTRIES.__members__}')

    if inspect.isclass(base_class):
        cls = base_class
    else:
        # get the class indicated by the base_class string
        cls = find_class(base_class)

    # load the contents of the plugin directory if we are supposed to
    # and if we haven't yet
    if not plugins or prefs.get('AUTOPLUGIN') is False:
        # if given explicit negative override, dont do it
        pass
    else:
        with globals()['_IMPORT_LOCK']:
            if not _IMPORTED.value:
                _ = import_plugins()

    # find subclasses!
    subclasses = recurse_subclasses(cls)
    # if we have found one among the imported classes, return that
    if class_name is not None:
        for subclass in subclasses:
            if subclass.__name__ == class_name:
                logger.debug(f"Found {subclass} as subclass of {cls} in module {subclass.__module__}")
                return subclass

    # if we haven't found the class yet and are asked to parse the ast tree, do it!
    if ast:
        ast_subclasses = list_classes(cls.__module__)
        for subclass in ast_subclasses:
            # if we were asked to get a specific class...
            if class_name is not None:
                if subclass[0] == class_name:
                    # import it and check that it is a subclass!
                    imported_subclass = find_class(subclass[1])
                    if issubclass(imported_subclass, cls):
                        logger.debug(f"Found {imported_subclass} as subclass of {cls} in {subclass[1]}")
                        return imported_subclass
            else:
                # get and import everything!
                try:
                    imported_subclass = find_class(subclass[1])
                    if issubclass(imported_subclass, cls):
                        subclasses.append(imported_subclass)
                except ImportError as e:
                    logger.warning(f'Exception importing requested class {subclass[1]}, got exception:\n{e}')

    # if all the found classes were requested, return them.
    if class_name is None:
        return sorted(list(set(subclasses)),
                      key=lambda subclass: ''.join([
                          subclass.__module__,
                          subclass.__name__
                      ]))

    # if we've gotten this far then we haven't found it :(
    ex_text = f"Could not find subclass of {cls} with name {class_name}!"
    logger.exception(ex_text)
    raise ValueError(ex_text)


def get_hardware(class_name:Optional[str] = None, plugins:bool = True, ast:bool = True) -> Union["Hardware", List["Hardware"]]:
    """
    Get a hardware class by name.

    Alias for :func:`.registry.get`

    Args:
        class_name (str): Name of hardware class to get
        plugins (bool): If ``True`` (default) ensure plugins are loaded and return
            from them. see :func:`.registry.get` for more details about the
            behavior of this argument
        ast (bool): If ``True`` (default) parse the syntax tree of all modules
            within :mod:`~autopilot.hardware`. see :func:`.registry.get` for more details about the
            behavior of this argument

    Returns:
        :class:`~autopilot.hardware.Hardware`
    """
    return get(REGISTRIES.HARDWARE, class_name=class_name, plugins=plugins, ast=ast)


def get_task(class_name:Optional[str] = None, plugins:bool = True, ast:bool = True) -> Union["Task", List["Task"]]:
    """
    Get a task class by name.

    Alias for :func:`.registry.get`

    Args:
        class_name (str): Name of task class to get
        plugins (bool): If ``True`` (default) ensure plugins are loaded and return
            from them. see :func:`.registry.get` for more details about the
            behavior of this argument
        ast (bool): If ``True`` (default) parse the syntax tree of all modules
            within :mod:`~autopilot.tasks`. see :func:`.registry.get` for more details about the
            behavior of this argument

    Returns:
        :class:`~autopilot.tasks.Task`
    """
    return get(REGISTRIES.TASK, class_name=class_name, plugins=plugins, ast=ast)






