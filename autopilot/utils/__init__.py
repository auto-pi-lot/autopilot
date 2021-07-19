import json
from threading import Thread


class ReturnThread(Thread):
    """
    Thread whose .join() method returns the value from the function
    thx to https://stackoverflow.com/a/6894023
    """
    def __init__(self, group=None, target=None, name=None,
                 args=(), kwargs={}, Verbose=None):
        Thread.__init__(self, group, target, name, args, kwargs, Verbose)
        self._return = None
    def run(self):
        if self._Thread__target is not None:
            self._return = self._Thread__target(*self._Thread__args,
                                                **self._Thread__kwargs)
    def join(self, timeout=None):
        Thread.join(self, timeout)

        return self._return


def list_subjects(pilot_db=None):
    """
    Given a dictionary of a pilot_db, return the subjects that are in it.

    Args:
        pilot_db (dict): a pilot_db. if None tried to load pilot_db with :method:`.load_pilotdb`

    Returns:
        subjects (list): a list of currently active subjects

    """

    if pilot_db is None:
        pilot_db = load_pilotdb()

    subjects = []
    for pilot, values in pilot_db.items():
        if 'subjects' in values.keys():
            subjects.extend(values['subjects'])

    return subjects


def load_pilotdb(file_name=None, reverse=False):
    """
    Try to load the file_db

    Args:
        reverse:
        file_name:

    Returns:

    """

    if file_name is None:
        file_name = '/usr/autopilot/pilot_db.json'

    with open(file_name) as pilot_file:
        pilot_db = json.load(pilot_file)

    if reverse:
        # simplify pilot db
        pilot_db = {k: v['subjects'] for k, v in pilot_db.items()}
        pilot_dict = {}
        for pilot, subjectlist in pilot_db.items():
            for ms in subjectlist:
                pilot_dict[ms] = pilot
        pilot_db = pilot_dict

    return pilot_db


def coerce_discrete(df, col, mapping={'L':0, 'R':1}):
    """
    Coerce a discrete/string column of a pandas dataframe into numeric values

    Default is to map 'L' to 0 and 'R' to 1 as in the case of Left/Right 2AFC tasks

    Args:
        df (:class:`pandas.DataFrame`) : dataframe with the column to transform
        col (str):  name of column
        mapping (dict): mapping of strings to numbers

    Returns:
        df (:class:`pandas.DataFrame`) : transformed dataframe

    """

    for key, val in mapping.items():
        df.loc[df[col]==key,col] = val

    # if blanks, warn and remove
    if '' in df[col].unique():
        n_blanks = sum(df[col]=='')
        Warning('{} blank rows detected, removing.'.format(n_blanks))
        df.drop(df.index[df[col]==''], axis=0, inplace=True)

    df = df.astype({col:float})
    return df


def find_recursive(key, dictionary):
    """
    Find all instances of a key in a dictionary, recursively.

    Args:
        key:
        dictionary:

    Returns:
        list
    """
    for k, v in dictionary.items():
        if k == key:
            yield v
        elif isinstance(v, dict):
            for result in find_recursive(key, v):
                yield result
        elif isinstance(v, list):
            for d in v:
                for result in find_recursive(key, d):
                    yield result