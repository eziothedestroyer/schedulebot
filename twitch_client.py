"""Small Twitch Helix client with desktop-friendly Device Code authorization."""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request


IDENTITY = "https://id.twitch.tv/oauth2"
HELIX = "https://api.twitch.tv/helix"
SCOPES = "channel:manage:broadcast clips:edit"


class TwitchClient:
    def __init__(self, client_id, client_secret="", access_token="", refresh_token="", token_callback=None):
        self.client_id = client_id.strip()
        self.client_secret = client_secret.strip()
        self.access_token = access_token.strip()
        self.refresh_token = refresh_token.strip()
        self.token_callback = token_callback
        if not self.client_id:
            raise ValueError("The Twitch Client ID file is missing or empty.")

    @staticmethod
    def _form(url, values):
        data = urllib.parse.urlencode(values).encode()
        request = urllib.request.Request(url, data=data, method="POST",
                                         headers={"Content-Type": "application/x-www-form-urlencoded"})
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                return json.load(response)
        except urllib.error.HTTPError as error:
            try:
                detail = json.loads(error.read()).get("message", str(error))
            except Exception:
                detail = str(error)
            raise RuntimeError(detail) from error
        except urllib.error.URLError as error:
            raise RuntimeError("Could not reach Twitch. Check your internet connection and try again.") from error

    def _accept_tokens(self, tokens):
        self.access_token = tokens["access_token"]
        self.refresh_token = tokens.get("refresh_token", self.refresh_token)
        if self.token_callback:
            self.token_callback(self.access_token, self.refresh_token)
        return tokens

    def start_device_authorization(self):
        return self._form(IDENTITY + "/device", {"client_id": self.client_id, "scopes": SCOPES})

    def finish_device_authorization(self, device):
        deadline = time.monotonic() + int(device.get("expires_in", 900))
        interval = max(1, int(device.get("interval", 5)))
        values = {"client_id": self.client_id, "scopes": SCOPES,
                  "device_code": device["device_code"],
                  "grant_type": "urn:ietf:params:oauth:grant-type:device_code"}
        while time.monotonic() < deadline:
            time.sleep(interval)
            try:
                token = self._form(IDENTITY + "/token", values)
                return self._accept_tokens(token)
            except RuntimeError as error:
                detail = str(error).lower()
                if "authorization_pending" in detail:
                    continue
                if "slow_down" in detail:
                    interval += 1
                    continue
                if "access_denied" in detail:
                    raise RuntimeError("Twitch authorization was cancelled. Click Connect Twitch to try again.") from error
                if "expired" in detail or "invalid device code" in detail:
                    raise RuntimeError("The Twitch authorization code expired. Click Connect Twitch to get a new code.") from error
                raise
        raise TimeoutError("Twitch authorization expired. Click Connect Twitch and try again.")

    def refresh_access_token(self):
        if not self.refresh_token:
            raise RuntimeError("Your Twitch session expired. Click Connect Twitch to authorize again.")
        values = {"client_id": self.client_id, "refresh_token": self.refresh_token,
                  "grant_type": "refresh_token"}
        if self.client_secret:
            values["client_secret"] = self.client_secret
        return self._accept_tokens(self._form(IDENTITY + "/token", values))

    def _api(self, path, method="GET", query=None, payload=None, retry=True):
        if not self.access_token:
            raise RuntimeError("Connect your Twitch account first.")
        url = HELIX + path
        if query:
            url += "?" + urllib.parse.urlencode(query)
        data = json.dumps(payload).encode() if payload is not None else None
        request = urllib.request.Request(url, data=data, method=method, headers={
            "Authorization": "Bearer " + self.access_token,
            "Client-Id": self.client_id,
            "Content-Type": "application/json",
        })
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                body = response.read()
                return json.loads(body) if body else {}
        except urllib.error.HTTPError as error:
            if error.code == 401 and retry and self.refresh_token:
                self.refresh_access_token()
                return self._api(path, method, query, payload, retry=False)
            try:
                detail = json.loads(error.read()).get("message", str(error))
            except Exception:
                detail = str(error)
            raise RuntimeError(detail) from error
        except urllib.error.URLError as error:
            raise RuntimeError("Could not reach Twitch. Check your internet connection and try again.") from error

    def user(self):
        users = self._api("/users").get("data", [])
        if not users:
            raise RuntimeError("Twitch did not return the connected channel.")
        return users[0]

    def channel(self, broadcaster_id):
        channels = self._api("/channels", query={"broadcaster_id": broadcaster_id}).get("data", [])
        return channels[0] if channels else {}

    def find_category(self, name):
        matches = self._api("/search/categories", query={"query": name, "first": 20}).get("data", [])
        exact = next((item for item in matches if item.get("name", "").casefold() == name.casefold()), None)
        return exact or (matches[0] if matches else None)

    def update_channel(self, broadcaster_id, title, category="", tags=None):
        payload = {"title": title}
        if category:
            match = self.find_category(category)
            if not match:
                raise RuntimeError(f"No Twitch category matched {category!r}.")
            payload["game_id"] = match["id"]
        if tags:
            payload["tags"] = tags[:10]
        self._api("/channels", method="PATCH", query={"broadcaster_id": broadcaster_id}, payload=payload)
        return payload

    def stream_status(self, broadcaster_id):
        streams = self._api("/streams", query={"user_id": broadcaster_id}).get("data", [])
        return streams[0] if streams else None

    def create_marker(self, broadcaster_id, description=""):
        payload = {"user_id": broadcaster_id}
        if description:
            payload["description"] = description[:140]
        markers = self._api("/streams/markers", method="POST", payload=payload).get("data", [])
        return markers[0] if markers else {}

    def create_clip(self, broadcaster_id, title="", duration=30):
        query = {"broadcaster_id": broadcaster_id, "duration": max(5, min(60, duration))}
        if title:
            query["title"] = title[:100]
        clips = self._api("/clips", method="POST", query=query).get("data", [])
        if not clips:
            raise RuntimeError("Twitch did not return a clip.")
        return clips[0]
