#!/usr/bin/env python3

"""OneDrive API client."""

# TODO: customizable conflict behavior

import os
import logging
import time
import urllib.parse

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

        See Also
        --------
        list

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

    def exists(self, path):
        """Check if file or directory exists in OneDrive.

        Returns
        -------
        exists : bool

        """
        try:
            self.metadata(path)
            return True
        except onedrive.exceptions.FileNotFoundError:
            return False

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
        metadata = self.metadata(path)
        return metadata["webUrl"]

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
        metadata = self.metadata(path)
        if "file" in metadata:
            return ("file", [metadata])
        else:
            return ("directory", self.children(path))

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
        metadata = self.metadata(path)
        if "folder" in metadata:
            raise onedrive.exceptions.IsADirectoryError(path=path)
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

        Exceptions
        ----------
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
                raise onedrive.exceptions.NotADirectoryError(msg=msg)
            else:
                if exist_ok:
                    return metadata
                else:
                    raise onedrive.exceptions.FileExistsError(
                        path=path, type="directory", url=metadata["webUrl"])
        elif status_code == 403:  # Forbidden (accessDenied)
            msg = "one of the intermediate paths of '%s' is not a directory" % path
            raise onedrive.exceptions.NotADirectoryError(msg=msg)
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

        Exceptions
        ----------
        onedrive.exceptions.FileNotFoundError:
            If the parent does not exist.
        onedrive.exceptions.FileExistsError
            If path already exists and is a directory.
        onedrive.exceptions.NotADirectoryError
            If the parent is not a directory.

        See Also
        --------
        makedirs

        """
        dirname = os.path.dirname(path)
        try:
            parent_metadata = self.metadata(dirname)
        except onedrive.exceptions.FileNotFoundError:
            raise

        if "file" in parent_metadata:
            msg = ("parent '%s' (located at '%s') is not a directory" %
                   (dirname, parent_metadata["webUrl"]))
            raise onedrive.exceptions.NotADirectoryError(msg=msg)

        return self.makedirs(path, exist_ok=False)
