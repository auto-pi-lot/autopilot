"""
Data transformations.

Composable transformations from one representation of data to another.
Used as the lubricant and glue between hardware objects. Some hardware objects
disagree about the way information should be represented -- eg. cameras are very
partial to letting position information remain latent in a frame of a video, but
some other object might want the actual ``[x,y]`` coordinates. Transformations help
negotiate (but don't resolve their irreparably different worldviews :( )

Transformations are organized by modality, but this API is quite immature.

Transformations have a ``process`` method that accepts and returns a single object.
They must also define the format of their inputs and outputs (``format_in``
and ``format_out``). That API is also a sketch.

The :meth:`~.Transform.__add__` method allows transforms to be combined, eg.::

    from autopilot import transform as t
    transform_me = t.Image.DLC('model_directory')
    transform_me += t.selection.DLCSlice('point')
    transform_me.process(frame)
    # ... etcetera

.. todo::

    This is a first draft of this module and it purely synchronous at the moment. It will be expanded to ...
    * support multiple asynchronous processing rhythms
    * support automatic value coercion
    * make recursion checks -- make sure a child hasn't already been added to a processing chain.
    * idk participate at home! list your own shortcomings of this module, don't be shy it likes it.
"""

import typing
import autopilot
from autopilot.transform.transforms import Transform
from autopilot.transform import image, geometry, logical, selection, units

IMPORTED = False


def make_transform(transforms: typing.Union[typing.List[dict],typing.Tuple[dict]]) -> Transform:
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
            if len(t['transform'].split('.'))>1:
                module, classname = t['transform'].split('.')
                mod = __import__(f"autopilot.transform.{module}", fromlist=[classname])
                tfm_class = getattr(mod, classname)
            else:
                tfm_class = autopilot.get('transform', t['transform'])

        elif issubclass(t['transform'], Transform):
            tfm_class = t['transform']
        else:
            raise ValueError(f'Could not get transform from {t["transform"]}, need a name of a Transform class, or the class itself')

        transform = tfm_class(
            *t.get('args', []),
            **t.get('kwargs', {})
        )
        if ret is None:
            ret = transform
        else:
            ret = ret + transform

    return ret
