import pytest
from autopilot.utils.loggers import LOG_FORMATS, LogEntry, Log
from pathlib import Path

@pytest.mark.parametrize('format', LOG_FORMATS)
def test_parse_log_formats(format):
    parsed = format.parse(format.example)
    assert isinstance(parsed, dict)


@pytest.mark.parametrize('format', LOG_FORMATS)
def test_parse_log_entries(format):
    parsed = LogEntry.from_string(format.example)
    assert isinstance(parsed, LogEntry)


log_format_folders = Path(__file__).parent.resolve() / 'samples' / 'logs'
log_format_folders = list(log_format_folders.glob('*'))
@pytest.mark.parametrize('folder', log_format_folders)
def test_parse_log_folder(folder):
    """
    Test loading folders of sample log files

    .. todo::

        for now just testing if they parse (pydantic should take care of raising an exception if there are any errors)
        and will return later to check if there are any problems with the literal values of the parsed logs. just throwing
        the examples in there for now based on what I have lying around tbh

    """
    root_file = list(folder.glob('*.log'))[0]

    parsed = Log.from_logfile(root_file, include_backups=True)
    assert isinstance(parsed, Log)

