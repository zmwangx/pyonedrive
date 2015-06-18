#!/usr/bin/env python3

"""CLI interfaces for this package."""

# pylint: disable=broad-except

import argparse
import json
import multiprocessing
import os

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

    path = args.path
    try:
        print(client.geturl(path))
        return 0
    except onedrive.exceptions.FileNotFoundError:
        cerror("'%s' not found on OneDrive" % path)
        return 1
    except Exception as err:
        cerror("failed to get URL for '%s': %s: %s" %
               (path, type(err).__name__, str(err)))
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

def cli_rm():
    """Remove CLI."""
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", metavar="PATH", nargs="+",
                        help="path of remote item to remove")
    parser.add_argument("-r", "-R", "--recursive", action="store_true",
                        help="remove directories and their contents recursively")
    args = parser.parse_args()

    onedrive.log.logging_setup()
    client = onedrive.api.OneDriveAPIClient()

    returncode = 0
    for path in args.paths:
        try:
            client.rm(path, recursive=args.recursive)
            cprogress("'%s' removed from OneDrive" % path)
        except Exception as err:
            cerror("failed to remove '%s': %s: %s" %
                   (path, type(err).__name__, str(err)))
            returncode = 1
    return returncode

def cli_rmdir():
    """Remove empty directory CLI."""
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", metavar="DIRECTORY", nargs="+",
                        help="path of remote directory to remove")
    args = parser.parse_args()

    onedrive.log.logging_setup()
    client = onedrive.api.OneDriveAPIClient()

    returncode = 0
    for path in args.paths:
        try:
            client.rmdir(path)
            cprogress("directory '%s' removed from OneDrive" % path)
        except Exception as err:
            cerror("failed to remove '%s': %s: %s" %
                   (path, type(err).__name__, str(err)))
            returncode = 1
    return returncode

class CopyWorker(multiprocessing.Process):
    """A worker for copying an item on OneDrive.

    Parameters
    ----------
    client : onedrive.api.OneDriveAPIClient
    src, dst : str
        Source and destination of the copy operation. Passed to
        ``onedrive.api.OneDriveAPIClient.copy``.
    recursive : bool, optional
        Whether to allow recursive copying of a directory. Default is
        ``False``.
    overwrite, show_progress : bool, optional
        Passed to ``onedrive.api.OneDriveAPIClient.copy``. Defaults are
        ``False``.

    Attributes
    ----------
    src, dst : str

    """

    def __init__(self, client, src, dst, recursive=False, overwrite=False, show_progress=False):
        """Init."""
        super().__init__()
        self._client = client
        self.src = src
        self.dst = dst
        self._recursive = recursive
        self._overwrite = overwrite
        self._show_progress = show_progress

    def run(self):
        """Run the copy operation and monitor status.

        The exit code is either 0 or 1, indicating success or failure.

        """
        try:
            if not self._recursive:
                self._client.assert_file(self.src)
            self._client.copy(self.src, self.dst,
                              overwrite=self._overwrite, show_progress=self._show_progress)
            cprogress("finished copying '%s' to '%s'" % (self.src, self.dst))
            return 0
        except KeyboardInterrupt:
            cerror("copying '%s' to '%s' interrupted" % (self.src, self.dst))
            return 1
        except Exception as err:
            # catch any exception in a multiprocessing environment
            cerror("failed to copy '%s' to '%s': %s: %s" %
                   (self.src, self.dst, type(err).__name__, str(err)))
            return 1

def cli_mv_or_cp(util, util_name=None):
    """Mimic the behavior of coreutils ``mv`` or ``cp``.

    Parameters
    ----------
    util : {"mv", "cp"}
    util_name : str, optional
        Utility name shown in usage and help text. If omitted, will be
        set to the value of ``util``.

    """
    usage = """
    {util_name} [options] [-T] SOURCE DEST
    {util_name} [options] SOURCE... DIRECTORY
    {util_name} [options] -t DIRECTORY SOURCE...""".format(util_name=util_name)
    parser = argparse.ArgumentParser(usage=usage)
    parser.add_argument("paths", nargs="+",
                        help="sources, destination or directory, depending on invocation")

    parser.add_argument("-t", "--target-directory", action="store_true",
                        help="copy all SOURCE arguments into DIRECTORY")
    parser.add_argument("-T", "--no-target-directory", action="store_true",
                        help="treat DEST as exact destination, not directory")
    parser.add_argument("-f", "--force", action="store_true",
                        help="overwrite existing destinations")
    if util == "cp":
        parser.add_argument("-R", "-r", "--recursive", action="store_true",
                            help="copy directories recursively")
    args = parser.parse_args()

    onedrive.log.logging_setup()
    client = None  # defer setup

    # list of (src, dst) pairs, where dst is the full destination
    src_dst_list = []

    if args.target_directory and args.no_target_directory:
        cfatal_error("conflicting options -t and -T; see %s -h" % util_name)
        return 1
    if len(args.paths) < 2:
        cfatal_error("at least two paths required; see %s -h" % util_name)
        return 1
    elif len(args.paths) == 2:
        # single source item
        if args.target_directory:
            # mv/cp -t DIRECTORY SOURCE
            directory, source = args.paths
            dest = os.path.join(directory, os.path.basename(source))
        elif args.no_target_directory:
            # mv/cp -T SOURCE DEST
            source, dest = args.paths
        else:
            # no -t or -T flag
            # automatically decide based on whether dest is an existing directory
            client = onedrive.api.OneDriveAPIClient()
            if client.isdir(args.paths[1]):
                # mv/cp SOURCE DIRECTORY
                source, directory = args.paths
                dest = os.path.join(directory, os.path.basename(source))
            else:
                # mv/cp SOURCE DEST
                source, dest = args.paths
        src_dst_list.append((source, dest))
    else:
        # multiple source items
        if args.no_target_directory:
            cerror("option -T cannot be specified when there are multiple source items")
            return 1
        elif args.target_directory:
            # mv/cp -t DIRECTORY SOURCE...
            sources = args.paths[1:]
            directory = args.paths[0]
        else:
            # mv/cp SOURCE... DIRECTORY
            sources = args.paths[:-1]
            directory = args.paths[-1]

        src_dst_list = [(source, os.path.join(directory, os.path.basename(source)))
                        for source in sources]

    if client is None:
        client = onedrive.api.OneDriveAPIClient()

    # 3, 2, 1, action!
    returncode = 0
    if util == "mv":
        # move each item synchronously
        for src_dst_pair in src_dst_list:
            src, dst = src_dst_pair
            try:
                client.move(src, dst, overwrite=args.force)
                cprogress("moved '%s' to '%s'" % (src, dst))
            except Exception as err:
                cerror("failed to move '%s' to '%s': %s: %s" %
                       (src, dst, type(err).__name__, str(err)))
                returncode = 1
    else:
        # cp is more involved
        num_items = len(src_dst_list)
        show_progress = (num_items == 1) and zmwangx.pbar.autopbar()
        workers = [CopyWorker(client, src, dst, recursive=args.recursive, overwrite=args.force,
                              show_progress=show_progress)
                   for src, dst in src_dst_list]
        try:
            for worker in workers:
                worker.start()
            for worker in workers:
                worker.join()
                if worker.exitcode != 0:
                    returncode = 1
        except KeyboardInterrupt:
            returncode = 1

    return returncode

def cli_mv():
    """Alias for cli_mv_or_cp("mv", "onedrive-mv")."""
    return cli_mv_or_cp("mv", "onedrive-mv")

def cli_cp():
    """Alias for cli_mv_or_cp("cp", "onedrive-cp")."""
    return cli_mv_or_cp("cp", "onedrive-cp")

def cli_metadata():
    """Display metadata CLI."""
    parser = argparse.ArgumentParser(description="Dump JSON metadata of item.")
    parser.add_argument("path", help="remote path (file or directory)")
    args = parser.parse_args()

    onedrive.log.logging_setup()
    client = onedrive.api.OneDriveAPIClient()

    path = args.path
    try:
        print(json.dumps(client.metadata(path), indent=4))
        return 0
    except onedrive.exceptions.FileNotFoundError:
        cerror("'%s' not found on OneDrive" % path)
        return 1
    except Exception as err:
        cerror("failed to get URL for '%s': %s: %s" %
               (path, type(err).__name__, str(err)))
        return 1
