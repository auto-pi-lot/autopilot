import os
import logging
import re
from pathlib import Path
from logging.handlers import RotatingFileHandler
from threading import Lock
import warnings

from autopilot import prefs

_LOGGERS = [] # type: list
"""
List of instantiated loggers, used in :func:`.init_logger` to return existing loggers without modification
"""

_INIT_LOCK = Lock() # type: Lock


def init_logger(instance=None, module_name=None, class_name=None, object_name=None) -> logging.Logger:
    """
    Initialize a logger

    Loggers are created such that...

    * There is one logger per module (eg. all gpio objects will log to hardware.gpio)
    * If the passed object has a ``name`` attribute, that name will be prefixed to its log messages in the file
    * The loglevel for the file handler and the stdout is determined by ``prefs.get('LOGLEVEL')``, and if none is provided ``WARNING`` is used by default
    * logs are rotated according to ``prefs.get('LOGSIZE')`` (in bytes) and ``prefs.get('LOGNUM')`` (number of backups of ``prefs.get('LOGSIZE')`` to cycle through)

    Logs are stored in ``prefs.get('LOGDIR')``, and are formatted like::

        "%(asctime)s - %(name)s - %(levelname)s : %(message)s"

    Loggers can be initialized either by passing an object to the first ``instance`` argument, or
    by specifying any of ``module_name`` , ``class_name`` , or ``object_name`` (at least one must be specified)
    which are combined with periods like ``module.class_name.object_name``

    Args:
        instance: The object that we are creating a logger for! if None, at least one of ``module, class_name, or object_name`` must be passed
        module_name (None, str): If no ``instance`` passed, the module name to create a logger for
        class_name (None, str): If no ``instance`` passed, the class name to create a logger for
        object_name (None, str): If no ``instance`` passed, the object name/id to create a logger for

    Returns:
        :class:`logging.logger`
    """

    # --------------------------------------------------
    # gather variables
    # --------------------------------------------------

    if instance is not None:
        # get name of module_name without prefixed autopilot
        # eg passed autopilot.hardware.gpio.Digital_In -> hardware.gpio
        # filtering leading 'autopilot' from string
        module_name = instance.__module__.lstrip('autopilot.')
        class_name = instance.__class__.__name__

        # get name of object if it has one
        if hasattr(instance, 'name'):
            object_name = str(instance.name)
        elif hasattr(instance, 'id'):
            object_name = str(instance.id)
        else:
            object_name = None

        # --------------------------------------------------
        # check if logger needs to be made, or exists already
        # --------------------------------------------------
    elif not any((module_name, class_name, object_name)):
        raise ValueError('Need to either give an object to create a logger for, or one of module_name, class_name, or object_name')


    # get name of logger to get
    logger_name_pieces = [v for v in (module_name, class_name, object_name) if v is not None]
    logger_name = '.'.join(logger_name_pieces)

    # trim __ from logger names, linux don't like to make things like that
    # re.sub(r"^\_\_")

    # --------------------------------------------------
    # if new logger must be made, make it, otherwise just return existing logger
    # --------------------------------------------------

    # use a lock to prevent loggers from being double-created, just to be extra careful
    with globals()['_INIT_LOCK']:
        logger = logging.getLogger(logger_name)

        # check if something starting with module_name already exists in loggers
        MAKE_NEW = False
        if not any([test_logger == module_name for test_logger in globals()['_LOGGERS']]):
            MAKE_NEW = True

        if MAKE_NEW:
            loglevel = getattr(logging, prefs.get('LOGLEVEL'))
            logger.setLevel(loglevel)

            # make formatter that includes name
            log_formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s : %(message)s")

            ## file handler
            # base filename is the module_name + '.log
            base_filename = os.path.join(prefs.get('LOGDIR'), module_name + '.log')
            try:
                fh = RotatingFileHandler(
                    base_filename,
                    mode='a',
                    maxBytes=int(prefs.get('LOGSIZE')),
                    backupCount=int(prefs.get('LOGNUM'))
                )
            except PermissionError as e:
                # catch permissions errors, try to chmod our way out of it
                try:
                    for mod_file in Path(base_filename).parent.glob(f"{Path(base_filename).stem}*"):
                        os.chmod(mod_file, 0o777)
                        warnings.warn(f'Couldnt access {mod_file}, changed permissions to 0o777')

                    fh = RotatingFileHandler(
                        base_filename,
                        mode='a',
                        maxBytes=int(prefs.get('LOGSIZE')),
                        backupCount=int(prefs.get('LOGNUM'))
                    )
                except Exception as f:
                    raise PermissionError(f'Couldnt open logfile {base_filename}, and couldnt chmod our way out of it.\n'+'-'*20+f'\ngot errors:\n{e}\n\n{f}\n'+'-'*20)

            fh.setLevel(loglevel)
            fh.setFormatter(log_formatter)
            logger.addHandler(fh)

            # console stream handler with same loglevel
            ch = logging.StreamHandler()
            ch.setLevel(loglevel)
            ch.setFormatter(log_formatter)
            logger.addHandler(ch)





            ## log creation
            logger.info(f'logger created: {logger_name}')
            globals()['_LOGGERS'].append(module_name)

        else:
            logger.info(f'logger reconstituted: {logger_name}')

    return logger