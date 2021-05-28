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
from autopilot.setup.scripts import SCRIPTS
import argparse
import sys

parser = argparse.ArgumentParser(description="Run autopilot setup script(s)")
parser.add_argument('scripts', nargs='*', type=str)
parser.add_argument('--list', help="list available setup scripts!", action='store_true')


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
    if script_name in SCRIPTS.keys():
        call_series(SCRIPTS[script_name]['commands'], script_name)
    else:
        Exception('No script named {}, must be one of {}'.format(script_name, "\n".join(SCRIPTS.keys())))

def run_scripts(scripts):
    env_results = {}
    for script_name in scripts:
        commands = SCRIPTS[script_name]['commands']
        env_results[script_name] = call_series(commands, script_name)

    # make results string
    env_result = "\033[0;32;40m\n--------------------------------\nScript Results:\n"
    for config, result in env_results.items():
        if result:
            env_result += "  [ SUCCESS ] "
        else:
            env_result += "  [ FAILURE ] "

        env_result += config
        env_result += '\n'

    env_result += '--------------------------------\u001b[0m'

    print(env_result)


def list_scripts():
    print('\nAvailable Scripts:\n----------------------------')

    # find longest script name
    longest_name = 0
    for script_name in SCRIPTS.keys():
        if len(script_name) > longest_name:
            longest_name = len(script_name)


    for script_name in sorted(SCRIPTS.keys()):
        pad = " " * (longest_name - len(script_name))
        print(f'\033[1;37;42m{script_name}{pad}\u001b[0m : {SCRIPTS[script_name]["text"]}')

if __name__ == "__main__":
    args = parser.parse_args()

    if args.list:
        list_scripts()
        sys.exit()
    elif args.scripts:
        run_scripts(args.scripts)
        sys.exit()
    else:
        raise RuntimeError('Need to give name of one or multiple scripts, ')