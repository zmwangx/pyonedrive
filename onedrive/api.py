#!/usr/bin/env python3

"""OneDrive API client."""

# TODO: define more meaningful exception classes

import os
import logging
import time
import urllib.parse

import requests

from zmwangx.colorout import cprogress
import zmwangx.hash
import zmwangx.pbar

import onedrive.auth
import onedrive.log
import onedrive.upload_helper

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
            raise OSError("'%s' does not exist" % local_path)
        elif not os.path.isfile(local_path):
            raise OSError("'%s' is not a file" % local_path)

        # check remote file existence
        path = os.path.join(directory, os.path.basename(local_path))
        url = self.geturl(path)
        if url:
            raise OSError("'%s' already exists at %s" % (path, url))

        # initiate upload session
        encoded_path = urllib.parse.quote(path)
        # TODO: customizable conflict behavior
        session_response = self.post("drive/root:/%s:/upload.createSession" % encoded_path,
                                     json={"@name.conflictBehavior": "fail"})
        if session_response.status_code == 404:
            raise OSError("directory '%s' does not exist on OneDrive" % directory)
        try:
            upload_url = session_response.json()["uploadUrl"]
        except KeyError:
            raise OSError("no 'uploadUrl' in response: %s" % session_response.text)
        # remove access code from upload_url, since the access code may
        # not be valid throughout the lifetime of the session
        upload_url = urllib.parse.urlunparse(urllib.parse.urlparse(upload_url)._replace(query=""))

        # calculate local file hash
        if compare_hash:
            if show_progress_bar:
                cprogress("hashing progress:")
            local_sha1sum = zmwangx.hash.file_hash(local_path, "sha1",
                                                   show_progress_bar=show_progress_bar).lower()
            logging.info("SHA-1 digest of local file '%s': %s", local_path, local_sha1sum)

        # TODO: save session

        canonical_path = os.path.realpath(local_path)
        total = os.path.getsize(canonical_path)
        if show_progress_bar:
            if compare_hash:
                # print "upload progress:" to distinguish from hashing progress
                cprogress("upload progress:")
            pbar = zmwangx.pbar.ProgressBar(total)
        else:
            pbar = None
            pbar = zmwangx.pbar.ProgressBar(total) if show_progress_bar else None
        with open(canonical_path, "rb") as fileobj:
            position = 0
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
                else:
                    if response.status_code == 401:  # 401 Unauthorized
                        # set the weird_error flag and sleep 30 seconds
                        weird_error = True
                        time.sleep(30)
                    elif response.status_code == 416:
                        try:
                            # TODO: handle "Optimistic concurrency failure during fragmented upload"
                            if ((response.json()["error"]["innererror"]["code"] ==
                                 "fragmentRowCountCheckFailed")):
                                # raise if encountered weird error twice in a row
                                if weird_error:
                                    raise NotImplementedError(
                                        "got HTTP %d: %s; don't know what to do" %
                                        (416, response.text))
                                # set the weird_error flag and sleep 30 seconds
                                weird_error = True
                                time.sleep(30)
                            else:
                                weird_error = False
                        except KeyError:
                            pass
                    else:
                        weird_error = False

                    if response.status_code in {416, 500, 502, 503, 504}:
                        if response.status_code >= 500:
                            time.sleep(30)
                        else:
                            time.sleep(3)

                        try:
                            status_response = self.get(upload_url, path=path)
                        except requests.exceptions.RequestException as err:
                            logging.error(str(err))
                            raise
                        if status_response.status_code != 200:
                            raise OSError("failed to request upload status; got HTTP %d: %s" %
                                          (status_response.status_code, status_response.text))
                        expected_ranges = status_response.json()["nextExpectedRanges"]

                        # no remaining range
                        if not expected_ranges:
                            time.sleep(15)
                            if self.exists(path):
                                return
                            else:
                                raise OSError("no missing ranges, "
                                              "but '%s' does not exist on OneDrive" % path)

                        # multi-range not implemented
                        if len(expected_ranges) > 1:
                            raise NotImplementedError(
                                "got ranges %s; multi-range upload not implemented"
                                % str(expected_ranges))

                        # single range, set new position
                        position = int(expected_ranges[0].split("-")[0])
                        if pbar:
                            pbar.force_update(position)
                        continue

                    raise OSError("got HTTP %d: %s" %
                                  (response.status_code, response.text))

                position += size
                if pbar:
                    pbar.update(size)
            assert response.status_code in {200, 201}  # 200 OK or 201 Created

            if compare_hash:
                try:
                    remote_sha1sum = response.json()["file"]["hashes"]["sha1Hash"].lower()
                    logging.info("SHA-1 digest of remote file '%s': %s", path, remote_sha1sum)
                except KeyError:
                    raise KeyError("response JSON has no key file.hashes.sha1Hash")
                if local_sha1sum != remote_sha1sum:
                    msg = ("SHA-1 digest mismatch:\nlocal '%s': %s\nremote '%s': %s" %
                           (local_path, local_sha1sum, path, remote_sha1sum))
                    logging.error(msg)
                    raise OSError("error: %s" % msg)

            if pbar:
                pbar.finish()

    def exists(self, path):
        """Check if file or directory exists in OneDrive."""
        return self.geturl(path) is not None

    def geturl(self, path):
        """Get URL for a file or directory.

        Returns None if the requested item does not exist.

        """
        encoded_path = urllib.parse.quote(path)
        logging.info("requesting '%s'", encoded_path)
        metadata_response = self.get("drive/root:/%s" % encoded_path)
        status_code = metadata_response.status_code
        if status_code == 200:
            return metadata_response.json()["webUrl"]
        elif status_code == 404:
            return None
        else:
            raise OSError("got HTTP %d upon metadata request for '%s': %s" %
                          (status_code, path, metadata_response.text))
