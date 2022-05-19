"""
Utility functions to parse logging files, extracting data, separating by ID, etc.

See also :mod:`autopilot.utils.loggers` and the :class:`autopilot.utils.loggers.Log` class
"""

import typing
from pathlib import Path
from ast import literal_eval
import json

import pandas as pd

from autopilot.utils.loggers import Log

class Data_Extract(typing.TypedDict):
    header: dict
    data: pd.DataFrame

def extract_data(logfile:Path, include_backups:bool=True, output_dir:typing.Optional[Path]=None) -> typing.List[Data_Extract]:
    """
    Extract data from networking logfiles.

    Args:
        logfile (:class:`pathlib.Path`): Logfile to parse
        include_backups (bool): Include log backups (default ``True``), eg. ``logfile.log.1``, ``logfile.log.2``
        output_dir (Path): If present, save output to directory as a ``.json`` file with header information from the
            ``'START'`` message, and a ``csv`` file with the trial data

    Returns:
        typing.List[Data_Extract]: List of extracted data and headers
    """
    logfile = Path(logfile)
    log = Log.from_logfile(logfile, include_backups=include_backups, parse_messages=['node_msg_recv', 'node_msg_sent'])

    # select only parsed messages
    entries = [e for e in log.entries if isinstance(e.message, dict)]
    # select only start and data messages
    entries = [e for e in entries if e.message['key'] in ('DATA', 'START')]
    # sort entries by time
    entries.sort(key=lambda x: x.timestamp)


    # iterate through messages, splitting into epochs demarcated by a 'START' messages
    sessions = []
    this_session = []
    for e in entries:
        if  e.message['key'] == 'START' and len(this_session)>0:
            sessions.append(this_session)
            this_session = []

        this_session.append(e)

    # filter start repeats
    sessions = [s for s in sessions if len(s)>1]

    # clean up start messages into headers and data into pandas dfs
    clean_sessions = []
    for s in sessions:
        header_msg = s[0]
        assert header_msg.message['key'] == 'START'

        task = literal_eval(header_msg.message['value'])
        subject, pilot, session = task['subject'], task['pilot'], task['session']
        del task['subject']
        del task['pilot']
        del task['session']
        header = {
            'timestamp': header_msg.timestamp,
            'task': task,
            'subject': subject,
            'pilot': pilot,
            'session': session,
        }
        # iterate through remainder of messages extracting data
        data = []
        for d in s[1:]:
            assert d.message['key'] == 'DATA'
            msg_data = literal_eval(d.message['value'])
            msg_data['log_timestamp'] = d.timestamp.isoformat()
            # dedupe messages that are copied over to plotting classes
            if len(data)>0 and ('trial_num' not in msg_data.keys() or msg_data['timestamp'] == data[-1]['timestamp']):
                continue
            data.append(msg_data)

        # make a dataframe and package together with header, save
        df = pd.DataFrame(data)
        clean_sessions.append(Data_Extract(header=header, data=df))

    if output_dir:
        output_dir = Path(output_dir)

        if not output_dir.exists():
            output_dir.mkdir(parents=True, exist_ok=True)

        assert output_dir.is_dir()

        for s in clean_sessions:
            # make base output name
            base_name = f"{s['header']['subject']}_{s['header']['timestamp'].strftime('%y%m%dT%H%M%S')}_session-{s['header']['session']}"
            header_json = s['header'].copy()
            header_json['timestamp'] = header_json['timestamp'].isoformat()
            header_json['data_file'] = base_name + '.csv'
            with open(output_dir / (base_name + '.json'), 'w') as jfile:
                json.dump(header_json, jfile, indent=4, separators=(',', ': '), sort_keys=True)

            s['data'].to_csv(output_dir / (base_name + '.csv'), index=False)

    return clean_sessions





