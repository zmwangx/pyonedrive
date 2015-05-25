#!/usr/bin/env python3

"""Authenticate with OneDrive's API and make authenticated HTTP requests."""

import configparser
import os
import time
import urllib.parse

import requests

import onedrive.log

class OneDriveOAuthClient(object):
    """Interface for dancing with OneDrive's OAuth."""

    API_ENDPOINT = "https://api.onedrive.com/v1.0/"

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
        onedrive.log.log_response(refresh_request)
        self._access_token = refresh_request.json()["access_token"]
        # deduct a minute from expire time just to be safe
        self._expires = time.time() + refresh_request.json()["expires_in"] - 60

    def request(self, method, url, **kwargs):
        """HTTP request with OAuth."""
        path = kwargs.pop("path", None)
        url = urllib.parse.urljoin(self.API_ENDPOINT, url)

        if time.time() >= self._expires:
            self.refresh_access_token()
        response = self.client.request(method, url, **kwargs)

        onedrive.log.log_response(response, path=path)

        return response

    def get(self, url, params=None, **kwargs):
        """HTTP GET with OAuth."""
        return self.request("get", url, params=params, **kwargs)

    def options(self, url, **kwargs):
        """HTTP OPTIONS with OAuth."""
        return self.request("options", url, **kwargs)

    def head(self, url, **kwargs):
        """HTTP HEAD with OAuth."""
        return self.request("head", url, **kwargs)

    def post(self, url, data=None, json=None, **kwargs):
        """HTTP POST with OAuth."""
        return self.request("post", url, data=data, json=json, **kwargs)

    def put(self, url, data=None, **kwargs):
        """HTTP PUT with OAuth."""
        return self.request("put", url, data=data, **kwargs)

    def patch(self, url, data=None, **kwargs):
        """HTTP PATCH with OAuth."""
        return self.request("patch", url, data=data, **kwargs)

    def delete(self, url, **kwargs):
        """HTTP DELETE with OAuth."""
        return self.request("delete", url, **kwargs)
