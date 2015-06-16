#!/usr/bin/env python3

"""Package-specific exceptions."""

# pylint: disable=redefined-builtin

import onedrive.util

class GeneralOneDriveException(Exception):
    """The base execption class for all package-specific exceptions.

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

class GeneralAPIException(GeneralOneDriveException):
    """The base execption class for all API related exceptions.

    All OneDrive API related exceptions are derived from this class.

    """
    pass

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
    type : str

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

    Attributes
    ----------
    msg : str
    path : str
    type : str

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

class IsADirectoryError(GeneralAPIException):
    """Requested item is a directory.

    Parameters
    ----------
    msg : str, optional
    path : str, optional
        Remote path.

    Attributes
    ----------
    msg : str
    path : str

    """

    def __init__(self, msg=None, path=None):
        """Init."""
        # pylint: disable=super-init-not-called
        self.path = path
        if msg is not None:
            self.msg = msg
        else:
            path_desc = "'%s'" % path if path is not None else "requested item"
            self.msg = "%s is a directory" % path_desc

class NotADirectoryError(GeneralAPIException):
    """Requested item is not a directory.

    Parameters
    ----------
    msg : str, optional
    path : str, optional
        Remote path.

    Attributes
    ----------
    msg : str
    path : str

    """

    def __init__(self, msg=None, path=None):
        """Init."""
        # pylint: disable=super-init-not-called
        self.path = path
        if msg is not None:
            self.msg = msg
        else:
            path_desc = "'%s'" % path if path is not None else "requested item"
            self.msg = "%s is not a directory" % path_desc

class PermissionError(GeneralAPIException):
    """Trying to run an operation without the adequate access rights.

    Parameters
    ----------
    msg : str, optional
    path : str, optional
        Remote path.

    Attributes
    ----------
    msg : str
    path : str

    """

    def __init__(self, msg=None, path=None):
        """Init."""
        # pylint: disable=super-init-not-called
        self.path = path
        if msg is not None:
            self.msg = msg
        else:
            path_desc = "'%s'" % path if path is not None else "requested item"
            self.msg = "unspecified permission error on %s" % path_desc

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

    def __init__(self, msg=None, path=None, response=None, saved_session=None):
        """Init."""
        # pylint: disable=super-init-not-called
        self.msg = msg
        self.path = path
        self.response = response
        self.saved_session = saved_session
        if msg is None:
            path_desc = "'%s'" % path if path is not None else "unspecified file"
            self.msg = "error occured when trying to upload %s; %s" % (path_desc, self.msg)
        if saved_session:
            self.msg += "; session saved to '%s'" % saved_session.session_path

class CopyError(APIRequestError):
    """A special type of ``APIRequestError`` for error during copy operation.

    Parameters
    ----------
    msg : str, optional
    src, dst : str, optional
        Source and destination paths.
    response : requests.Response, optional
    request_desc : str, optional

    Attributes
    ----------
    msg : str
    path : str
    response : requests.Response
    request_desc : str

    """

    def __init__(self, msg=None, src=None, dst=None, response=None):
        """Init."""
        # pylint: disable=super-init-not-called
        self.msg = msg
        self.src = src
        self.dst = dst
        self.response = response
        if msg is None:
            src_desc = "unspecified item" if src is None else "'%s'" % src
            dst_desc = "unspecified item" if dst is None else "'%s'" % dst
            self.msg = "failed to copy '%s' to '%s'" % (src_desc, dst_desc)
            if response is not None:
                self.msg += ": %s" % response.text

class CorruptedDownloadError(GeneralOneDriveException):
    """Exception for a corrupted download."""

    def __init__(self, msg=None, path=None,
                 remote_size=None, local_size=None, remote_sha1sum=None, local_sha1sum=None):
        """Init."""
        # pylint: disable=super-init-not-called
        self.path = path
        self.remote_size = remote_size
        self.local_size = local_size
        self.remote_sha1sum = remote_sha1sum
        self.local_sha1sum = local_sha1sum
        if msg is not None:
            self.msg = msg
        else:
            basic_desc = "download of '%s' is corrupted" % path
            if remote_size is not None and local_size is not None and remote_size != local_size:
                extended_desc = (": remote size is %d bytes; local size is %d bytes" %
                                 (remote_size, local_size))
            elif (remote_sha1sum is not None and local_sha1sum is not None and
                  remote_sha1sum != local_sha1sum):
                extended_desc = (": remote SHA-1 digest is %s; local SHA-1 digest is %s" %
                                 (remote_sha1sum, local_sha1sum))
            else:
                extended_desc = ""
            self.msg = basic_desc + extended_desc
