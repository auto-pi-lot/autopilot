"""
Utility functions for handling plugins, eg. importing, downloading, listing, confirming, etc.
"""
import sys
import inspect
import importlib
from typing import Optional
from pathlib import Path
from multiprocessing import Value
from ctypes import c_bool
from collections import OrderedDict as odict

from autopilot.utils.loggers import init_logger
from autopilot import prefs
from autopilot.utils import wiki

_IMPORTED = Value(c_bool, False)

def import_plugins(plugin_dir:Optional[Path]=None) -> dict:
    """
    Import all plugins in the plugin (or supplied) directory.

    There is no specific form for a plugin at the moment, so
    this function will recursively import all modules and packages
    within the directory.

    Plugins can then be accessed by the :func:`~.utils.registry.get` registry
    functions.

    Args:
        plugin_dir (None, :class:`pathlib.Path`): Directory to import. if
            ``None`` (default), use ``prefs.get('PLUGINDIR')``.

    Returns:
        dict: of imported objects with form {"class_name": class_object}
    """
    logger = init_logger(module_name='plugins')

    if plugin_dir is not None:
        plugin_dir = Path(plugin_dir)
    else:
        plugin_dir = Path(prefs.get('PLUGINDIR'))

    if not plugin_dir.exists():
        logger.exception(f"Plugin directory {plugin_dir} does not exist!")
        return {}

    plugins = {}

    # recursively list python files in plugin directory
    plugin_files = Path(plugin_dir).glob('**/*.py')
    for pfile in plugin_files:
        # prepend autopilot.plugins to avoid namespace clashes and make them uniformly moduled
        module_name = 'autopilot.plugins.' + inspect.getmodulename(str(pfile))

        # import module
        try:
            if module_name in sys.modules:
                mod = sys.modules[module_name]
            else:
                mod_spec = importlib.util.spec_from_file_location(module_name, pfile)
                mod = importlib.util.module_from_spec(mod_spec)
                mod_spec.loader.exec_module(mod)
                sys.modules[module_name] = mod
        except Exception as e:
            logger.exception(f'plugin file {str(pfile)} could not be imported, got exception: {e}')
            continue

        # get the imported modules and check if they're one of ours
        # filter for classes and then for classes that are declared in the plugin
        # module itself
        members = inspect.getmembers(mod, inspect.isclass)
        members = [member for member in members if member[1].__module__ == module_name]

        # store in the plugin dictionary to be returned,
        for member in members:
            # if a plugin object with the same name was already found, warn the user and don't overwrite
            if member[0] in plugins.keys():
                logger.warning(f'Conflicting plugin object names, importing both but only returning first found: {member[0]}\nfound first in: {plugins[member[0]]}\nand now in: {member[1].__module__}')
                continue
            plugins[member[0]] = member[1]

    globals()['_IMPORTED'].value = True

    return plugins



def unload_plugins():
    """
    Un-import imported plugins (mostly for testing purposes)
    """
    mods = [mod for mod in sys.modules if 'autopilot.plugins' in mod]
    for mod in mods:
        del sys.modules[mod]
    _IMPORTED.value = False


def list_wiki_plugins():
    """
    List plugins available on the wiki using :func:`.utils.wiki.ask`

    Returns:
        dict: {'plugin_name': {'plugin_prop':'prop_value',...}
    """

    plugins = wiki.ask(filters="[[Category:Autopilot Plugin]]",
             properties=[
                 'Created By',
                 'Has Description',
                 'For Autopilot Version',
                 'Has Git Repository',
                 'Has Contributor',
                 'Is Autopilot Plugin Type',
                 'Controls Hardware',
                 'Has DOI'
             ])

    ordered_plugins = []
    # reorder fields in plugins with odicts
    for plugin in plugins:
        oplugin = odict()
        for field in ('name','Has Description',
                      'Created By', 'Has Contributor',
                      'url','Has Git Repository',
                      'Has DOI',
                      'For Autopilot Version',
                      'Is Autopilot Plugin Type',
                      'Controls Hardware'):
            oplugin[field] = plugin[field]

        ordered_plugins.append(oplugin)

    return plugins



