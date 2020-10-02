"""
Run scripts to setup system dependencies and autopilot plugins

.. example::

    > # to list scripts
    > python3 -m autopilot.setup.run_script --list

    > # to execute one script (setup hifiberry soundcard)
    > python3 -m autopilot.setup.run_script hifiberry

    > # to execute multiple scripts
    > python3 -m autopilot.setup.run_script hifiberry jackd

"""
import subprocess
from autopilot.setup.scripts import PILOT_ENV_CMDS
import argparse
import sys

parser = argparse.ArgumentParser(description="Run autopilot setup script(s)")
parser.add_argument('scripts', nargs='+', type=str)
parser.add_argument('-l', '--list', help="list available setup scripts!", action='store_true')


def call_series(commands, series_name=None):
    """
    Call a series of commands, giving a single return code on completion or failure

    :param commands:
    :return:
    """
    if series_name:
        print('\n\033[1;37;42m Running commands for {}\u001b[0m'.format(series_name))

    # have to just combine them -- can't do multiple calls b/c shell doesn't preserve between them
    combined_calls = ""
    last_command = len(commands)-1
    for i, command in enumerate(commands):
        join_with = " && "

        if isinstance(command, str):
            # just a command, default necessary
            combined_calls += command
        elif isinstance(command, dict):
            combined_calls += command['command']

            if command.get('optional', False):
                join_with = "; "

        if i < last_command:
            combined_calls += join_with


    print('Executing:\n    {}'.format(combined_calls))

    result = subprocess.run(combined_calls, shell=True, executable='/bin/bash')

    status = False
    if result.returncode == 0:
        status = True

    if series_name:
        if status:
            print('\n\033[1;37;42m  {} Successful, you lucky duck\u001b[0m'.format(series_name))
        else:
            print('\n\033[1;37;41m  {} Failed, check the error message & ur crystal ball\u001b[0m'.format(series_name))

    return status


def run_script(script_name):
    if script_name in PILOT_ENV_CMDS.keys():
        call_series(PILOT_ENV_CMDS[script_name], script_name)
    else:
        Exception('No script named {}, must be one of {}'.format(script_name, "\n".join(PILOT_ENV_CMDS.keys())))


def list_scripts():
    print('Available Scripts:')
    for script_name in sorted(PILOT_ENV_CMDS.keys()):
        print(f'{script_name}: {PILOT_ENV_CMDS[script_name]["text"]}\n')

if __name__ == "__main__":
    args = parser.parse_args()

    if args.list:
        list_scripts()
        sys.exit()
    elif args.scripts:
        call_series(args.scripts)
        sys.exit()
    else:
        raise RuntimeError('Need to give name of one or multiple scripts, ')