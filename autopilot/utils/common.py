"""
Generic utility functions that are used in multiple places in the library that
for now don't have a clear other place to be
"""

import inspect
import importlib
import json
import sys
from pathlib import Path
import pkgutil
import ast
import typing
from typing import Optional, List
from threading import Thread
import numpy as np


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
    ret_classes = []

    if not inspect.ismodule(module):
        module = importlib.import_module(module)

    # First get any members that are defined within the base __init__.py module itself
    base_classes = inspect.getmembers(module, inspect.isclass)
    ret_classes.extend([
        (bc[0], ".".join([bc[1].__module__, bc[1].__name__]))
        for bc in base_classes
    ])

    # get the parent directory name and module name, we'll use that
    mod_path = Path(module.__file__).resolve().parent
    if '__init__' not in str(Path(module.__file__)):
        mod_name = ".".join(module.__name__.split('.')[:-1])
    else:
        mod_name = module.__name__

    # get names of module files within top-level package
    submodules = [mod for _, mod, _ in pkgutil.iter_modules([str(mod_path)])]
    submod_paths = [(mod_path / mod).with_suffix('.py') for mod in submodules]

    # parse the files to get the names of the classes
    for submod_name, submod in zip(submodules, submod_paths):
        with open(submod, 'r') as submod_f:
            submod_ast = ast.parse(submod_f.read())

        ret_classes.extend([
            (n.name, '.'.join([mod_name, submod_name, n.name]))
            for n in submod_ast.body
            if isinstance(n, ast.ClassDef)
        ])

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


class ReturnThread(Thread):
    """
    Thread whose .join() method returns the value from the function
    thx to https://stackoverflow.com/a/6894023
    """
    def __init__(self, group=None, target=None, name=None,
                 args=(), kwargs={}, Verbose=None):
        Thread.__init__(self, group, target, name, args, kwargs, Verbose)
        self._return = None
    def run(self):
        if self._Thread__target is not None:
            self._return = self._Thread__target(*self._Thread__args,
                                                **self._Thread__kwargs)
    def join(self, timeout=None):
        Thread.join(self, timeout)

        return self._return


def list_subjects(pilot_db=None):
    """
    Given a dictionary of a pilot_db, return the subjects that are in it.

    Args:
        pilot_db (dict): a pilot_db. if None tried to load pilot_db with :method:`.load_pilotdb`

    Returns:
        subjects (list): a list of currently active subjects

    """

    if pilot_db is None:
        pilot_db = load_pilotdb()

    subjects = []
    for pilot, values in pilot_db.items():
        if 'subjects' in values.keys():
            subjects.extend(values['subjects'])

    return subjects


def load_pilotdb(file_name=None, reverse=False):
    """
    Try to load the file_db

    Args:
        reverse:
        file_name:

    Returns:

    """

    if file_name is None:
        file_name = '/usr/autopilot/pilot_db.json'

    with open(file_name) as pilot_file:
        pilot_db = json.load(pilot_file)

    if reverse:
        # simplify pilot db
        pilot_db = {k: v['subjects'] for k, v in pilot_db.items()}
        pilot_dict = {}
        for pilot, subjectlist in pilot_db.items():
            for ms in subjectlist:
                pilot_dict[ms] = pilot
        pilot_db = pilot_dict

    return pilot_db


def coerce_discrete(df, col, mapping={'L':0, 'R':1}):
    """
    Coerce a discrete/string column of a pandas dataframe into numeric values

    Default is to map 'L' to 0 and 'R' to 1 as in the case of Left/Right 2AFC tasks

    Args:
        df (:class:`pandas.DataFrame`) : dataframe with the column to transform
        col (str):  name of column
        mapping (dict): mapping of strings to numbers

    Returns:
        df (:class:`pandas.DataFrame`) : transformed dataframe

    """

    for key, val in mapping.items():
        df.loc[df[col]==key,col] = val

    # if blanks, warn and remove
    if '' in df[col].unique():
        n_blanks = sum(df[col]=='')
        Warning('{} blank rows detected, removing.'.format(n_blanks))
        df.drop(df.index[df[col]==''], axis=0, inplace=True)

    df = df.astype({col:float})
    return df


def find_key_recursive(key, dictionary):
    """
    Find all instances of a key in a dictionary, recursively.

    Args:
        key:
        dictionary:

    Returns:
        list
    """
    for k, v in dictionary.items():
        if k == key:
            yield v
        elif isinstance(v, dict):
            for result in find_key_recursive(key, v):
                yield result
        elif isinstance(v, list):
            for d in v:
                for result in find_key_recursive(key, d):
                    yield result

def find_key_value(dicts:typing.List[dict], key:str, value:str, single=True):
    """
    Find an entry in a list of dictionaries where dict[key] == value.

    Args:
        dicts ():
        key ():
        value ():
        single (bool): if ``True`` (default), raise an exception if multiple
            results are matched
    """
    if not all([isinstance(item, dict) for item in dicts]):
        raise ValueError(f"Pass me a list of dicts! got {dicts}")

    matches = [match for match in dicts if match[key] == value]

    if len(matches)>1 and single:
        raise IndexError(f"Multiple matches found for key: {key}, value: {value}, got:\n{matches}")
    elif len(matches) == 1:
        matches = matches[0]

    return matches

def walk_dicts(adict, keys:Optional[List]=None) -> tuple:
    """
    Recursively yield key/value pairs, returning keys as tuples corresponding to the
    recursive keys in the dict

    Args:
        adict (dict): dict to walk over

    Yields:
        tuple of key value pairs
    """
    for k, v in adict.items():
        if keys is not None:
            keys.append(k)
        if isinstance(v, dict):
            walk_dicts(v, keys)
        else:
            yield k, v

def flatten_dict(nested:dict, keys=(), skip=()) -> dict:
    """
    Flatten a nested dictionary to a dictionary with tuples of the nested keys

    Similar to :func:`.walk_dicts`, excepts not a generator, and returns a flattened
    dictionary rather than a series of tuples.

    Examples:
        ::

            nested_dict = {
                'a': 1,
                'b': {
                    'c': 2,
                    'd': {
                        'e': 3
                    },
                'f': 4
                }
            }
            flatten_dict(nested_dict)
            {
                ('a',): 1,
                ('b', 'c'): 2,
                ('b', 'd', 'e'): 3,
                ('b', 'f'): 4
            }


    Args:
        nested (dict): A nested dictionary
        keys (tuple): A tuple of keys used in the recursive function to create the returned key
        skip (tuple[str]): Tuple of keys to skip flattening

    Returns:
        dict: A flattened dictionary

    """
    flat = {}
    if isinstance(nested, dict):
        for key, value in nested.items():
            if key in skip:
                if not isinstance(key, tuple):
                    key = (key,)
                flat.update({key:value})
            else:
                flat.update(flatten_dict(value, keys + (key,), skip))
        return flat
    else:
        return {keys:nested}

class NumpyEncoder(json.JSONEncoder):
    """
    Allow json serialization of objects containing numpy arrays.

    Use like ``json.dump(obj, fp, cls=NumpyEncoder)``

    Deserialize with :class:`.NumpyDecoder`

    References:
        * https://stackoverflow.com/a/49677241/13113166
        * https://github.com/mpld3/mpld3/issues/434#issuecomment-340255689
        * https://gist.github.com/massgh/297a73f2dba017ffd28dbc34b9a40e90
    """

    def default(self, obj):
        if isinstance(obj, (np.int_, np.intc, np.intp, np.int8,
                            np.int16, np.int32, np.int64, np.uint8,
                            np.uint16, np.uint32, np.uint64)):
            return int(obj)
        elif isinstance(obj, (np.float_, np.float16, np.float32,
                              np.float64)):
            return float(obj)
        elif isinstance(obj, (np.ndarray,)):  #### This is the fix
            return {
                "_kind_": "ndarray",
                "_value_": obj.tolist()
            }
        return json.JSONEncoder.default(self, obj)

class NumpyDecoder(json.JSONDecoder):
    """
    Allow json deserialization of objects containing numpy arrays.

    Use like ``json.load(fp, cls=NumpyDecoder)``

    Serialize with :class:`.NumpyEncoder`

    References:
        * https://stackoverflow.com/a/49677241/13113166
        * https://github.com/mpld3/mpld3/issues/434#issuecomment-340255689
        * https://gist.github.com/massgh/297a73f2dba017ffd28dbc34b9a40e90
    """

    def __init__(self, *args, **kwargs):
        json.JSONDecoder.__init__(self, object_hook=self.object_hook, *args, **kwargs)

    def object_hook(self, obj):
        try:
            kind = obj['_kind_']
            if kind == 'ndarray':
                    obj = np.array(obj['_value_'])

        except (TypeError, KeyError):
            # normal, just return obj
            pass

        return obj