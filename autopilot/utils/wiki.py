"""
Utility functions for dealing with the wiki (https://wiki.auto-pi-lot.com).

See the docstrings of the :func:`.ask` function, as well as the :ref:`guide_plugins_wiki` section
in the user guide for use.
"""
from typing import Union, Optional, List
import requests
import pdb
import json
from autopilot.utils.common import find_key_value

WIKI_URL = "https://wiki.auto-pi-lot.com/"

def ask(
        filters:Union[List[str],str],
        properties:Union[None,List[str],str]=None) -> List[dict]:
    """
    Perform an API call to the wiki using the `ask API <https://www.semantic-mediawiki.org/wiki/Help:API:ask>`_
    and simplify to a list of dictionaries

    Args:
        filters (list, str): A list of strings or a single string of semantic
            mediawiki formatted property filters. See :func:`.make_ask_string` for more information
        properties (None, list, str): Properties to return from filtered pages,
            See :func:`.make_ask_string` for more information

    Returns:

    """
    query_str = make_ask_string(filters=filters, properties=properties, full_url=True)
    result = requests.get(query_str)
    entries = result.json()['query']['results']

    # unnest 'printouts' and convert from a nested list of dicts with the top
    # dict as the name (eg {'entry_name':{prop1:'prop1'}} to {'name': 'entry_name', 'prop1':...}
    unnested = []
    for entry in entries:
        entry_name = list(entry.keys())[0]
        nested_entry = entry[entry_name]
        unnest_entry = _clean_smw_result(nested_entry)
        unnested.append(unnest_entry)

    return unnested

def browse(
        search:str,
        browse_type:str="page",
        params:Optional[dict]=None
):
    """
    Use the `browse <https://www.semantic-mediawiki.org/wiki/Help:API:smwbrowse>`_ api of the wiki  to
    search for specific pages, properties, and so on.

    Args:
        search (str): the search string! ``*`` can be used as a wildcard.
        browse_type (str): The kind of browsing we're doing, one of:

            * page
            * subject
            * property
            * pvalue
            * category
            * concept

        params (dict): Additional params for the browse given as a dictionary, see `the smw docs <https://www.semantic-mediawiki.org/wiki/Help:API:smwbrowse>`_
            for usage.

    Returns:
        dict, list of dicts of results
    """

    browse_str = make_browse_string(search=search, browse_type=browse_type, params=params, full_url=True)
    result = requests.get(browse_str)


def _clean_smw_result(nested_entry:dict) -> dict:
    # unnest entries that are [[Has type::page]] and thus have extra metadata
    unnest_entry = {}
    printouts = nested_entry.get('printouts', {})
    if len(printouts)>0:
        for k, v in printouts.items():
            if isinstance(v, list) and len(v) > 1:
                unnest_entry[k] = []
                for subv in v:
                    if isinstance(subv, dict) and 'fulltext' in subv.keys():
                        subv = subv['fulltext']
                    unnest_entry[k].append(subv)
                unnest_entry[k] = sorted(unnest_entry[k])
            elif isinstance(v, list) and len(v) == 1:
                unnest_entry[k] = v[0]
                if isinstance(unnest_entry[k], dict) and 'fulltext' in unnest_entry[k].keys():
                    unnest_entry[k] = unnest_entry[k]['fulltext']
            else:
                unnest_entry[k] = v

    unnest_entry['name'] = nested_entry['fulltext']
    unnest_entry['url'] = nested_entry['fullurl']
    return unnest_entry


def make_ask_string(filters:Union[List[str], str],
                    properties:Union[None,List[str],str]=None,
                    full_url:bool = True) -> str:
    """
    Create a query string to request semantic information from the Autopilot wiki

    Args:
        filters (list, str): A list of strings or a single string of semantic
            mediawiki formatted property filters, eg ``"[[Category:Hardware]]"``
            or ``"[[Has Contributor::sneakers-the-rat]]"``. Refer to the
            `semantic mediawiki documentation <https://www.semantic-mediawiki.org/wiki/Help:Selecting_pages>`_
            for more information on syntax
        properties (None, list, str): Properties to return from filtered pages,
            see the `available properties <https://wiki.auto-pi-lot.com/index.php/Special:Properties>`_
            on the wiki and the `semantic mediawiki documentation <https://www.semantic-mediawiki.org/wiki/Help:Selecting_pages>`_
            for more information on syntax. If ``None`` (default), just return
            the names of the pages
        full_url (bool): If ``True`` (default), prepend ``f'{WIKI_URL}api.php?action=ask&query='``
            to the returned string to make it `ready for an API call <https://www.semantic-mediawiki.org/wiki/Help:API:ask>`_

    Returns:
        str: the formatted query string
    """
    # combine the components, separated by pipes or pip question marks as the case may be
    if isinstance(filters, str):
        filters = [filters]

    if len(filters)==0:
        raise ValueError(f'You need to provide at least one filter! Cant get the whole wiki!')

    query_str = "|".join(filters)

    if isinstance(properties, str):
        properties = [properties]
    elif properties is None:
        properties = []

    if len(properties)>0:
        # double join with ?| so it goes between
        # all the properties *and* between filters and
        query_str = "|?".join((
            query_str,
            "|?".join(properties)
        ))

    # add api call boilerplate and URI-encode
    query_str = requests.utils.quote(query_str) + "&format=json&api_version=3"

    if full_url:
        return f"{WIKI_URL}api.php?action=ask&query=" + query_str
    else:
        return query_str

def make_browse_string(search, browse_type='page', params=None, full_url:bool=True):

    if params is None:
        params = {}
    params['search'] = search

    browse_str = f"&browse={browse_type}&params={json.dumps(params)}&format=json"
    if full_url:
        return f"{WIKI_URL}api.php?action=smwbrowse" + browse_str
    else:
        return browse_str




