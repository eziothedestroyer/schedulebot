"""Google Desktop OAuth and YouTube Live broadcast client."""
from __future__ import annotations

import base64
import hashlib
import json
import secrets
import urllib.parse
import urllib.request
import webbrowser
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from credential_store import get as get_secret, set_secret

AUTH = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN = "https://oauth2.googleapis.com/token"
API = "https://www.googleapis.com/youtube/v3"
SCOPE = "https://www.googleapis.com/auth/youtube"


def _json_request(url, *, data=None, token="", form=False):
    headers = {"Content-Type": "application/x-www-form-urlencoded" if form else "application/json; charset=UTF-8"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, data=data, headers=headers)
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


class YouTubeClient:
    def __init__(self, credentials_path):
        values = json.loads(Path(credentials_path).read_text(encoding="utf-8"))
        self.config = values.get("installed") or values.get("web")
        if not self.config:
            raise ValueError("The Google OAuth JSON is not a Desktop client file.")

    def connect(self):
        verifier = secrets.token_urlsafe(64)
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
        state, result = secrets.token_urlsafe(24), {}

        class Handler(BaseHTTPRequestHandler):
            def do_GET(inner):
                query = urllib.parse.parse_qs(urllib.parse.urlparse(inner.path).query)
                result.update({key: value[0] for key, value in query.items()})
                inner.send_response(200); inner.send_header("Content-Type", "text/html; charset=utf-8"); inner.end_headers()
                inner.wfile.write(b"<h2>ScheduleBot connected to YouTube.</h2><p>You may close this tab.</p>")
            def log_message(self, *_): pass

        server = HTTPServer(("127.0.0.1", 0), Handler)
        redirect = f"http://127.0.0.1:{server.server_port}"
        query = urllib.parse.urlencode({"client_id": self.config["client_id"], "redirect_uri": redirect,
            "response_type": "code", "scope": SCOPE, "access_type": "offline",
            "prompt": "consent", "state": state, "code_challenge": challenge,
            "code_challenge_method": "S256"})
        webbrowser.open(f"{AUTH}?{query}")
        server.timeout = 180; server.handle_request(); server.server_close()
        if result.get("state") != state or not result.get("code"):
            raise RuntimeError(result.get("error", "Google authorization was cancelled or timed out."))
        form = {"client_id": self.config["client_id"], "client_secret": self.config.get("client_secret", ""),
                "code": result["code"], "code_verifier": verifier,
                "grant_type": "authorization_code", "redirect_uri": redirect}
        tokens = _json_request(TOKEN, data=urllib.parse.urlencode(form).encode(), form=True)
        set_secret("youtube_access_token", tokens["access_token"])
        if tokens.get("refresh_token"):
            set_secret("youtube_refresh_token", tokens["refresh_token"])
        return True

    def access_token(self):
        refresh = get_secret("youtube_refresh_token")
        if refresh:
            form = {"client_id": self.config["client_id"], "client_secret": self.config.get("client_secret", ""),
                    "refresh_token": refresh, "grant_type": "refresh_token"}
            tokens = _json_request(TOKEN, data=urllib.parse.urlencode(form).encode(), form=True)
            set_secret("youtube_access_token", tokens["access_token"])
        token = get_secret("youtube_access_token")
        if not token:
            raise RuntimeError("Connect your YouTube account first.")
        return token

    def create_broadcast(self, title, description, local_start, privacy):
        start = datetime.fromisoformat(local_start.strip()).astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
        body = {"snippet": {"title": title.strip(), "description": description.strip(),
                            "scheduledStartTime": start},
                "status": {"privacyStatus": privacy, "selfDeclaredMadeForKids": False},
                "contentDetails": {"enableAutoStart": True, "enableAutoStop": True}}
        url = f"{API}/liveBroadcasts?part=snippet,status,contentDetails"
        return _json_request(url, data=json.dumps(body).encode(), token=self.access_token())
