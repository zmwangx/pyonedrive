#!/usr/bin/env python3

"""Package-specific exceptions."""

# pylint: disable=redefined-builtin

import onedrive.util

class GeneralAPIException(Exception):
    """The base execption class for all API related exceptions.

    All OneDrive API related exceptions are derived from this class.

    Parameters
    ----------
    msg : str, optional
        Error message. If ``None``, the message will be set to
        ``"unspecified API exception"``. Default is ``None``.

    Attributes
    ----------
    msg : str

    """
    def __init__(self, msg=None):
        """Init."""
        super().__init__()
        self.msg = msg if msg is not None else "unspecified API exception"

    def __str__(self):
        """The printable string is ``self.msg``."""
        if isinstance(self.msg, str):
            return self.msg
        else:
            return repr(self.msg)

class FileExistsError(GeneralAPIException):
    """File or directory already exists on OneDrive.

    Parameters
    ----------
    msg : str, optional
    path : str, optional
        Remote path.
    type : {None, "file", "directory"}, optional
    url : str, optional
        Remote URL.

    Attributes
    ----------
    msg : str
    path : str

    """

    def __init__(self, msg=None, path=None, type=None, url=None):
        """Init."""
        # pylint: disable=super-init-not-called
        self.path = path
        self.type = type
        self.url = url
        if msg is not None:
            self.msg = msg
        else:
            if type is not None:
                path_desc = ("%s '%s'" % (type, path) if path is not None
                             else "requested %s" % type)
            else:
                path_desc = ("'%s'" % path if path is not None
                             else "requested file or directory")
            location_desc = "at %s" % url if url is not None else "on OneDrive"
            self.msg = "%s already exists %s" % (path_desc, location_desc)

class FileNotFoundError(GeneralAPIException):
    """File or directory not found on OneDrive.

    Parameters
    ----------
    msg : str, optional
    path : str, optional
        Remote path.
    type : {None, "file", "directory"}, optional

    Attributes
    ----------
    msg : str
    path : str

    """

    def __init__(self, msg=None, path=None, type=None):
        """Init."""
        # pylint: disable=super-init-not-called
        self.path = path
        self.type = type
        if msg is not None:
            self.msg = msg
        else:
            if type is not None:
                path_desc = ("%s '%s'" % (type, path) if path is not None
                             else "requested %s" % type)
            else:
                path_desc = ("'%s'" % path if path is not None
                             else "requested file or directory")
            self.msg = "%s not found on OneDrive" % path_desc

class APIRequestError(GeneralAPIException):
    """An errored API request.

    Parameters
    ----------
    msg : str, optional
    response : requests.Response, optional
    request_desc : str, optional
        An optional description of the request which might be used in
        the message (if ``msg`` is not specified), e.g., ``"metadata
        request on 'vid'"``.

    Attributes
    ----------
    msg : str
    response : requests.Response
    request_desc : str

    """

    def __init__(self, msg=None, response=None, request_desc=None):
        """Init."""
        # pylint: disable=super-init-not-called
        self.response = response
        self.request_desc = request_desc
        if msg is not None:
            self.msg = msg
        else:
            request_desc = request_desc if request_desc is not None else "API request"
            if response is None or not hasattr(response, "request"):
                request_long_desc = request_desc
            else:
                request = response.request
                request_method = request.method
                request_url = onedrive.util.pop_query_from_url(request.url, "access_token")
                request_long_desc = "%s (%s %s )" % (request_desc, request_method, request_url)
            self.msg = ("got HTTP %d upon %s: %s; don't know what to do" %
                        (response.status_code, request_long_desc, response.text))

class UploadError(APIRequestError):
    """A special type of ``APIRequestError`` for error during uploads.

    Parameters
    ----------
    msg : str, optional
    path : str, optional
    response : requests.Response, optional
    request_desc : str, optional
    saved_session : onedrive.save.SavedUploadSession

    Attributes
    ----------
    msg : str
    path : str
    response : requests.Response
    request_desc : str

    """

    def __init__(self, msg=None, path=None, response=None, request_desc=None, saved_session=None):
        """Init."""
        super().__init__(msg=msg, response=response, request_desc=request_desc)
        self.path = path
        if msg is None:
            path_desc = "'%s'" % path if path is not None else "unspecified file"
            self.msg = "error occured when trying to upload %s; %s" % (path_desc, self.msg)
        if saved_session:
            self.msg += "; session saved to '%s'" % saved_session.session_path
