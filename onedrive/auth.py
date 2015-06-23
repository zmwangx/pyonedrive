#!/usr/bin/env python3

"""Authenticate with OneDrive's API and make authenticated HTTP requests."""

import logging
import time
import urllib.parse
import webbrowser

import requests

import zmwangx.config
from zmwangx.colorout import cprogress, cprompt

import onedrive.log

class OneDriveOAuthClient(object):
    """Interface for dancing with OneDrive's OAuth.

    Parameters
    ----------
    authorize : bool, optional
        If ``authorize`` is ``True``, authorize the client and generate
        a new refresh token (requires tty interaction); otherwise,
        assume the refresh token is already present in the config file,
        and raise if it is not available.

    Returns
    -------
    OSError
        If the config file or any necessary config section/parameter is
        missing.

    """

    API_ENDPOINT = "https://api.onedrive.com/v1.0/"

    def __init__(self, authorize=False):
        """Initialize with a readily usable access token.

        Or additionally do the interactive authorization, if the
        ``authorize`` parameter is set to ``True``.

        """
        instruction_message = ("see https://github.com/zmwangx/pyonedrive#getting-started "
                               "for instructions on configuring your client")
        try:
            conf = zmwangx.config.INIConfig("onedrive/conf.ini")
        except OSError as err:
            raise OSError("%s; %s" % (str(err), instruction_message))

        if not conf.has_section("oauth"):
            raise OSError("'oauth' section missing from config file '%s'; %s" %
                          (conf._config_file, instruction_message))

        self._conf = conf

        try:
            self._client_id = conf["oauth"]["client_id"]
        except KeyError:
            raise OSError("'client_id' missing from config file '%s'; %s" %
                          (conf._config_file, instruction_message))
        try:
            self._client_secret = conf["oauth"]["client_secret"]
        except KeyError:
            raise OSError("'client_secret' missing from config file '%s'; %s" %
                          (conf._config_file, instruction_message))
        try:
            self._redirect_uri = conf["oauth"]["redirect_uri"]
        except KeyError:
            self._redirect_uri = "https://login.live.com/oauth20_desktop.srf"

        self.client = requests.Session()

        if authorize:
            self.authorize_client()
        else:
            try:
                self._refresh_token = conf["oauth"]["refresh_token"]
            except KeyError:
                msg = ("'refresh_token' missing from config file '%s' -- "
                       "you might want to run onedrive-auth to generate a refresh token; %s" %
                       (conf._config_file, instruction_message))
                raise OSError(msg)

        try:
            self._access_token = conf["oauth"]["access_token"]
            self._expires = int(conf["oauth"]["expires"])
        except KeyError:
            self.refresh_access_token()

    def authorize_client(self):
        """Authorize the client using the code flow."""

        # get authorization code
        #
        # authorization url:
        # https://login.live.com/oauth20_authorize.srf?client_id={client_id}&scope={scope}
        #  &response_type=code&redirect_uri={redirect_uri}
        auth_url = urllib.parse.urlunparse((
            "https",  # scheme
            "login.live.com",  # netloc
            "oauth20_authorize.srf",  # path
            "",  # params
            urllib.parse.urlencode({
                "client_id": self._client_id,
                "scope": "wl.signin wl.offline_access onedrive.readwrite",
                "response_type": "code",
                "redirect_uri": self._redirect_uri,
            }),  # query
            "",  # fragment
        ))
        webbrowser.open(auth_url)

        info = ("You are being directed to your default web browser for authorization. "
                " When done, copy the URL you are redirected to and paste it back here.")
        prompt = "Please enter the redirect URL: "
        try:
            redirect_url = cprompt(info=info, prompt=prompt)
        except EOFError:
            raise EOFError("no input for the redirect URL prompt")
        code = urllib.parse.parse_qs(urllib.parse.urlparse(redirect_url).query)["code"][0]

        # redeem the code
        payload = {
            "client_id": self._client_id,
            "redirect_uri": self._redirect_uri,
            "client_secret": self._client_secret,
            "code": code,
            "grant_type": "authorization_code",
        }
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        redeem_request = requests.post("https://login.live.com/oauth20_token.srf",
                                       data=payload, headers=headers)
        self._access_token = redeem_request.json()["access_token"]
        self._refresh_token = redeem_request.json()["refresh_token"]

        # rewrite config file
        self._conf["oauth"]["refresh_token"] = self._refresh_token
        self._conf.rewrite_configs()
        cprogress("Refresh token generated and written.")

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
        self._expires = int(time.time()) + refresh_request.json()["expires_in"]
        self.client.params.update({"access_token": self._access_token})

        self._conf["oauth"]["access_token"] = self._access_token
        self._conf["oauth"]["expires"] = str(self._expires)
        self._conf.rewrite_configs()

    def request(self, method, url, **kwargs):
        """HTTP request with OAuth."""
        path = kwargs.pop("path", None)
        url = urllib.parse.urljoin(self.API_ENDPOINT, url)

        if time.time() >= self._expires:
            self.refresh_access_token()
        response = self.client.request(method, url, **kwargs)

        onedrive.log.log_response(response, path=path)

        if response.status_code == 401:
            # refresh token and try again
            logging.warning("got HTTP 401; refreshing token and retrying")
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

def main():
    """Authorization CLI."""
    OneDriveOAuthClient(authorize=True)

if __name__ == "__main__":
    main()
