============
 pyonedrive
============

*Caution: This package is Python 3.3+ only.*

`pyonedrive` is a OneDrive command line client using the new API. The code
quality isn't great, so don't hold your breath. [#]_ For a more complete
OneDrive solution in Python, see `mk-fg/python-onedrive
<https://github.com/mk-fg/python-onedrive>`_. Unfortunately,
``python-onedrive`` does not support — and the maintainer has no plan to
support — the new OneDrive API (see `#52
<https://github.com/mk-fg/python-onedrive/issues/52>`_).

.. [#] Yes, I cooked up convenient patches for all sorts of error scenarios
       along the way, resulting in horrible code. I will be able to do it
       cleaner if I ever get to rewrite this.

Features
--------

* Batch upload;
* Batch download;
* Create directories;
* List directory contents;
* Remove files and directories;
* Get item URL for viewing in web interface.

Seven console scripts are bundled with this package:

* ``onedrive-auth``;
* ``onedrive-geturl``;
* ``onedrive-ls``;
* ``onedrive-mkdir``;
* ``onedrive-rm``;
* ``onedrive-rmdir``;
* ``onedrive-upload``.

``onedrive-upload``, according to my testing, is more reliable than the CLI
shipped with ``python-onedrive``, as I have implemented retries and
safeguards. It is also more likely to win out in the long run since
``python-onedrive`` uses a `semi-private BITS API
<https://gist.github.com/rgregg/37ba8929768a62131e85>`_ that is subject to
change. Howeever, speed is not great when few uploads are running concurrently
(this is also the case for ``python-onedrive``); better use the Web interface
in that case when it's not too much hessle (use ``onedrive-geturl`` to get a
direct link to a remote directory).

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

* One needs to save the credentials to ``~/.config/onedrive/conf.ini``. The
  config file should be in the following format::

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

Best practices
--------------

* For whatever reason, the OneDrive resumable upload API responds slow or drops
  connection altogether quite often. Therefore, I have set a default timeout of
  15 seconds for each 10 MB chunk (add one second for each concurrent job). One
  may need to tweak the ``timeout`` parameter based on network condition to get
  best results.

* There are two modes of upload: streaming (each chunk) or not. The streaming
  mode uses less memory but is much more likely to hang (not forever since we
  have timeouts set in place) and generally slower.

  From my limited testing, a streaming worker uses ~15MB of memory, while a
  non-streaming one uses ~30MB at first and may grow to ~45MB for large files
  (maybe I have some hidden memory unreleased?). A streaming worker can be up
  to 30% slower (with timeouts accounted).

  Therefore, one should use nonstreaming workers (default) when there are only
  a few jobs, and streaming workers (specifying the ``-s, --streaming-upload``
  option) if there are a great number of concurrent jobs.

Known issues
------------

* Despite the timeout, very occasionally a request made through the
  ``requests`` module would stall, and there's little I can do in that case
  since it defies my order. Check ``~/.local/share/onedrive/onedrive.log`` to
  make sure the upload has really stalled (not your illusion). In that case,
  don't panic; the upload is resumable. Just interrupt the upload (``^C``),
  wait a minute or two, and try again.

Plans
-----

There are a couple of TODOs in the source code, waiting to be addressed.

Apart from that, I might implement addition features in the future, most likely
when I personally need something (and there might be a rewrite, as I mentioned
above).

..
   Local Variables:
   fill-column: 79
   End:
