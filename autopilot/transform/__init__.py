"""
Data transformations.

Experimental module.

Reusable transformations from one representation of data to another.
eg. converting frames of a video to locations of objects,
or locations of objects to area labels

.. todo::

    This is a preliminary module and it purely synchronous at the moment. It will be expanded to ...
    * support multiple asynchronous processing rhythms
    * support automatic value coercion

    The following design features need to be added
    * recursion checks -- make sure a child hasn't already been added to a processing chain.
"""

import typing
from autopilot.transform import image, geometry, logical, selection, units

IMPORTED = False


def make_transform(transforms: typing.List[dict]):
    """
    Make a transform from a list of iterator specifications.



    Args:
        transforms (list): A list of :class:`Transform` s and parameterizations in the form::

            [
                {'transform': Transform,
                'args': (arg1, arg2,), # optional
                'kwargs': {'key1':'val1', ...}, # optional
                {'transform': ...}
            ]

    Returns:
        :class:`Transform`
    """

    ret = None
    for t in transforms:
        if isinstance(t['transform'], str):
            module, classname = t['transform'].split('.')
            mod = __import__(f"autopilot.transform.{module}", fromlist=[classname])
            t['transform'] = getattr(mod, classname)
        transform = t['transform'](
            *t.get('args', []),
            **t.get('kwargs', {})
        )
        if ret is None:
            ret = transform
        else:
            ret = ret + transform

    return ret