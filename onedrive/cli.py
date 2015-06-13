#!/usr/bin/env python3

"""CLI interfaces for this package."""

# pylint: disable=broad-except

import argparse
import multiprocessing

from zmwangx.colorout import cerror, cfatal_error, cprogress
import zmwangx.humansize
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
                        help="path of local file to upload")
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
        directory_url = client.geturl(directory)
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
        print(client.geturl(args.path))
        return 0
    except onedrive.exceptions.GeneralAPIException as err:
        cerror("%s: %s" % (type(err).__name__, str(err)))
        return 1

def cli_ls():
    """List items CLI."""
    description = """Mimic ls on OneDrive items. By default the long
    format is used: type, child count, size, name. Type is a single
    character, d or -. Note that this differs from ls -l in several
    ways: mode is only a single character, distinguishing files and
    directories; link count is replaced by child count, and for files
    this is -; size is human readable by default (use +h/++human to turn
    off); there are no owner, group, creation time and modification time
    columns. Use +l/++long to turn off long format."""
    parser = argparse.ArgumentParser(description=description, prefix_chars="-+")
    parser.add_argument("path", help="remote directory")
    parser.add_argument("+h", "++human", action="store_false",
                        help="turn off human readable format")
    parser.add_argument("+l", "++long", action="store_false",
                        help="turn off long format")
    args = parser.parse_args()

    onedrive.log.logging_setup()
    client = onedrive.api.OneDriveAPIClient()

    try:
        itemtype, items = client.list(args.path)
    except onedrive.exceptions.GeneralAPIException as err:
        cerror("%s: %s" % (type(err).__name__, str(err)))
        return 1

    if not args.long:
        for item in items:
            print(item["name"])
        return 0

    # collect stat for each item
    item_stats_list = []
    for item in items:
        itemtype = "d" if "folder" in item else "-"
        try:
            childcount_s = str(item["folder"]["childCount"])
        except KeyError:
            childcount_s = "-"
        size = item["size"]
        if args.human:
            size_s = zmwangx.humansize.humansize(size, prefix="iec", unit="")
        else:
            size_s = str(size)
        name = item["name"]
        item_stats_list.append((itemtype, childcount_s, size_s, name))
    # calculate max width of each field (except the last field: name)
    widths = [0, 0, 0]
    for item_stats in item_stats_list:
        for field_index in range(3):
            if len(item_stats[field_index]) > widths[field_index]:
                widths[field_index] = len(item_stats[field_index])
    # print
    format_string = "%{widths[0]}s %{widths[1]}s %{widths[2]}s %s".format(widths=widths)
    for item_stats in item_stats_list:
        print(format_string % item_stats)
    return 0

class Downloader(object):
    """Downloader that downloads files from OneDrive."""

    def __init__(self, client, compare_hash=True, show_progress_bar=False):
        """Set client and paramters."""
        self._client = client
        self._compare_hash = compare_hash
        self._show_progress_bar = show_progress_bar

    def __call__(self, path):
        """Download a remote file."""
        try:
            self._client.download(path, compare_hash=self._compare_hash,
                                  show_progress_bar=self._show_progress_bar)
            cprogress("finished downloading '%s'" % path)
            return 0
        except KeyboardInterrupt:
            cerror("download of '%s' interrupted" % path)
            return 1
        except Exception as err:
            # catch any exception in a multiprocessing environment
            cerror("failed to download '%s': %s: %s" %
                   (path, type(err).__name__, str(err)))
            return 1

def cli_download():
    """Download CLI."""
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", metavar="PATH", nargs="+",
                        help="path of remote file to download")
    parser.add_argument("-j", "--jobs", type=int, default=0,
                        help="number of concurrect downloads, use 0 for unlimited; default is 0")
    parser.add_argument("--no-check", action="store_true",
                        help="do not compare checksum of remote and local files")
    args = parser.parse_args()

    onedrive.log.logging_setup()
    client = onedrive.api.OneDriveAPIClient()

    num_files = len(args.paths)
    jobs = min(args.jobs, num_files) if args.jobs > 0 else num_files
    with multiprocessing.Pool(processes=jobs, maxtasksperchild=1) as pool:
        show_progress_bar = (num_files == 1) and zmwangx.pbar.autopbar()
        downloader = Downloader(client, compare_hash=not args.no_check,
                                show_progress_bar=show_progress_bar)
        returncodes = []
        try:
            returncodes = pool.map(downloader, args.paths, chunksize=1)
        except KeyboardInterrupt:
            returncodes.append(1)
        return 1 if 1 in returncodes else 0

def cli_mkdir():
    """Make directory CLI."""
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", metavar="DIRECTORY", nargs="+",
                        help="path of remote directory to create")
    parser.add_argument("-p", "--parents", action="store_true",
                        help="no error if existing, make parent directories as needed")
    args = parser.parse_args()

    onedrive.log.logging_setup()
    client = onedrive.api.OneDriveAPIClient()

    returncode = 0
    for path in args.paths:
        try:
            if args.parents:
                metadata = client.makedirs(path, exist_ok=True)
            else:
                metadata = client.mkdir(path)
            cprogress("directory '%s' created at '%s'" %
                      (path, metadata["webUrl"]))
        except Exception as err:
            cerror("failed to create directory '%s': %s: %s" %
                   (path, type(err).__name__, str(err)))
            returncode = 1
    return returncode
