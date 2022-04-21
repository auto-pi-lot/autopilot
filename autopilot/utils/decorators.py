"""
Decorators for Autopilot classes

Add functionality to autopilot classes without entering into or depending on the inheritance hierarchy.
"""
import inspect
from functools import wraps
import typing
import warnings


class Introspect:
    """
    Decorator to be used around methods (particularly __init__) to
    store arguments given on call.

    Stores args and kwargs in
    ``self._introspect[wrapped_function.__name__] = {'kwarg_1': val_1, 'kwarg_2': val_2}``

    Note that this will unpack positional arguments into keyword arguments.
    If the topmost class is given positional arguments, they will be stored in the
    special field ``'args': [arg1,arg2,...]``


    Works by wrapping the method in such a way that ``self`` is preserved, and can
    patch into the existing MRO.

    .. note::

        This class was intended for use on ``__init__`` methods and has not been tested on
        other methods. Though they should work in theory, there may be unexpected behavior
        in introspecting across multiple frames, as the check is for whether we are within the
        calling object's calling hierarchy.

    For example, given a Superclass and a Subclass (and a mock Introspect object) like this::

        class Introspect:
            def __call__(self, func) -> typing.Callable:
                @wraps(func)
                def wrapped_fn(wrapped_self, *args, **kwargs):
                    print('2. start of introspection')
                    ret = func(wrapped_self, *args, **kwargs)
                    print('4. end of introspection')
                    return ret
                return wrapped_fn

        class Superclass:

            @Introspect()
            def __init__(self, *args, **kwargs):
                self.args = args
                self.kwargs = kwargs
                print(f"3. superclass function call")

        class Subclass(Superclass):
            def __init__(self, *args, **kwargs):
                print('1. inheriting class, pre super call')
                super(Subclass, self).__init__(*args, **kwargs)
                print('5. inheriting class, post super call')


    One would get the following output::

        >>> instance = Subclass('a', 'b', 'c')
        1. inheriting class, pre super call
        2. start of introspection
        3. superclass function call
        4. end of introspection
        5. inheriting class, post super call

    To hoist the call back up into the (potentially multiple) subclass frames,
    we use ``inspect`` and iterate through frames, grabbing their arguments, until
    we reach a frame that is no longer in our calling hierarchy.

    """

    def __call__(self, func):
        @wraps(func)
        def wrapped_fn(wrapped_self, *args, **kwargs):

            # call wrapped function, returning results
            ret = func(wrapped_self, *args, **kwargs)
            try:
                # ensure __introspect exists and store args
                if not hasattr(wrapped_self, '_introspect'):
                    wrapped_self._introspect = {}

                # combine the kwargs we receive with those we introspect from inheriting classes
                __our_kwargs = {**kwargs}
                __our_kwargs.update(self.__inspect_args(wrapped_self))
                if args:
                    __our_kwargs['args'] = args

                # store in this method's name
                wrapped_self._introspect[func.__name__] = __our_kwargs
            except Exception as e:
                warnings.warn(f'Could not introspect arguments, got exception {e}')
            finally:
                return ret

        return wrapped_fn

    def __inspect_args(self, wrapped_self):
        # pop out two layers in the stack to get to the calling method,
        # then continue traversing stack until self is no longer present
        # or doesn't match us
        calling_args = {}
        for i, frame_info in enumerate(inspect.stack()[2:]):
            lox = inspect.getargvalues(frame_info.frame).locals

            # break if we've reached an object that isn't in the
            # inheritance tree of our wrapped object.
            if not lox.get('self', False) is wrapped_self:
                break

            _args = inspect.getargvalues(frame_info.frame).locals
            # filter meta-kwargs
            _args = {
                k: v for k, v in lox.items() if k not in (
                    'self', 'args', 'kwargs', '__class__'
                )
            }
            calling_args.update(_args)
        return calling_args


