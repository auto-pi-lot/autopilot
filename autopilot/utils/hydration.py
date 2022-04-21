"""
Functions to be able to make sending and recreating autopilot objects by sending compressed
representations of their instantiation.

Examples:

    >>> import autopilot
    >>> from pprint import pprint

    >>> Noise = autopilot.get('sound', 'Noise')
    >>> a_noise = Noise(duration=1000, amplitude=0.01, fs=44100)

    >>> dehydrated_noise = dehydrate(a_noise)
    >>> pprint(dehydrated_noise)
    {'class': 'autopilot.stim.sound.sounds.Noise',
     'kwargs': {'amplitude': 0.01,
                'channel': None,
                'duration': 1000,
                'fs': 44100}}

    >>> b_noise = hydrate(dehydrated_noise)

    >>> a_noise
    <autopilot.stim.sound.sounds.Noise object at 0x12d76f400>
    >>> b_noise
    <autopilot.stim.sound.sounds.Noise object at 0x12d690310>

    >>> a_noise._introspect['__init__']
    {'fs': 44100, 'duration': 1000, 'amplitude': 0.01, 'channel': None}
    >>> b_noise._introspect['__init__']
    {'fs': 44100, 'duration': 1000, 'amplitude': 0.01, 'channel': None}


"""

from autopilot.utils.common import find_class


def dehydrate(obj) -> dict:
    """
    Get a dehydrated version of an object that has its ``__init__`` method wrapped with
     :class:`.utils.decorators.Introspect` for sending across the wire/easier reinstantiation and provenance.

    Args:
        obj: The (instantiated) object to dehydrate

    Returns:
        dict: a dictionary that can be used with :func:`.hydrate`, of the form::

            {
                'class': 'autopilot.submodule.Class',
                'kwargs': {'kwarg_1': 'value1', ... }
            }
    """
    if not hasattr(obj, '_introspect') or not obj._introspect.get('__init__', False):
        raise RuntimeError(f'Could not dehydrate object, as its __init__ method has not been wrapped with Introspect')

    module = obj.__class__.__module__
    classname = obj.__class__.__name__
    return {
        'class': '.'.join([module, classname]),
        'kwargs': obj._introspect['__init__']
    }

def hydrate(obj_dict:dict):
    """
    Rehydrate an object description from :func:`.dehydrate`
    """
    if 'class' not in obj_dict.keys() and 'kwargs' not in obj_dict.keys():
        raise ValueError('Dictionary was not created by dehyrating an object!')

    _class = find_class(obj_dict['class'])
    return _class(**obj_dict['kwargs'])

