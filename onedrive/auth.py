#!/usr/bin/env python3

"""Authenticate with OneDrive's API and make authenticated HTTP requests."""

import configparser
import os

import requests

class OneDriveOAuthClient(object):
    """Interface for dancing with OneDrive's OAuth."""

    API_ENDPOINT = "https://api.onedrive.com/v1.0"

    def __init__(self):
        """Initialize with a readily usable access token."""
        self._get_config_file()
        self._get_credentials()
        self.refresh_access_token()
        self.client = requests.session()
        self.client.params.update({"access_token": self._access_token})

    def _get_config_file(self):
        """Get config file path."""
        if "XDG_CONFIG_HOME" in os.environ:
            self._config_file = os.path.join(os.environ["XDG_CONFIG_HOME"],
                                             "onedrive", "conf.ini")
        else:
            self._config_file = os.path.expanduser("~/.config/onedrive/conf.ini")

    def _get_credentials(self):
        """Get OAuth credentials from config file."""
        conf = configparser.ConfigParser()
        conf.read(self._config_file)
        self._client_id = conf["oauth"]["client_id"]
        self._client_secret = conf["oauth"]["client_secret"]
        self._refresh_token = conf["oauth"]["refresh_token"]
        try:
            self._redirect_uri = conf["oauth"]["redirect_uri"]
        except KeyError:
            self._redirect_uri = "http://localhost:8000"

    def refresh_access_token(self):
        """Get new access token with refresh token."""
        payload = {
            "client_id": self._client_id,
            "client_secret": self._client_secret,
            "refresh_token": self._refresh_token,
            "redirect_uri": self._redirect_uri,
            "grant_type": "refresh_token",
        }
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        refresh_request = requests.post("https://login.live.com/oauth20_token.srf",
                                        data=payload, headers=headers)
        self._access_token = refresh_request.json()["access_token"]

    def get(self, url, **kwargs):
        """HTTP GET with OAuth."""
        url = "%s%s" % (self.API_ENDPOINT, url)
        return self.client.get(url, **kwargs)

    def options(self, url, **kwargs):
        """HTTP OPTIONS with OAuth."""
        url = "%s%s" % (self.API_ENDPOINT, url)
        return self.client.options(url, **kwargs)

    def head(self, url, **kwargs):
        """HTTP HEAD with OAuth."""
        url = "%s%s" % (self.API_ENDPOINT, url)
        return self.client.head(url, **kwargs)

    def post(self, url, data=None, json=None, **kwargs):
        """HTTP POST with OAuth."""
        url = "%s%s" % (self.API_ENDPOINT, url)
        return self.client.post(url, data, json, **kwargs)

    def put(self, url, data=None, **kwargs):
        """HTTP PUT with OAuth."""
        url = "%s%s" % (self.API_ENDPOINT, url)
        return self.client.put(url, data, **kwargs)

    def patch(self, url, data=None, **kwargs):
        """HTTP PATCH with OAuth."""
        url = "%s%s" % (self.API_ENDPOINT, url)
        return self.client.patch(url, data, **kwargs)

    def delete(self, url, **kwargs):
        """HTTP DELETE with OAuth."""
        url = "%s%s" % (self.API_ENDPOINT, url)
        return self.client.delete(url, **kwargs)
