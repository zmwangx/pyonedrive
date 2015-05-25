#!/usr/bin/env python3

"""Streaming upload helper."""

import io
import logging
import requests

class FileSegment(io.IOBase):
    """Implements a file segment object that mimicks a binary file object."""

    def __init__(self, fileobj, start, length, total):
        """Init; seek to starting position."""
        self._fileobj = fileobj
        self._start = start
        # end is last readable byte in the segment + 1
        self._end = min(start + length, total)
        assert self._start < self._end
        self._fileobj.seek(start)
        self._length = length
        self.len = length  # for requests.utils.super_len

    def read(self, size=-1):
        """Read up to the end of fragment."""
        size = size if size is not None else -1
        maxsize = self._end - self._fileobj.tell()
        if size < 0 or size > maxsize:
            size = maxsize
        return self._fileobj.read(size)

def stream_put_file_segment(session, url, fileobj, start, length, total,
                            timeout=None, retries=5, path=None):
    """PUT a file segment using requests' streaming upload feature."""
    for retry in range(retries + 1):
        segment = FileSegment(fileobj, start, length, total)
        headers = {"Content-Range": "bytes %d-%d/%d" % (start, start + length - 1, total)}
        try:
            return session.put(url, data=segment, headers=headers, timeout=timeout, path=path)
        except requests.exceptions.RequestException as err:
            if path:
                logging.warning("%s: %s", path, str(err))
            else:
                logging.warning(str(err))
            if retry == retries:
                raise

def put_file_segment(session, url, segment, start, length, total,
                     timeout=None, retries=5, path=None):
    """PUT a file segment already loaded into a bytes object."""
    headers = {"Content-Range": "bytes %d-%d/%d" % (start, start + length - 1, total)}
    for retry in range(retries + 1):
        try:
            return session.put(url, data=segment, headers=headers, timeout=timeout, path=path)
        except requests.exceptions.RequestException as err:
            if path:
                logging.warning("%s: %s", path, str(err))
            else:
                logging.warning(str(err))
            if retry == retries:
                raise
