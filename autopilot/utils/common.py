"""
Generic utility functions that are used in multiple places in the library that
for now don't have a clear other place to be
"""

import inspect
import importlib
import sys
from pathlib import Path
import pkgutil
import ast
import typing


def list_classes(module) -> typing.List[typing.Tuple[str, str]]:
    """
    List all classes within a module/package without importing by parsing the syntax tree
    directly with :mod:`ast` .

    Args:
        module (module, str): either the imported module to be queried, or its name as a string.
           if passed a string, attempt to import with :func:`importlib.import_module`

    Returns:
        list of tuples [('ClassName', 'module1.module2.ClassName')] a la :func:`inspect.getmembers`
    """
    if not inspect.ismodule(module):
        module = importlib.import_module(module)

    # First get any members that are defined within the base module itself
    ret_classes = inspect.getmembers(module, inspect.isclass)

    mod_path = Path(module.__file__).resolve()
    if '__init__' in str(mod_path):
        mod_path = mod_path.parent

    # get names of modules
    submodules = [mod for _, mod, _ in pkgutil.iter_modules([mod_path])]
    submod_paths = [(mod_path / mod).with_suffix('.py') for mod in submodules]

    # parse the files to get the names of the classes
    for submod_name, submod in zip(submodules, submod_paths):
        with open(submod, 'r') as submod_f:
            submod_ast = ast.parse(submod_f.read())

        submod_classes = [n.name for n in submod_ast.body if
                          isinstance(n, ast.ClassDef)]
        for submod_class in submod_classes:
            ret_classes.append((submod_class, '.'.join([module.__name__, str(submod_name), submod_class])))

    return ret_classes


def find_class(cls_str:str):
    """
    Given a full package.module.ClassName string, return the relevant class

    Args:
        cls_str (str): a full package.module.ClassName string, like ``'autopilot.hardware.Hardware'``

    Returns:
        the class indicated by ``cls_str``
    """
    # get class and module names first by splitting off final class name
    class_name = cls_str.split('.')[-1]
    module_name = '.'.join(cls_str.split('.')[:-1])

    # import or get reference to already-imported module
    if module_name in sys.modules:
        mod = sys.modules[module_name]
    else:
        mod = importlib.import_module(module_name)

    return getattr(mod, class_name)


def recurse_subclasses(cls, leaves_only=False) -> list:
    """
    Given some class, find its subclasses recursively

    See: https://stackoverflow.com/a/17246726/13113166

    Args:
        leaves_only (bool): If True, only include classes that have no further subclasses,
            if False (default), return all subclasses.

    Returns:
        list of subclasses
    """

    all_subclasses = []

    for subclass in cls.__subclasses__():
        if leaves_only:
            if len(subclass.__subclasses__()) == 0:
                all_subclasses.append(subclass)
        else:
            all_subclasses.append(subclass)
        all_subclasses.extend(recurse_subclasses(subclass, leaves_only))

    return all_subclasses