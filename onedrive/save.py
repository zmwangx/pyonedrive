#!/usr/bin/env python3

"""This module reads and writes saved upload sessions.

A saved session is ``~/.local/share/onedrive/saved_sessions/ID.json``, where
``ID`` is a unique SHA-1 hexdigest computed from the remote path and the
SHA-1 digest of the file. It looks like::

{
    "upload_url": ...,
    "expires": 1433128563
}

where ``"expires"`` is a POSIX timestamp.

"""

import arrow
import json
import hashlib
import logging
import os
import time

class SavedUploadSession(object):
    """Saved upload session.

    Parameters
    ----------
    remote_path : str
    sha1sum : str

    Attributes
    ----------
    session_path : str
        Path of saved session on disk.
    upload_url : str
        ``None`` when session hasn't been loaded or saved.
    expires : int
        POSIX timestamp. ``None`` when session hasn't been loaded or
        saved.

    """
    # pylint: disable=attribute-defined-outside-init,invalid-name

    def __init__(self, remote_path, sha1sum):
        """Try to load saved upload session."""
        self.session_path = self._locate_saved_session(remote_path, sha1sum)
        self.load()

    def __bool__(self):
        """Check if an upload session is already loaded."""
        return self.upload_url is not None

    @staticmethod
    def _locate_saved_session(remote_path, sha1sum):
        """Return path of the saved session on disk (might not exist)."""
        if "XDG_DATA_HOME" in os.environ:
            home = os.path.join(os.environ["XDG_DATA_HOME"], "onedrive")
        else:
            home = os.path.expanduser("~/.local/share", "onedrive")

        session_id = hashlib.sha1("{path}\n{sha1sum}".format(
            path=remote_path, sha1sum=sha1sum).encode("utf-8")).hexdigest()

        return os.path.join(home, "saved_sessions", "%s.json" % session_id)

    def load(self):
        """Try to load saved session."""
        if os.path.exists(self.session_path):
            with open(self.session_path, encoding="utf-8") as fp:
                session = json.load(fp)
                if session["expires"] > time.time():
                    self.upload_url = session["upload_url"]
                    self.expires = session["expires"]
                    logging.info("session %s loaded from disk", self.session_path)
                    return
            # session found on disk but has expired
            logging.warning("session found on disk in %s but has expired",
                            self.session_path)
            # remove the expired session from disk
            os.remove(self.session_path)

        self.upload_url = None
        self.expires = None

    def save(self, upload_url, expiration_datetime):
        """Write a new session to self and to disk.

        expiration_datetime is an ISO-8601 formatted datetime string as
        returned by the API.

        """
        self.upload_url = upload_url
        self.expires = arrow.get(expiration_datetime).timestamp
        os.makedirs(os.path.dirname(self.session_path), exist_ok=True)
        with open(self.session_path, "w", encoding="utf-8") as fp:
            json.dump({"upload_url": self.upload_url, "expires": self.expires},
                      fp, indent=4)
        logging.info("session %s saved", self.session_path)

    def discard(self):
        """Disgard the saved session."""
        try:
            os.remove(self.session_path)
        except FileNotFoundError:
            pass
        logging.info("session %s discarded", self.session_path)
        self.upload_url = None
        self.expires = None
