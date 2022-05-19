import os
import logging
import re
import multiprocessing as mp
import inspect
from pathlib import Path
from logging.handlers import RotatingFileHandler
from threading import Lock
import warnings
from rich.logging import RichHandler
from dataclasses import dataclass
from datetime import datetime
from parse import parse
import typing
from typing import Literal


from autopilot.root import Autopilot_Type

from autopilot import prefs

_LOGGERS = [] # type: list
"""
List of instantiated loggers, used in :func:`.init_logger` to return existing loggers without modification
"""

_INIT_LOCK = Lock() # type: Lock

LOGLEVELS = Literal['DEBUG', 'INFO', 'WARNING', 'ERROR']

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

        module_name = instance.__module__
        if "__main__" in module_name:
            # awkward workaround to get module name of __main__ run objects
            mod_obj = inspect.getmodule(instance)
            try:
                mod_suffix  = inspect.getmodulename(inspect.getmodule(instance).__file__)
                module_name = '.'.join([mod_obj.__package__, mod_suffix])
            except AttributeError:
                # when running interactively or from a plugin, __main__ does not have __file__
                module_name = "__main__"


        module_name = re.sub('^autopilot.', '', module_name)

        class_name = instance.__class__.__name__

        # if object is running in separate process, give it its own file
        if issubclass(instance.__class__, mp.Process):
            # it should be at least 2 (in case its first spawned in its module)
            # but otherwise nocollide
            p_num = 2
            _module_name = module_name
            module_name = f"{_module_name}_{str(p_num).zfill(2)}"
            if module_name in globals()['_LOGGERS']:
                for existing_mod in globals()['_LOGGERS']:
                    if module_name in existing_mod and re.match(r'\d$', existing_mod):
                        p_num += 1

                module_name = f"{_module_name}_{str(p_num).zfill(2)}"

        # get name of object if it has one
        if hasattr(instance, 'id'):
            object_name = str(instance.id)
        elif hasattr(instance, 'name'):
            object_name = str(instance.name)
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

        # check if something starting with module_name already exists in loggers
        MAKE_NEW = False
        if not any([test_logger == module_name for test_logger in globals()['_LOGGERS']]):
            MAKE_NEW = True

        if MAKE_NEW:
            parent_logger = logging.getLogger(module_name)
            loglevel = getattr(logging, prefs.get('LOGLEVEL'))
            parent_logger.setLevel(loglevel)

            # make formatter that includes name
            log_formatter = logging.Formatter("[%(asctime)s] %(levelname)s [%(name)s]: %(message)s")

            ## file handler
            # base filename is the module_name + '.log
            base_filename = Path(prefs.get('LOGDIR')) / (module_name + '.log')

            fh = _file_handler(base_filename)
            fh.setLevel(loglevel)
            fh.setFormatter(log_formatter)
            parent_logger.addHandler(fh)

            # rich logging handler for stdout
            parent_logger.addHandler(_rich_handler())

            # if our parent is the rootlogger, disable propagation to avoid printing to stdout
            if isinstance(parent_logger.parent, logging.RootLogger):
                parent_logger.propagate = False

            ## log creation
            globals()['_LOGGERS'].append(module_name)
            parent_logger.debug(f'parent, module-level logger created: {module_name}')

        logger = logging.getLogger(logger_name)
        if logger_name not in globals()['_LOGGERS']:
        # logger.addHandler(_rich_handler())
            logger.debug(f"Logger created: {logger_name}")
            globals()['_LOGGERS'].append(logger_name)

    return logger


def _rich_handler() -> RichHandler:
    rich_handler = RichHandler(rich_tracebacks=True, markup=True)
    rich_formatter = logging.Formatter(
        "[bold green]\[%(name)s][/bold green] %(message)s",
        datefmt='[%y-%m-%dT%H:%M:%S]'
    )
    rich_handler.setFormatter(rich_formatter)
    return rich_handler

def _file_handler(base_filename: Path) -> RotatingFileHandler:
    # if directory doesn't exist, try to make it
    if not base_filename.parent.exists():
        base_filename.parent.mkdir(parents=True, exist_ok=True)

    try:
        fh = RotatingFileHandler(
            str(base_filename),
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
            raise PermissionError(
                f'Couldnt open logfile {base_filename}, and couldnt chmod our way out of it.\n' + '-' * 20 + f'\ngot errors:\n{e}\n\n{f}\n' + '-' * 20)

    return fh

# --------------------------------------------------
# Parsers and in-memory representation of logs
# --------------------------------------------------

class ParseError(RuntimeError):
    """
    Error parsing a logfile
    """

def _convert_asc_timestamp(timestamp:str) -> datetime:
    hunk, ms = timestamp.split(',')
    ms += '000'
    timestamp = '.'.join([hunk, ms])
    return datetime.strptime(timestamp, '%Y-%m-%d %H:%M:%S.%f')

@dataclass
class Log_Format:
    format: str
    """A format string parseable by ``parse``"""
    example: str
    """An example string (that allows for testing)"""
    conversions: typing.Optional[typing.Dict[str, typing.Callable]] = None
    """A dictionary matching keys in the ``format`` string to callables for post-parsing coercion"""

    def parse(self, log_entry:str) -> dict:
        if self.conversions is None:
            conversions = {}
        else:
            conversions = self.conversions

        res = parse(self.format, log_entry, conversions)
        if res is None:
            raise ParseError(f'Could not parse {log_entry} with {self.format}')
        else:
            return res.named



LOG_FORMATS = (
    Log_Format(
        format = '{timestamp:Timestamp} - {name} - {level} : {message}',
        conversions = {
            'Timestamp': _convert_asc_timestamp
        },
        example = "2022-03-07 16:56:48,954 - networking.node.Net_Node._T - DEBUG : RECEIVED: ID: _testpi_9879; TO: T; SENDER: _testpi; KEY: DATA; FLAGS: {'NOREPEAT': True}; VALUE: {'trial_num': 1197, 'timestamp': '2022-03-01T23:52:16.995387', 'frequency': 45255.0, 'amplitude': 0.1, 'ramp': 5.0, 'pilot': 'testpi', 'subject': '0895'}"
    ),
    Log_Format(
        format = '[{timestamp:Timestamp}] {level} [{name}]: {message}',
        conversions = {
            'Timestamp': _convert_asc_timestamp
        },
        example = '[2022-03-09 16:13:43,224] INFO [networking.node]: parent, module-level logger created: networking.node'
    )
)
"""
Possible formats of logging messages (to allow change over versions) as a `parse string <https://github.com/r1chardj0n3s/parse>`_
"""

MESSAGE_FORMATS = {
    'node_msg_recv': '{action}: ID: {message_id}; TO: {to}; SENDER: {sender}; KEY: {key}; FLAGS: {flags}; VALUE: {value}',
    'node_msg_sent': '{action} - ID: {message_id}; TO: {to}; SENDER: {sender}; KEY: {key}; FLAGS: {flags}; VALUE: {value}'
}
"""
Additional parsing patterns for logged messages

* ``node_msg``: Logging messages from :class:`.networking.node.Net_Node`

"""




class LogEntry(Autopilot_Type):
    """
    Single entry in a log
    """
    timestamp: datetime
    name: str
    level: LOGLEVELS
    message: typing.Union[str, dict]

    def parse_message(self, format:typing.List[str]):
        """
        Parse the message using a format string specified as a key in the :data:`.MESSAGE_FORMATS` dictionary (or a format string itself)

        replaces the :attr:`.message` attribute.

        If parsing unsuccessful, no exception is raised because there are often messages that are not parseable in the logs!

        Args:
            format (typing.List[str]): List of format strings to try!

        Returns:

        """
        if isinstance(format, str):
            format = [format]

        format = [MESSAGE_FORMATS[f]if f in MESSAGE_FORMATS.keys() else f for f in format]

        for f in format:
            result = parse(f, self.message)
            if result is not None:
                self.message = result.named
                return


    @classmethod
    def from_string(cls,
                    entry:str,
                    parse_message:typing.Optional[typing.List[str]]=None) -> 'LogEntry':
        """
        Create a LogEntry by parsing a string.

        Try to parse using any of the possible :ref:`.LOG_FORMATS`, raising a
        :class:`.ParseError` if none are successful

        Args:
            entry (str): single line of a logging file
            parse_message (Optional[str]): Parse messages with the :data:`.MESSAGE_FORMATS` key or format string

        Returns:
            :class:`.LogEntry`

        Raises:
            :class:`.ParseError` if no messages are parsed

        """
        for aformat in LOG_FORMATS:
            try:
                result = aformat.parse(entry)
            except ParseError:
                # fine, we're searching for one that works
                continue

            entry = cls(**result)
            if parse_message is not None:
                entry.parse_message(parse_message)
            return entry

        # if we haven't returned anything, raise a parse error
        raise ParseError(f'Couldnt parse entry with any known log formats: {entry}')

class Log(Autopilot_Type):
    """
    Representation of a logfile in memory
    """
    entries: typing.List[LogEntry]

    @classmethod
    def from_logfile(cls,
                     file: typing.Union[Path, str],
                     include_backups:bool = True,
                     parse_messages: typing.Optional[typing.List[str]]=None ):
        """
        Load a logfile (and maybe its backups) from a logfile location

        Args:
            file (:class:`pathlib.Path`, str): If string, converted to Path. If relative (and relative file is not found),
                then attempts to find relative to ``prefs.LOGDIR``
            include_backups (bool): if ``True`` (default), try and load all of the backup logfiles (that have .1, .2, etc appended)
            parse_messages (Optional[str]): Parse messages with the :data:`.MESSAGE_FORMATS` key or format string

        Returns:
            :class:`.Log`
        """
        file = Path(file)
        if not file.exists():
            if file.is_absolute():
                relfile = file.relative_to(prefs.get('LOGDIR'))
            else:
                relfile = Path(prefs.get('LOGDIR')) / file
            if not relfile.exists():
                raise ParseError(f"Could not find input file either as an absolute path, or path relative to LOGDIR, got path {str(file)}")
            file = relfile

        with open(file, 'r') as lfile:
            lines = lfile.readlines()
        entries = [LogEntry.from_string(e, parse_messages) for e in lines]

        if include_backups:
            subfile = file.with_suffix(file.suffix+'.1')
            while subfile.exists():
                with open(subfile, 'r') as sfile:
                    lines = sfile.readlines()
                entries.extend([LogEntry.from_string(e, parse_messages) for e in lines])
                subfile = subfile.with_suffix('.' + str(int(subfile.suffix[1:])+1))

        return cls(entries=entries)


