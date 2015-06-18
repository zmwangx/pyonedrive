#!/usr/bin/env python3

"""OneDrive API client."""

# pylint: disable=too-many-lines

import os
import logging
import time
import urllib.parse

import arrow
import requests

from zmwangx.colorout import cprogress
import zmwangx.hash
import zmwangx.pbar

import onedrive.auth
import onedrive.exceptions
import onedrive.log
import onedrive.save
import onedrive.upload_helper
import onedrive.util

class OneDriveAPIClient(onedrive.auth.OneDriveOAuthClient):
    """OneDrive API client."""

    # pylint: disable=too-many-public-methods

    def __init__(self):
        """Init."""
        super().__init__()

    def upload(self, directory, local_path,
               chunk_size=10485760, timeout=15,
               stream=False, compare_hash=True, show_progress_bar=False):
        """Upload file using the resumable upload API."""

        # check local file existence
        if not os.path.exists(local_path):
            raise FileNotFoundError("'%s' does not exist" % local_path)
        elif not os.path.isfile(local_path):
            raise IsADirectoryError("'%s' is a directory" % local_path)

        # check remote file existence
        path = os.path.join(directory, os.path.basename(local_path))
        try:
            url = self.geturl(path)
            raise onedrive.exceptions.FileExistsError(path=path, url=url)
        except onedrive.exceptions.FileNotFoundError:
            pass

        # calculate local file hash
        if compare_hash:
            if show_progress_bar:
                cprogress("hashing progress:")
            local_sha1sum = zmwangx.hash.file_hash(
                local_path, "sha1", show_progress_bar=show_progress_bar).lower()
            logging.info("SHA-1 digest of local file '%s': %s", local_path, local_sha1sum)

            # try to load a saved session, which is not available in no
            # check mode (without checksumming, the file might be
            # modified or even replaced, so resuming upload is a very
            # bad idea)
            session = onedrive.save.SavedUploadSession(path, local_sha1sum)
        else:
            session = None

        if session:
            if show_progress_bar:
                filename = os.path.basename(local_path)
                cprogress("%s: loaded unfinished session from disk" % filename)
                cprogress("%s: retrieving upload session" % filename)
            upload_url = session.upload_url
            position = self._get_upload_position(path, upload_url, session)
        else:
            upload_url = self._initiate_upload_session(path, session)
            position = 0

        # initiliaze progress bar for the upload
        total = os.path.getsize(os.path.realpath(local_path))
        if show_progress_bar:
            if compare_hash:
                # print "upload progress:" to distinguish from hashing progress
                cprogress("upload progress:")
            pbar = zmwangx.pbar.ProgressBar(total, preprocessed=position)

        with open(os.path.realpath(local_path), "rb") as fileobj:
            response = None
            weird_error = False
            while position < total:
                size = min(chunk_size, total - position)
                if stream:
                    response = onedrive.upload_helper.stream_put_file_segment(
                        self, upload_url, fileobj, position, size, total,
                        timeout=timeout, path=path)
                else:
                    fileobj.seek(position)
                    segment = fileobj.read(size)
                    response = onedrive.upload_helper.put_file_segment(
                        self, upload_url, segment, position, size, total,
                        timeout=timeout, path=path)

                if response.status_code in {200, 201, 202}:
                    weird_error = False
                    position += size
                    if show_progress_bar:
                        pbar.update(size)
                    continue
                elif response.status_code == 404:
                    # start over
                    weird_error = False
                    upload_url = self._initiate_upload_session(path)
                    position = 0
                    if show_progress_bar:
                        pbar.force_update(position)
                    continue
                elif self._is_weird_upload_error(response):
                    if weird_error:
                        # twice in a row, raise
                        raise onedrive.exceptions.UploadError(
                            path=path, response=response, saved_session=session,
                            request_desc="chunk upload request")
                    else:
                        # set the weird_error flag and wait
                        weird_error = True
                        time.sleep(30)
                else:
                    # errored, but not weird
                    weird_error = False

                # errored, retry
                if response.status_code >= 500:
                    time.sleep(30)
                else:
                    time.sleep(3)
                position = self._get_upload_position(path, upload_url, session)
                if show_progress_bar:
                    pbar.force_update(position)

            # finished uploading the entire file
            if show_progress_bar:
                pbar.finish()
            assert response.status_code in {200, 201}  # 200 OK or 201 Created

            if compare_hash:
                try:
                    remote_sha1sum = response.json()["file"]["hashes"]["sha1Hash"].lower()
                    logging.info("SHA-1 digest of remote file '%s': %s", path, remote_sha1sum)
                except KeyError:
                    msg = "file created response has no key file.hashes.sha1Hash"
                    raise onedrive.exceptions.UploadError(
                        msg=msg, path=path, response=response, saved_session=session)

                if local_sha1sum != remote_sha1sum:
                    msg = ("SHA-1 digest mismatch:\nlocal '%s': %s\nremote '%s': %s" %
                           (local_path, local_sha1sum, path, remote_sha1sum))
                    logging.error(msg)
                    raise onedrive.exceptions.UploadError(
                        msg=msg, path=path, response=response, saved_session=session)

            # success
            if session:
                session.discard()

    def _initiate_upload_session(self, path, session=None):
        """Initiate a resumable upload session and return the upload URL.

        If the session parameter is given (a
        onedrive.save.SavedUploadSession object), then the newly created
        session is also saved to disk using the session.save call.

        """
        encoded_path = urllib.parse.quote(path)
        session_response = self.post("drive/root:/%s:/upload.createSession" % encoded_path,
                                     json={"@name.conflictBehavior": "fail"})
        if session_response.status_code == 404:
            raise onedrive.exceptions.FileNotFoundError(path=os.path.dirname(path),
                                                        type="directory")
        elif session_response.status_code != 200:
            raise onedrive.exceptions.UploadError(
                path=path, response=session_response, saved_session=session,
                request_desc="upload session initiation request")

        try:
            upload_url = session_response.json()["uploadUrl"]
        except KeyError:
            msg = ("no 'uploadUrl' in response: %s; cannot initiate upload session for '%s'" %
                   (session_response.text, path))
            raise onedrive.exceptions.UploadError(
                msg=msg, path=path, response=session_response, saved_session=session)

        # remove access code from upload_url, since the access code may
        # not be valid throughout the lifetime of the session
        upload_url = onedrive.util.pop_query_from_url(upload_url, "access_token")

        if session is not None:
            session.save(upload_url, session_response.json()["expirationDateTime"])

        return upload_url

    def _get_upload_position(self, path, upload_url, session=None):
        """Get the postion to continue with the upload."""
        try:
            status_response = self.get(upload_url, path=path)
        except requests.exceptions.RequestException as err:
            logging.error(str(err))
            raise
        if status_response.status_code != 200:
            raise onedrive.exceptions.UploadError(
                path=path, response=status_response, saved_session=session,
                request_desc="upload session status request")
        expected_ranges = status_response.json()["nextExpectedRanges"]

        # no remaining range
        if not expected_ranges:
            time.sleep(30)
            if self.exists(path):
                return
            else:
                raise onedrive.exceptions.UploadError(
                    msg="no missing ranges, but file still does not exist on OneDrive",
                    path=path, response=status_response, saved_session=session)

        # multi-range not implemented
        if len(expected_ranges) > 1:
            msg = "got ranges %s; multi-range upload not implemented" % str(expected_ranges)
            raise onedrive.exceptions.UploadError(
                msg=msg, path=path, response=status_response, saved_session=session)

        # single range, return position
        return int(expected_ranges[0].split("-")[0])

    @staticmethod
    def _is_weird_upload_error(response):
        """Check if a response got during upload is unhandleable.

        There are some errors lacking a known or implemented solution,
        e.g., 401 Unauthorized when the request clearly carries the
        required token. When these errors occur, the only we could do is
        wait and try again, and if it still fails, raise.

        """
        # one known weird situation is fragmentRowCountCheckFailed (see
        # https://github.com/zmwangx/pyonedrive/issues/1)
        if response.status_code == 416:
            try:
                if ((response.json()["error"]["innererror"]["code"] ==
                     "fragmentRowCountCheckFailed")):
                    return True
            except KeyError:
                pass

        # here are the codes with known solutions
        if response.status_code in {200, 201, 202, 404, 416, 500, 502, 503, 504}:
            return False

        return True

    def metadata(self, path):
        """Get metadata of a file or directory.

        Returns
        -------
        metadata : dict
            The JSON object as returned by the API:
            https://dev.onedrive.com/items/get.htm.

        Raises
        ------
        onedrive.exceptions.FileNotFoundError
            If requested item is not found.

        """
        encoded_path = urllib.parse.quote(path)
        logging.info("requesting '%s'", encoded_path)
        metadata_response = self.get("drive/root:/%s" % encoded_path)
        status_code = metadata_response.status_code
        if status_code == 200:
            return metadata_response.json()
        elif status_code == 404:
            raise onedrive.exceptions.FileNotFoundError(path=path)
        else:
            raise onedrive.exceptions.APIRequestError(
                response=metadata_response,
                request_desc="metadata request for '%s'" % path)

    def assert_exists(self, path):
        """Assert that ``path`` exists on OneDrive.

        Raises
        ------
        onedrive.exceptions.FileNotFoundError
            If requested item is not found.

        """
        try:
            self.metadata(path)
            return
        except onedrive.exceptions.FileNotFoundError:
            raise

    def assert_file(self, path):
        """Assert that ``path`` is an existing file on OneDrive.

        Raises
        ------
        onedrive.exceptions.FileNotFoundError
            If requested item is not found.
        onedrive.exceptions.IsADirectoryError
            If requested item exists but is a directory.

        """
        try:
            metadata = self.metadata(path)
            if "file" not in metadata:
                raise onedrive.exceptions.IsADirectoryError(path=path)
        except onedrive.exceptions.FileNotFoundError:
            raise

    def assert_dir(self, path):
        """Assert that ``path`` is an existing directory on OneDrive.

        Raises
        ------
        onedrive.exceptions.FileNotFoundError
            If requested item is not found.
        onedrive.exceptions.NotADirectoryError
            If requested item exists but is a file.

        """
        try:
            metadata = self.metadata(path)
            if "folder" not in metadata:
                raise onedrive.exceptions.NotADirectoryError(path=path)
        except onedrive.exceptions.FileNotFoundError:
            raise

    def exists(self, path):
        """Check if file or directory exists on OneDrive.

        Returns
        -------
        bool

        """
        try:
            self.assert_exists(path)
            return True
        except onedrive.exceptions.FileNotFoundError:
            return False

    def isfile(self, path):
        """Check if path is an existing file on OneDrive.

        Returns
        -------
        bool

        """
        try:
            self.assert_file(path)
            return True
        except (onedrive.exceptions.FileNotFoundError, onedrive.exceptions.IsADirectoryError):
            return False

    def isdir(self, path):
        """Check if path is an existing directory on OneDrive.

        Returns
        -------
        bool

        """
        try:
            self.assert_dir(path)
            return True
        except (onedrive.exceptions.FileNotFoundError, onedrive.exceptions.NotADirectoryError):
            return False

    def getsize(self, path):
        """Get the size, in bytes, of path.

        This differs from ``os.path.getsize`` in that the total size of
        a directory is returned.

        Returns
        -------
        size : int

        Raises
        ------
        onedrive.exceptions.FileNotFoundError
            If the requested item is not found.

        """
        try:
            metadata = self.metadata(path)
            return metadata["size"]
        except onedrive.exceptions.FileNotFoundError:
            raise

    def getmtime(self, path):
        """Get the time of last modification of path.

        Returns
        -------
        posix_time : int
            The number of seconds since the epoch.

        Raises
        ------
        onedrive.exceptions.FileNotFoundError
            If the requested item is not found.

        """
        try:
            metadata = self.metadata(path)
            return arrow.get(metadata["lastModifiedDateTime"]).timestamp
        except onedrive.exceptions.FileNotFoundError:
            raise

    def geturl(self, path):
        """Get URL for a file or directory.

        Returns
        -------
        url : str

        Raises
        ------
        onedrive.exceptions.FileNotFoundError
            If requested item is not found.

        """
        try:
            metadata = self.metadata(path)
            return metadata["webUrl"]
        except onedrive.exceptions.FileNotFoundError:
            raise

    def children(self, path):
        """List children of a directory.

        Returns
        -------
        children : list
            Returns a list of objects as returned by the children API
            (https://dev.onedrive.com/items/list.htm). If the requested
            item turns out to be a file, then the return value will be
            an empty list.

            Example return value for the children API (truncated)::

                [
                  {"name": "myfile.jpg", "size": 2048, "file": {} },
                  {"name": "Documents", "folder": { "childCount": 4 } },
                  {"name": "Photos", "folder": { "childCount": 203 } },
                  {"name": "my sheet(1).xlsx", "size": 197 }
                ]

        Raises
        ------
        onedrive.exceptions.FileNotFoundError
            If the requested item is not found.

        See Also
        --------
        list

        """
        encoded_path = urllib.parse.quote(path)
        logging.info("requesting children of '%s'", encoded_path)
        children_response = self.get("drive/root:/%s:/children" % encoded_path)
        status_code = children_response.status_code
        if status_code == 200:
            return children_response.json()["value"]
        elif status_code == 404:
            raise onedrive.exceptions.FileNotFoundError(path=path)
        else:
            raise onedrive.exceptions.APIRequestError(
                response=children_response,
                request_desc="children request for '%s'" % path)

    def list(self, path):
        """List the file itself, or children of a directory.

        Returns
        -------
        (type, items) : (str, list)
            ``type`` is the type of the requested path, which is either
            ``"file"`` or ``"directory"``.

            For directories, ``items`` is a list of objects as returned
            by the children API
            (https://dev.onedrive.com/items/list.htm). For files,
            ``items`` is a singleton with the metadata object as
            returned by the metadata API
            (https://dev.onedrive.com/items/get.htm).

        Raises
        ------
        onedrive.exceptions.FileNotFoundError
            If the requested item is not found.

        See Also
        --------
        children, metadata

        """
        try:
            metadata = self.metadata(path)
            if "file" in metadata:
                return ("file", [metadata])
            else:
                return ("directory", self.children(path))
        except onedrive.exceptions.FileNotFoundError:
            raise

    def listdir(self, path):
        """List the names of children of a directory.

        Returns
        -------
        list
            A list containing the names of the entries in the directory
            given by ``path``.

        Raises
        ------
        onedrive.exceptions.FileNotFoundError:
            If the requested item is not found.
        onedrive.exceptions.NotADirectoryError:
            If the requested item is not a directory.

        """
        self.assert_dir(path)
        children = self.children(path)
        return [child["name"] for child in children]

    def download(self, path, compare_hash=True, show_progress_bar=False):
        """Download a file from OneDrive.

        Parameters
        ----------
        path : str
            Remote path of file to download.
        compare_hash : bool, optional
            Whether to compare local and remote file hashes. Default is
            ``True``.
        show_progress_bar : bool, optional
            Whether to display a progress bar. Default is ``False``.

        Raises
        ------
        onedrive.exceptions.FileNotFoundError
            If the requested file is not found.
        onedrive.exceptions.IsADirectoryError
            If the requested item is a directory.
        FileExistsError
            If a file exists locally with the same filename.
        onedrive.exceptions.CorruptedDownload
            If the download appears corrupted (size or SHA-1 mismatch)

        """
        try:
            metadata = self.metadata(path)
            if "folder" in metadata:
                raise onedrive.exceptions.IsADirectoryError(path=path)
        except onedrive.exceptions.FileNotFoundError:
            raise

        local_path = metadata["name"]
        if os.path.exists(local_path):
            raise FileExistsError("'%s' already exists locally" % local_path)

        size = metadata["size"]
        if show_progress_bar:
            if compare_hash:
                cprogress("download progress:")
            pbar = zmwangx.pbar.ProgressBar(size)

        download_request = requests.get(url=metadata["@content.downloadUrl"], stream=True)
        tmp_path = "%s.part" % local_path
        with open(tmp_path, "wb") as fileobj:
            chunk_size = 65536
            for chunk in download_request.iter_content(chunk_size=chunk_size):
                if chunk:
                    fileobj.write(chunk)
                if show_progress_bar:
                    pbar.update(chunk_size)
        if show_progress_bar:
            pbar.finish()

        local_size = os.path.getsize(tmp_path)
        if size != local_size:
            raise onedrive.exceptions.CorruptedDownloadError(
                path=path, remote_size=size, local_size=local_size)
        if compare_hash:
            remote_sha1sum = metadata["file"]["hashes"]["sha1Hash"].lower()
            if show_progress_bar:
                cprogress("hashing progress:")
            local_sha1sum = zmwangx.hash.file_hash(
                tmp_path, "sha1", show_progress_bar=show_progress_bar).lower()
            if remote_sha1sum != local_sha1sum:
                raise onedrive.exceptions.CorruptedDownloadError(
                    path=path, remote_sha1sum=remote_sha1sum, local_sha1sum=local_sha1sum)
        os.rename(tmp_path, local_path)

    def makedirs(self, path, exist_ok=False):
        """Recursively create directory.

        Parameters
        ----------
        exist_ok : bool
            If ``False``, ``onedrive.exceptions.FileExistsError`` is
            raised when path already exists and is a directory. Default
            is ``False``.

        Returns
        -------
        metadata : dict
            Metadata object of the created (or existing) directory, as
            returned by a standard metadata request.

        Raises
        ------
        onedrive.exceptions.FileExistsError
            If path already exists and is a directory (with ``exist_ok``
            set to ``False``).
        onedrive.exceptions.NotADirectoryError
            If path or one of its intermediate paths exists and is not a
            directory.

        See Also
        --------
        mkdir

        """
        basename = os.path.basename(path)
        dirname = os.path.dirname(path)
        encoded_dirname = urllib.parse.quote(dirname)
        makedirs_response = self.post(
            "drive/root:/%s:/children" % encoded_dirname,
            json={"name": basename, "folder": {}, "@name.conflictBehavior": "fail"})
        status_code = makedirs_response.status_code
        if status_code == 201:
            return makedirs_response.json()
        elif status_code == 409:  # Conflict
            metadata = self.metadata(path)
            if "file" in metadata:
                msg = ("'%s' already exists at '%s' and is not a directory" %
                       (path, metadata["webUrl"]))
                raise onedrive.exceptions.NotADirectoryError(msg=msg, path=path)
            else:
                if exist_ok:
                    return metadata
                else:
                    raise onedrive.exceptions.FileExistsError(
                        path=path, type="directory", url=metadata["webUrl"])
        elif status_code == 403:  # Forbidden (accessDenied)
            msg = "one of the intermediate paths of '%s' is not a directory" % path
            raise onedrive.exceptions.NotADirectoryError(msg=msg, path=path)
        else:
            raise onedrive.exceptions.APIRequestError(
                response=makedirs_response,
                request_desc="directory creation request for '%s'" % path)

    def mkdir(self, path):
        """Create a directory (no recursive).

        Returns
        -------
        metadata : dict
            Metadata object of the created directory, as returned by a
            standard metadata request.

        Raises
        ------
        onedrive.exceptions.FileNotFoundError
            If the parent does not exist.
        onedrive.exceptions.FileExistsError
            If path already exists and is a directory.
        onedrive.exceptions.NotADirectoryError
            If the parent is not a directory.

        See Also
        --------
        makedirs

        """
        parent = os.path.dirname(path)
        self.assert_dir(parent)
        return self.makedirs(path, exist_ok=False)

    def rm(self, path, recursive=False):
        """Remove an item.

        Parameters
        ----------
        recursive : bool
            If ``True``, remove a directory and its children
            recursively; otherwise, raise
            ``onedrive.exceptions.IsADirectoryError`` when the item
            requested is a directory. Default is ``False``.

        Raises
        ------
        onedrive.exceptions.FileNotFoundError
            If the item does not exist in the first place.
        onedrive.exceptions.IsADirectoryError
            If ``recursive`` is set to ``False`` and the requested item
            is a directory.

        """
        encoded_path = urllib.parse.quote(path)

        if not recursive:
            self.assert_file(path)

        delete_response = self.delete("drive/root:/%s" % encoded_path)
        status_code = delete_response.status_code
        if status_code == 204:
            return
        elif status_code == 404:
            raise onedrive.exceptions.FileNotFoundError(path=path)
        else:
            raise onedrive.exceptions.APIRequestError(
                response=delete_response,
                request_desc="deletion request for '%s'" % path)

    def remove(self, path):
        """Alias for ``self.rm(path)``."""
        self.rm(path)

    def rmtree(self, path):
        """Remove directory tree.

        Basically an alias for ``self.rm(path, recursive=True)``, with
        the additional check that ``path`` is an existing directory.

        Raises
        ------
        onedrive.exceptions.FileNotFoundError
            If the item does not exist in the first place.
        onedrive.exceptions.NotADirectoryError
            If the item exists but is not a directory.

        """
        self.assert_dir(path)
        self.rm(path, recursive=True)

    def rmdir(self, path):
        """Remove an empty directory.

        Raises
        ------
        onedrive.exceptions.FileNotFoundError
            If the item does not exist in the first place.
        onedrive.exceptions.NotADirectoryError
            If the item exists but is not a directory.
        onedrive.exceptions.PermissionError
            If the directory is not empty.

        """
        try:
            metadata = self.metadata(path)
        except onedrive.exceptions.FileNotFoundError:
            raise

        if "file" in metadata:
            raise onedrive.exceptions.NotADirectoryError(path=path)

        child_count = metadata["folder"]["childCount"]
        if child_count > 0:
            msg = "directory '%s' is not empty" % path
            raise onedrive.exceptions.PermissionError(msg=msg, path=path)

        self.rm(path, recursive=True)

    def removedirs(self, path):
        """Remove directories recursively.

        Works like ``rmdir`` except that, if the leaf directory is
        successfully removed, ``removedirs`` tries to successively
        remove every parent directory mentioned in path until an error
        is raised (which is ignored, because it generally means that a
        parent directory is not empty).

        Raises
        ------
        See ``rmdir``. Only exceptions on the leaf directory are raised.

        """
        self.rmdir(path)
        while True:
            path = os.path.dirname(path)
            if not path:
                break
            try:
                self.rmdir(path)
            except onedrive.exceptions.PermissionError:
                break

    def move_or_copy(self, action, src, dst, overwrite=False,
                     block=True, monitor_interval=1, show_progress=False):
        """Move or copy an item.

        https://dev.onedrive.com/items/move.htm.
        https://dev.onedrive.com/items/copy.htm.

        Parameters
        ----------
        action : {"move", "copy"}
            Select an action.
        src : str
            Source item path.
        dst : dst
            Destination item path (including both dirname and basename).
        overwrite : bool, optional
            Whether to overwrite in the case of a conflict. Default is
            ``False``. Note that even when this is set to ``True``, the
            destination won't be overwritten if it is not of the same
            type as the source (i.e., source is file but dest is
            directory, or the other way round), or if it is a nonempty
            directory.
        block : bool, optional
            Whether to block until copy completes or errors (only useful
            when action is copy). Default is ``True``.
        monitor_interval : float, optional
            Only useful when action is copy. See ``monitor_copy``.
        show_progress : bool, optional
            Only useful when action is copy. See ``monitor_copy``.

        Returns
        -------
        monitor_url : str
            If action is copy and ``block`` is set to ``True``, then
            return the URL for monitoring copy status (which can be
            passed to ``monitor_copy``); otherwise, return nothing.

        Raises
        ------
        onedrive.exceptions.FileNotFoundError
            If source or the parent of the destination does
            not exist.
        onedrive.exceptions.NotADirectoryError
            If the parent of the destination exists but is not a
            directory.
        onedrive.exceptions.FileExistsError
            If the source and destination are the same item (whether
            ``overwrite`` or not); or if ``overwrite`` is ``False`` and
            the destination item already exists.
        onedrive.exceptions.PermissionError
            If trying to overwrite a dest with a source of a different
            type, or trying to overwrite a nonempty directory.
        onedrive.excpetions.CopyError
            If action is copy, ``block`` is ``True``, and the copy
            operation fails.

        See Also
        --------
        monitor_copy, move, copy, mv, cp

        """
        if action not in {"move", "copy"}:
            raise ValueError("unknow action '%s'; should be 'move' or 'copy'" % action)

        # check source and dest are not the same item
        if os.path.abspath(src) == os.path.abspath(dst):
            actioning = "moving" if action is "move" else "copying"
            msg = "'%s': %s to the same item" % (src, actioning)
            raise onedrive.exceptions.FileExistsError(msg=msg, path=src)

        # confirm source item existence and store metadata for future use
        try:
            src_metadata = self.metadata(src)
        except onedrive.exceptions.FileNotFoundError:
            raise

        # overwriting behavior
        if not overwrite:
            if self.exists(dst):
                raise onedrive.exceptions.FileExistsError(path=dst)
        else:
            try:
                dst_metadata = self.metadata(dst)

                # get source and dest types
                src_type = "file" if "file" in src_metadata else "directory"
                dst_type = "file" if "file" in dst_metadata else "directory"

                # decide action based on source and dest types
                if src_type != dst_type:
                    msg = ("cannot overwrite %s '%s' with %s '%s'" %
                           (dst_type, dst, src_type, src))
                    raise onedrive.exceptions.PermissionError(msg)
                elif dst_type == "file":
                    # both are files, remove dest
                    self.rm(dst)
                else:
                    # both are directories, try to remove dest (only works if it's empty)
                    try:
                        self.rmdir(dst)
                    except onedrive.exceptions.PermissionError:
                        raise

            except onedrive.exceptions.FileNotFoundError:
                # dest not there yet, which is good
                pass

        new_parent = os.path.dirname(dst)
        new_name = os.path.basename(dst)

        # confirm new parent is an existing directory
        self.assert_dir(new_parent)

        # make request
        encoded_path = urllib.parse.quote(src)
        encoded_new_parent = urllib.parse.quote(new_parent)
        method = "patch" if action == "move" else "post"
        endpoint = ("drive/root:/%s" % encoded_path if action == "move" else
                    "drive/root:/%s:/action.copy" % encoded_path)
        headers = {} if action == "move" else {"prefer": "respond-async"}
        response = self.request(method, endpoint, headers=headers, json={
            "parentReference": {"path": "/drive/root:/%s" % encoded_new_parent},
            "name": new_name,
        })
        status_code = response.status_code

        if status_code == 200:
            # successful move
            return
        elif status_code == 202:
            # copy: accepted
            monitor_url = onedrive.util.pop_query_from_url(response.headers["location"],
                                                           "access_token")
            if block:
                self.monitor_copy(monitor_url,
                                  monitor_interval=monitor_interval,
                                  show_progress=show_progress,
                                  src=src, dst=dst)
            else:
                return monitor_url

        # HTTP 400 (invalidArgument) seems to be returned when trying to
        # move an item that is recently moved; seems to be a bug on the
        # server side. Anyway, we treats it just like 404 for now.
        elif status_code in {400, 404}:
            # API says not found; but we already checked the existence
            # of source, so what is not found must be the new parent.
            raise onedrive.exceptions.FileNotFoundError(path=new_parent)
        elif status_code == 409:
            # conflict, shouldn't really happen as we already tested
            # prior to request, but anyway
            raise onedrive.exceptions.FileExistsError(path=dst)
        else:
            raise onedrive.exceptions.APIRequestError(
                response=response,
                request_desc="%s request for '%s' to '%s'" % (action, src, dst))

    def monitor_copy(self, monitor_url, monitor_interval=1,
                     show_progress=False, src=None, dst=None):
        """
        Monitor an async copy job.

        Parameters
        ----------
        monitor_url : str
            A monitor URL returned by the copy API. See
            https://dev.onedrive.com/items/copy.htm.
        monitor_interval : float, optional
            Interval between two status queries, in seconds. Default is
            ``1``.
        show_progress : bool, optional
            Whether to print textual progress information to
            stderr. Default is ``False``.
        src, dst : str
            Source and destination paths. Used for informational purpose
            only. Defaults are ``None``.

        Raises
        ------
        onedrive.exceptions.CopyError
           If the copy operation failed or was cancelled.

        """
        src_desc = "unspecified item" if src is None else "'%s'" % src
        dst_desc = "unspecified item" if dst is None else "'%s'" % dst
        if show_progress:
            cprogress("copying %s to %s" % (src_desc, dst_desc))
            ptext = zmwangx.pbar.ProgressText(init_text="copying")
        while True:
            status_response = self.get(monitor_url)
            status_code = status_response.status_code
            if status_code in {200, 303}:
                if show_progress:
                    ptext.finish("finished copying")
                return
            elif status_code == 202:
                if show_progress:
                    status = status_response.json()
                    text = "%s: %s" % (status["status"], status["statusDescription"])
                    ptext.text(text)
            elif status_code == 500:
                if show_progress:
                    status = status_response.json()
                    text = "%s: %s" % (status["status"], status["statusDescription"])
                    ptext.finish(text)
                raise onedrive.exceptions.CopyError(
                    msg=text, src=src, dst=dst, response=status_response)
            else:
                if show_progress:
                    ptext.finish("unknown error occurred")
                raise onedrive.exceptions.CopyError(
                    src=src, dst=dst, response=status_response,
                    request_desc="copy status request for '%s' to '%s'" % (src, dst))
            time.sleep(monitor_interval)

    def move(self, *args, **kwargs):
        """
        Alias for ``self.move_or_copy("move", *args, **kwargs)``.

        Basic usage: ``move(path, new_parent, new_name)``.

        """
        return self.move_or_copy("move", *args, **kwargs)

    def copy(self, *args, **kwargs):
        """
        Alias for ``self.move_or_copy("copy", *args, **kwargs)``.

        Basic usage: ``copy(path, new_parent, new_name)``.

        """
        return self.move_or_copy("copy", *args, **kwargs)

    def rename(self, src, dst):
        """
        Rename the file or directory ``src`` to ``dst``.

        Raises
        ------
        onedrive.exceptions.FileNotFoundError
            If ``src`` or the parent directory of ``dst`` does not
            exist.
        onedrive.exceptions.FileExistsError
            If ``dst`` already exists.

        """
        self.move(src, os.path.dirname(dst), os.path.basename(dst))

    def renames(self, src, dst):
        """Recursive directory or file renaming function.

        Works like ``rename``, except creation of any intermediate
        directories needed to make the new pathname good is attempted
        first. After the rename, directories corresponding to rightmost
        path segments of the old name will be pruned away using
        ``removedirs``.

        Raises
        ------
        onedrive.exceptions.FileNotFoundError
            If ``src`` does not exist.
        onedrive.exceptions.FileExistsError
            If ``dst`` already exists.
        onedrive.exceptions.NotADirectoryError
            If one of the intermediate paths of ``dst`` already exists
            and is not a directory.

        """
        self.assert_exists(src)

        # try to make intermediate directories required
        try:
            self.makedirs(os.path.dirname(dst), exist_ok=True)
        except onedrive.exceptions.NotADirectoryError:
            raise

        # try to rename
        try:
            self.rename(src, dst)
        except onedrive.exceptions.FileExistsError:
            raise

        # pruned old path with removedirs
        self.removedirs(os.path.dirname(src))

    def walk(self, top, topdown=True, paths_only=False, **kwargs):
        """Walk a directory tree.

        Retrieve metadata of items (or names only, if you prefer) in a
        directory tree by walking the tree either top-down or bottom-up.  See
        https://docs.python.org/3/library/os.html#os.walk for more detailed
        explanation and usage examples (in fact, part of the doc you see here
        is directly copied from there).

        Parameters
        ----------
        top : str
            The path to the root directory.
        topdown : bool, optional
            If ``True``, the triple for a directory is generated before the
            triples for any of its subdirectories (directories are generated
            top-down). If ``False``, the triple for a directory is generated
            after the triples for all of its subdirectories (directories are
            generated bottom-up). No matter the value of ``topdown``, the list
            of subdirectories is retrieved before the tuples for the directory
            and its subdirectories are generated. Default is ``True``.

            When ``topdown`` is ``True``, the caller can modify the dirs or
            dirnames list in-place, and ``walk`` will only recurse into the
            subdirectories that remain; this can be used to prune the search,
            impose a specific order of visiting, or even to inform ``walk``
            about directories the caller creates or renames before it resumes
            ``walk`` again. Modifying the list when ``topdown`` is ``False`` is
            ineffective, because in bottom-up mode the directories in dirnames
            are generated before dirpath itself is generated.
        paths_only : bool, optional
            Whether to yield only the directory path and lists with only item
            names (as opposed to full metadata objects). See the "Yields"
            section. Default is ``False``.

        Other Parameters
        ----------------
        check_dir : bool, optional
            Whether to perform a check to confirm ``top`` is an existing
            directory. If set to ``False``, ``walk`` will just assume ``top``
            is an existing directory, will may lead to surprises if you haven't
            confirmed it beforehand. Default is ``True``. This parameter is
            mostly used internally (to reduce recursion overhead).
        metadata : dict, optional
            The metadata object of ``top``, if it is already known; default is
            ``None``. This parameter is used to avoid one extra metadata query
            when ``paths_only`` is ``False``. It becomes significant when used
            in a recursive setting.

        Yields
        ------
        (dirmetadata, dirs, files) or (dirpath, dirnames, filenames)
            For each directory in the tree rooted at directory ``top``
            (including ``top`` itself), a three-tuple is yielded. Whether full
            metadata objects or only path/names are yielded depends on the
            ``paths_only`` option.

        Returns
        -------
        onedrive.exceptions.FileNotFoundError
            If ``top`` is not found.
        onedrive.exceptions.IsADirectoryError
            If ``top`` exists but is a directory.

        """
        for tup in self.walkn(top, topdown=topdown, paths_only=paths_only, **kwargs):
            yield tup[1:]

    def walkn(self, top, level=0, topdown=True, paths_only=False, **kwargs):
        """Walk, armored with level info.

        See ``walk``. This method works exactly the same as ``walk`` except
        that the level of the subdirectory is prepended to each yielded
        tuple. By default ``top`` has level 0, but this can be customized via
        the ``level`` option.

        """
        check_dir = kwargs.pop("check_dir", True)
        top_metadata = kwargs.pop("metadata", None)

        if check_dir:
            try:
                if top_metadata is None:
                    top_metadata = self.metadata(top)
                if "folder" not in top_metadata:
                    raise onedrive.exceptions.NotADirectoryError(path=top)
            except onedrive.exceptions.FileNotFoundError:
                raise

        dirs = []
        files = []
        children = self.children(top)
        for item in children:
            if "folder" in item:
                dirs.append(item)
                if not topdown:
                    yield from self.walkn(os.path.join(top, item["name"]), level + 1,
                                          topdown=topdown, paths_only=paths_only,
                                          check_dir=False, metadata=item)
            else:
                files.append(item)

        # yield at the current level
        if paths_only:
            dirnames = [item["name"] for item in dirs]
            filenames = [item["name"] for item in files]
            yield level, top, dirnames, filenames
        else:
            if top_metadata is None:
                top_metadata = self.metadata(top)
            yield level, top_metadata, dirs, files

        # if topdown, recurse into subdirectories
        if topdown:
            for item in dirs:
                yield from self.walkn(os.path.join(top, item["name"]), level + 1,
                                      topdown=topdown, paths_only=paths_only,
                                      check_dir=False, metadata=item)
