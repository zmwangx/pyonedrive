#!/usr/bin/env python3

"""Logging facilities."""

import logging
import os

def logging_setup():
    """Setup logging."""
    if "XDG_DATA_HOME" in os.environ:
        logfile = os.path.join(os.environ["XDG_DATA_HOME"], "onedrive", "onedrive.log")
    else:
        logfile = os.path.expanduser("~/.local/share/onedrive/onedrive.log")
    logdir = os.path.dirname(logfile)
    if not os.path.exists(logdir):
        os.makedirs(logdir, mode=0o700)

    logging.basicConfig(
        filename=logfile,
        level=logging.INFO,
        format="%(asctime)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
    )

def log_response(response, path=None):
    """Log response from requests."""
    if path:
        logging.info("%s: HTTP %d: %s", path, response.status_code, response.text)
    else:
        logging.info("HTTP %d: %s", response.status_code, response.text)
