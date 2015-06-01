#!/usr/bin/env python3

"""CLI interfaces for this package."""

import argparse
import multiprocessing

from zmwangx.colorout import cerror, cfatal_error, cprogress
import zmwangx.pbar

import onedrive.api
import onedrive.exceptions
import onedrive.log

class Uploader(object):
    """Uploader that uploads files to a given OneDrive directory."""

    def __init__(self, client, directory,
                 timeout=None,
                 stream=False, compare_hash=True, show_progress_bar=False):
        """Set client, directory, and parameters."""
        self._client = client
        self._directory = directory
        self._timeout = timeout
        self._stream = stream
        self._compare_hash = compare_hash
        self._show_progress_bar = show_progress_bar

    def __call__(self, local_path):
        """Upload a local file."""
        try:
            self._client.upload(self._directory, local_path,
                                timeout=self._timeout,
                                stream=self._stream,
                                compare_hash=self._compare_hash,
                                show_progress_bar=self._show_progress_bar)
            cprogress("finished uploading '%s'" % local_path)
            return 0
        except KeyboardInterrupt:
            cerror("upload of '%s' interrupted" % local_path)
            return 1
        # pylint: disable=broad-except
        except Exception as err:
            # catch any exception in a multiprocessing environment
            cerror("failed to upload '%s': %s: %s" %
                   (local_path, type(err).__name__, str(err)))
            return 1

def cli_upload():
    """Upload CLI."""
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", help="remote directory to upload to")
    parser.add_argument("local_paths", metavar="PATH", nargs="+",
                        help="path of local files to upload")
    parser.add_argument("--base-segment-timeout", type=float, default=15,
                        help="""base timeout for uploading a single
                        segment (10MiB) -- one second is added to this
                        base timeout for every concurrent job; default is
                        14""")
    parser.add_argument("-j", "--jobs", type=int, default=8,
                        help="number of concurrect uploads, use 0 for unlimited; default is 8")
    parser.add_argument("-s", "--streaming-upload", action="store_true")
    parser.add_argument("--no-check", action="store_true",
                        help="do not compare checksum of local and remote files")
    args = parser.parse_args()

    onedrive.log.logging_setup()
    client = onedrive.api.OneDriveAPIClient()

    directory = args.directory
    try:
        directory_url = client.geturl(directory, to_raise=True)
    except onedrive.exceptions.GeneralAPIException as err:
        cfatal_error(str(err))
        return 1
    cprogress("preparing to upload to '%s'" % directory)
    cprogress("directory URL: %s" % directory_url)

    num_files = len(args.local_paths)
    jobs = min(args.jobs, num_files) if args.jobs > 0 else num_files
    timeout = args.base_segment_timeout + jobs
    with multiprocessing.Pool(processes=jobs, maxtasksperchild=1) as pool:
        show_progress_bar = (num_files == 1) and zmwangx.pbar.autopbar()
        uploader = Uploader(client, directory,
                            timeout=timeout,
                            stream=args.streaming_upload,
                            compare_hash=not args.no_check,
                            show_progress_bar=show_progress_bar)
        returncodes = []
        try:
            returncodes = pool.map(uploader, args.local_paths, chunksize=1)
        except KeyboardInterrupt:
            returncodes.append(1)
        return 1 if 1 in returncodes else 0

def cli_geturl():
    """Get URL CLI."""
    parser = argparse.ArgumentParser()
    parser.add_argument("path", help="remote path (file or directory)")
    args = parser.parse_args()

    onedrive.log.logging_setup()
    client = onedrive.api.OneDriveAPIClient()

    try:
        print(client.geturl(args.path, to_raise=True))
        return 0
    except onedrive.exceptions.GeneralAPIException as err:
        cerror("%s: %s", type(err).__name__, str(err))
        return 1
