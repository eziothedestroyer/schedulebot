"""Small TikTok Desktop OAuth and Content Posting (draft upload) client."""
from __future__ import annotations

import hashlib
import json
import mimetypes
import secrets
import threading
import urllib.parse
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer

from credential_store import get as get_secret, set_secret

AUTHORIZE = "https://www.tiktok.com/v2/auth/authorize/"
TOKEN = "https://open.tiktokapis.com/v2/oauth/token/"
UPLOAD_INIT = "https://open.tiktokapis.com/v2/post/publish/inbox/video/init/"
STATUS = "https://open.tiktokapis.com/v2/post/publish/status/fetch/"


def _request(url, *, data=None, token="", content_type="application/json; charset=UTF-8"):
    headers = {"Content-Type": content_type}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=data, headers=headers)
    with urllib.request.urlopen(req, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


class TikTokClient:
    def __init__(self, client_key, client_secret, callback=None):
        self.client_key = client_key.strip()
        self.client_secret = client_secret.strip()
        self.callback = callback or (lambda message: None)

    def connect(self):
        if not self.client_key or not self.client_secret:
            raise ValueError("Enter the TikTok client key and client secret first.")
        verifier = secrets.token_urlsafe(64)[:96]
        challenge = hashlib.sha256(verifier.encode()).hexdigest()
        state = secrets.token_urlsafe(24)
        result = {}

        class Handler(BaseHTTPRequestHandler):
            def do_GET(inner):
                query = urllib.parse.parse_qs(urllib.parse.urlparse(inner.path).query)
                result.update({k: v[0] for k, v in query.items()})
                inner.send_response(200)
                inner.send_header("Content-Type", "text/html; charset=utf-8")
                inner.end_headers()
                inner.wfile.write(b"<h2>ScheduleBot connected.</h2><p>You may close this tab.</p>")
            def log_message(self, *_):
                pass

        server = HTTPServer(("127.0.0.1", 0), Handler)
        redirect = f"http://127.0.0.1:{server.server_port}/callback/"
        params = urllib.parse.urlencode({"client_key": self.client_key,
            "response_type": "code", "scope": "user.info.basic,video.upload",
            "redirect_uri": redirect, "state": state, "code_challenge": challenge,
            "code_challenge_method": "S256"})
        webbrowser.open(f"{AUTHORIZE}?{params}")
        server.timeout = 180
        server.handle_request()
        server.server_close()
        if result.get("state") != state or not result.get("code"):
            raise RuntimeError(result.get("error_description", "TikTok authorization was cancelled or timed out."))
        form = urllib.parse.urlencode({"client_key": self.client_key,
            "client_secret": self.client_secret, "code": result["code"],
            "grant_type": "authorization_code", "redirect_uri": redirect,
            "code_verifier": verifier}).encode()
        tokens = _request(TOKEN, data=form, content_type="application/x-www-form-urlencoded")
        if not tokens.get("access_token"):
            raise RuntimeError(tokens.get("error_description", "TikTok did not return an access token."))
        set_secret("tiktok_access_token", tokens["access_token"])
        set_secret("tiktok_refresh_token", tokens.get("refresh_token", ""))
        return True

    def upload_draft(self, path):
        token = get_secret("tiktok_access_token")
        if not token:
            raise RuntimeError("Connect a TikTok account first.")
        size = path.stat().st_size
        init = _request(UPLOAD_INIT, token=token, data=json.dumps({"source_info": {
            "source": "FILE_UPLOAD", "video_size": size, "chunk_size": size,
            "total_chunk_count": 1}}).encode())
        if init.get("error", {}).get("code") not in (None, "ok"):
            raise RuntimeError(init["error"].get("message", init["error"]["code"]))
        data = init["data"]
        media = mimetypes.guess_type(path.name)[0] or "video/mp4"
        req = urllib.request.Request(data["upload_url"], data=path.read_bytes(), method="PUT",
            headers={"Content-Type": media, "Content-Length": str(size),
                     "Content-Range": f"bytes 0-{size - 1}/{size}"})
        with urllib.request.urlopen(req, timeout=300):
            pass
        return data["publish_id"]

    def status(self, publish_id):
        return _request(STATUS, token=get_secret("tiktok_access_token"),
                        data=json.dumps({"publish_id": publish_id}).encode())
