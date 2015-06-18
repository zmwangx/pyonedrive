============
 pyonedrive
============

*Caution: This package is Python 3.3+ only.*

`pyonedrive` is a OneDrive command line client using `OneDrive API v1.0
<https://dev.onedrive.com/README.htm>`_.

Features
--------

* Batch upload;
* Batch download;
* Create directories;
* List directory contents;
* Move or copy files and directories;
* Remove files and directories;
* Get item URL for viewing in web interface (among other metadata);
* A public API exposing all features listed above, and some familiar filesystem
  operations similar to those exposed by STL ``os`` and ``os.path``.

The following console scripts are bundled with this package:

* ``onedrive-auth``;
* ``onedrive-cp``;
* ``onedrive-geturl``;
* ``onedrive-ls``;
* ``onedrive-metadata``;
* ``onedrive-mkdir``;
* ``onedrive-mv``;
* ``onedrive-rm``;
* ``onedrive-rmdir``;
* ``onedrive-upload``.

The names of the scripts are pretty much self-explanatory. To use any of these,
you will need to first register an application and authorize the client. See
the "Notes" section below.

Installation
------------

Clone the repository, then in the root of the directory, do ::

  pip install .

or ::

  ./setup.py install

Note that some older versions of ``setuptools`` might not work; in that case,
run ``pip install --upgrade pip`` first.

Notes
-----

* Note that this package depends on some helper modules from my ``zmwangx``
  package (`link <https://github.com/zmwangx/pyzmwangx>`_). ``setuptools`` will
  automatically install the package through git (see the "Installation"
  section).  Use a virtualenv if you don't want to pollute your global
  environment.

* One needs to `register an application
  <https://dev.onedrive.com/app-registration.htm>`_ and save the credentials to
  ``~/.config/onedrive/conf.ini``. The config file should be in the following
  format::

    [oauth]
    client_id = XXXXXXXXXXXXXXXX
    client_secret = XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
    refresh_token = XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX

  In case one doesn't have the refresh token, it can be automatically generated
  and written to the config file by running ::

    onedrive-auth

  (requires tty interaction). Just make sure ``client_id`` and
  ``client_secret`` are present in the config file before running
  ``onedrive-auth``.

* This package is yet to reach stable (or even beta), so the API is subject to
  compatibility-breaking changes. I won't break it without a good reason,
  though.

  CLI, on the other hand, should be mostly backward-compatible. There could be
  additions, and subtle behaviors in edge cases might be tweaked.

Best practices
--------------

* For whatever reason, the OneDrive resumable upload API responds slow or drops
  connection altogether fairly often. Therefore, I have set a default base
  timeout of 15 seconds for each 10 MB chunk (add one second for each
  concurrent job). One may need to tweak the ``timeout`` parameter based on
  network condition to get best results. For CLI use, see the
  ``--base-segment-timeout`` option of ``onedrive-upload``.

* There are two modes of upload: streaming (which doesn't load full chunks into
  memory) or not. The streaming mode uses less memory but is much more likely
  to hang (not forever since we have timeouts set in place) and generally
  slower, for whatever reason.

  From my limited testing, a streaming worker uses ~15MB of memory, while a
  non-streaming one uses ~30MB at first and may grow to ~45MB for large files
  (maybe I have some hidden memory unreleased?). A streaming worker can be up
  to 30% slower (with timeouts accounted).

  Therefore, one should use nonstreaming workers (default) when the worker
  count is relatively low (what counts as low depends on your expectation of
  memory usage), and streaming workers (with the ``-s, --streaming-upload``
  option) only if there are a great number of concurrent jobs.

Known issues
------------

* Despite the timeout, very occasionally a request made through the
  ``requests`` module would stall, and there's little I can do in that case
  since it defies my order. Check ``~/.local/share/onedrive/onedrive.log`` to
  make sure the upload has really stalled (not your illusion). In that case,
  don't panic; the upload is resumable. Just interrupt the upload (``^C``),
  wait a minute or two, and try again.

* When copying items from the command line, you might see weird "actions in
  progress..." in the web interface. Just don't panic and don't click cancel.

  In fact, at the moment of writing, the copy API is not very reliable (it
  might randomly fail on large files, e.g., those greater than 1GB). The API is
  labeled as preview though (2015-06-15), so hopefully it will get better.

* Extended attributes and especially **resource forks** are not supported,
  because (1) I don't know how to upload them; (2) OneDrive doesn't support
  them anyway.

Plans
-----

A list of enhancement plans are `here
<https://github.com/zmwangx/pyonedrive/labels/enhancement>`_ in the issue
tracker.

Apart from that, I might implement additional features in the future, most
likely when I personally need something. Feel free to suggest features and
enhancements in the issue tracker though (or better yet, submit pull requests).

..
   Local Variables:
   fill-column: 79
   End:
