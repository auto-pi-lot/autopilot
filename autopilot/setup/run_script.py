"""
Run scripts to setup system dependencies and autopilot plugins

::

    > # to list scripts
    > python3 -m autopilot.setup.run_script --list

    > # to execute one script (setup hifiberry soundcard)
    > python3 -m autopilot.setup.run_script hifiberry

    > # to execute multiple scripts
    > python3 -m autopilot.setup.run_script hifiberry jackd

"""
import typing
import subprocess
from autopilot.setup.scripts import SCRIPTS
import argparse
import sys

parser = argparse.ArgumentParser(description="Run autopilot setup script(s)")
parser.add_argument('scripts', nargs='*', type=str)
parser.add_argument('--list', help="list available setup scripts!", action='store_true')


def call_series(commands:typing.List[typing.Union[str, dict]], series_name=None, verbose:bool=True) -> bool:
    """
    Call a series of commands, giving a single return code on completion or failure

    See :mod:`.setup.scripts` for syntax of command list.

    Args:
        commands (list): List of strings or dicts to call, see :mod:`.setup.scripts`
        series_name (None, str): If provided, print name of currently running script
        verbose (bool): If ``True`` (default), print command and status messages.

    Returns:
        bool - ``True`` if completed successfully
    """
    if series_name and verbose:
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

    if verbose:
        print('Executing:\n    {}'.format(combined_calls))

    result = subprocess.run(combined_calls, shell=True, executable='/bin/bash')

    status = False
    if result.returncode == 0:
        status = True

    if series_name and verbose:
        if status:
            print('\n\033[1;37;42m  {} Successful, you lucky duck\u001b[0m'.format(series_name))
        else:
            print('\n\033[1;37;41m  {} Failed, check the error message & ur crystal ball\u001b[0m'.format(series_name))

    return status


def run_script(script_name):
    """
    Thin wrapper around :func:`.call_series` that gets a script by name from
    :data:`.scripts.SCRIPTS` and passes the list of ``commands``

    Args:
        script_name (str): name of a script in :data:`.scripts.SCRIPTS`
    """
    if script_name in SCRIPTS.keys():
        call_series(SCRIPTS[script_name]['commands'], script_name)
    else:
        raise NameError('No script named {}, must be one of {}'.format(script_name, "\n".join(SCRIPTS.keys())))

def run_scripts(scripts:typing.List[str], return_all:bool=False,print_status:bool=True) -> typing.Union[bool, typing.Dict[str,bool]]:
    """
    Run a series of scripts, printing results

    Args:
        scripts (list): list of script names
        return_all (bool): if True, return dict of ``{script:success}`` for each
            called script. If ``False`` (default), return single bool if all commands were successful
        print_status (bool): if ``True`` (default), print whether each script completed successfully or not.

    Returns:
        bool: success or failure of scripts - ``True`` if all were successful, ``False`` otherwise.
    """
    env_results = {}
    for script_name in scripts:
        commands = SCRIPTS[script_name].get('commands', None)
        if commands is not None:
            env_results[script_name] = call_series(commands, script_name)

    # indicate global success
    success = True

    # make results string
    if print_status:
        env_result = "\033[0;32;40m\n--------------------------------\nScript Results:\n"
        for config, result in env_results.items():
            if result:
                env_result += "  [ SUCCESS ] "
            else:
                env_result += "  [ FAILURE ] "
                success = False

            env_result += config
            env_result += '\n'

        env_result += '--------------------------------\u001b[0m'

        print(env_result)

    if return_all:
        return env_results
    else:
        return success


def list_scripts():
    """
    Print a formatted list of names in :data:`.scripts.SCRIPTS`
    """
    print('\nAvailable Scripts:\n----------------------------')

    # find longest script name
    longest_name = 0
    for script_name in SCRIPTS.keys():
        if len(script_name) > longest_name:
            longest_name = len(script_name)


    for script_name in sorted(SCRIPTS.keys()):
        pad = " " * (longest_name - len(script_name))
        print(f'\033[0;32m{script_name}{pad}\u001b[0m : {SCRIPTS[script_name]["text"]}')

if __name__ == "__main__":
    args = parser.parse_args()

    if args.list:
        list_scripts()
        sys.exit()
    elif args.scripts:
        res = run_scripts(args.scripts)
        if res:
            sys.exit()
        else:
            sys.exit(1)
    else:
        raise RuntimeError('Need to give name of one or multiple scripts, ')