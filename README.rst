============
 pyonedrive
============

**11/06/2015 update.** This project has been permanently shut after `Microsoft drops unlimited OneDrive storage after people use it for unlimited storage <http://arstechnica.com/information-technology/2015/11/microsoft-drops-unlimited-onedrive-storage-after-people-use-it-for-unlimited-storage/>`_.

**10/08/2015 update.** OneDrive has officially released `a Python SDK <https://github.com/OneDrive/onedrive-sdk-python>`_, so projects looking for an API should use that instead. Meanwhile, this project will still function as an independent CLI with quite helpful progress information and error messages (I won't switch to the official SDK until mine breaks or when I've got a load of time).

----

*Caution 1: This package is Python 3.3+ only.*

*Caution 2: Development has been deferred indefinitely as of July*
*20, 2015. However, contributions are welcome, and the maintainer will review*
*pull requests in a timely manner.*

``pyonedrive`` is a OneDrive API/CLI client using `OneDrive API v1.0 <https://dev.onedrive.com/README.htm>`_.

Structure of this document
==========================

* `Features <#features>`_

  - `Experimental/incomplete features <#experimentalincomplete-features>`_

* `Getting started <#getting-started>`_
* `Documentation <#documentation>`_
* `Notes <#notes>`_
* `Best practices <#best-practices>`_
* `Known issues <#known-issues>`_
* `Plans <#plans>`_
* `License <#license>`_

Features
========

* Batch upload;
* Batch download;
* Create directories;
* List directory (or recursively, directory tree) contents;
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
the "Getting started" section below.

Experimental/incomplete features
--------------------------------

* Directory upload (recursive), provided by the console script
  ``onedrive-dirupload``;
* Directory download (recursive), provided by the console script
  ``onedrive-dirdownload``;
* Batch renaming, provided by the console script ``onedrive-rename``.

Getting started
===============

To install this package, clone the repository, then in the root of the
directory, do ::

  pip install --process-dependency-links .

or ::

  ./setup.py install

Note that some older versions of ``setuptools`` might not work; in that case,
run ``pip install --upgrade pip`` first.

Once the package is installed, one still needs to `register an application
<https://dev.onedrive.com/app-registration.htm>`_ and save the credentials to
``~/.config/onedrive/conf.ini`` (or ``$XDG_CONFIG_HOME/onedrive/conf.ini``, if
``XDG_CONFIG_HOME`` is defined in your environment) to make any meaningful use
of this package. The config file should be in the following format::

    [oauth]
    client_id = XXXXXXXXXXXXXXXX
    client_secret = XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
    refresh_token = XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX

Note that the package assumes that full access has been granted (``wl.signin
wl.offline_access onedrive.readwrite``) to the client. If not, some API methods
might fail with ``onedrive.exceptions.APIRequestError``.

In case one doesn't have a refresh token yet, it can be automatically generated
and written to the config file by running ::

    onedrive-auth

(requires tty interaction and authorization in the browser). Just make sure
``client_id`` and ``client_secret`` are present in the config file before
running ``onedrive-auth``.

Documentation
=============

For console scripts, you may get usage instructions and option listings with
the ``-h, --help`` flag.

API doc may be built by running ::

  pip install tox
  tox docs

This will build HTML docs in ``docs/build/html``.

Notes
=====

* This package depends on some helper modules from my personal ``zmwangx``
  package (`link <https://github.com/zmwangx/pyzmwangx>`_). Fairly recent
  versions of ``setuptools`` will automatically install the package through git
  (see the "Installation" section).  Use a virtualenv if you don't want to
  pollute your global environment.

* This package is yet to reach stable (or even beta), so the API is subject to
  compatibility-breaking changes. I won't break it without a good reason,
  though.

  CLI, on the other hand, should be mostly backward-compatible, so it should be
  safe to use the console scripts in shell scripts (as long as you don't parse
  the output of, say, ``onedrive-ls``). There could be additions, and subtle
  behaviors in edge cases might be tweaked.

* Your config file is routinely overwritten with new tokens, so do not put
  comments in the config file (they are routinely wiped), and do not rely on
  the options having a particular order (not guaranteed).

Best practices
==============

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
============

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
  currently labeled as preview though (2015-06-15), so hopefully it will get
  better.

* Extended attributes and especially **resource forks** are not supported,
  because (1) I don't know how to upload them; (2) OneDrive doesn't support
  them anyway.

Plans
=====

A list of enhancement plans are `here
<https://github.com/zmwangx/pyonedrive/labels/enhancement>`_ in the issue
tracker.

Apart from that, I might implement additional features in the future, most
likely when I personally need something. Feel free to suggest features and
enhancements in the issue tracker though (or better yet, submit pull requests).

License
-------

The MIT license (MIT)

Copyright (c) 2015 Zhiming Wang

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.

..
   Local Variables:
   fill-column: 79
   End:
