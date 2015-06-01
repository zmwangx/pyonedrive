#!/usr/bin/env python3

"""Some shared utilities."""

import urllib.parse

def pop_query_from_url(url, query_variable):
    """Strip a certain query_variable from an URL.

    E.g., often times we want to strip the access token when printing
    the URL for informational purposes.

    Parameters
    ----------
    url : str
        Original URL.
    query_variable : str
        Query variable to be striped, e.g., ``access_token``.

    Returns
    -------
    stripped_url : str

    Examples
    --------
    >>> pop_query_from_url("http://example.com?access_token=142857", "access_token")
    'http://example.com'

    """
    scheme, netloc, path, params, query, fragment = urllib.parse.urlparse(url)
    query_dict = urllib.parse.parse_qs(query)
    try:
        query_dict.pop(query_variable)
    except KeyError:
        pass
    new_query = urllib.parse.urlencode(query_dict, doseq=True)
    return urllib.parse.urlunparse((scheme, netloc, path, params, new_query, fragment))
