"""Google Desktop OAuth and YouTube Live broadcast client."""
from __future__ import annotations

import base64
import hashlib
import json
import mimetypes
import secrets
import time
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
UPLOAD_API = "https://www.googleapis.com/upload/youtube/v3/videos"
SCOPE = "https://www.googleapis.com/auth/youtube https://www.googleapis.com/auth/yt-analytics.readonly"


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

    def upload_video(self, path, title, description="", privacy="private", tags=None,
                     progress_callback=None, chunk_size=8 * 1024 * 1024):
        """Upload a regular video or VOD with YouTube's resumable protocol."""
        path = Path(path)
        if not path.is_file():
            raise FileNotFoundError(f"Video file not found: {path}")
        if not title.strip():
            raise ValueError("Enter a video title before uploading.")
        if privacy not in {"private", "unlisted", "public"}:
            raise ValueError("Privacy must be private, unlisted, or public.")
        total = path.stat().st_size
        if total < 1:
            raise ValueError("The selected video file is empty.")
        mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        if not (mime.startswith("video/") or mime == "application/octet-stream"):
            mime = "application/octet-stream"
        body = json.dumps({
            "snippet": {"title": title.strip(), "description": description.strip(),
                        "tags": [tag.strip() for tag in (tags or []) if tag.strip()]},
            "status": {"privacyStatus": privacy, "selfDeclaredMadeForKids": False},
        }).encode()
        request = urllib.request.Request(
            UPLOAD_API + "?uploadType=resumable&part=snippet,status",
            data=body, method="POST", headers={
                "Authorization": "Bearer " + self.access_token(),
                "Content-Type": "application/json; charset=UTF-8",
                "X-Upload-Content-Length": str(total),
                "X-Upload-Content-Type": mime,
            })
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                upload_url = response.headers.get("Location")
        except urllib.error.HTTPError as error:
            raise RuntimeError(self._google_error(error, "YouTube rejected the upload request.")) from error
        except urllib.error.URLError as error:
            raise RuntimeError("Could not reach YouTube. Check your internet connection and try again.") from error
        if not upload_url:
            raise RuntimeError("YouTube did not return a resumable upload URL.")

        sent = 0
        with path.open("rb") as video:
            while sent < total:
                video.seek(sent)
                chunk = video.read(min(chunk_size, total - sent))
                end = sent + len(chunk) - 1
                upload = urllib.request.Request(upload_url, data=chunk, method="PUT", headers={
                    "Authorization": "Bearer " + self.access_token(),
                    "Content-Type": mime,
                    "Content-Length": str(len(chunk)),
                    "Content-Range": f"bytes {sent}-{end}/{total}",
                })
                for attempt in range(4):
                    try:
                        with urllib.request.urlopen(upload, timeout=300) as response:
                            result = json.loads(response.read().decode("utf-8"))
                        sent = end + 1
                        if progress_callback:
                            progress_callback(sent, total)
                        if sent >= total:
                            return result
                        break
                    except urllib.error.HTTPError as error:
                        if error.code == 308:
                            received = error.headers.get("Range", "")
                            sent = int(received.rsplit("-", 1)[-1]) + 1 if "-" in received else sent
                            if progress_callback:
                                progress_callback(sent, total)
                            break
                        if error.code in {500, 502, 503, 504} and attempt < 3:
                            time.sleep(2 ** attempt)
                            continue
                        raise RuntimeError(self._google_error(error, "YouTube video upload failed.")) from error
                    except urllib.error.URLError as error:
                        if attempt < 3:
                            time.sleep(2 ** attempt)
                            continue
                        raise RuntimeError("The YouTube upload was interrupted. Check your connection and try again.") from error
        raise RuntimeError("YouTube ended the upload without returning a video ID.")

    @staticmethod
    def _google_error(error, fallback):
        try:
            payload = json.loads(error.read().decode("utf-8"))
            return payload.get("error", {}).get("message") or fallback
        except Exception:
            return fallback

    def create_stream(self, title="ScheduleBot OBS Stream"):
        body = {"snippet": {"title": title}, "cdn": {"frameRate": "variable",
                "ingestionType": "rtmp", "resolution": "variable"},
                "contentDetails": {"isReusable": True}}
        return _json_request(f"{API}/liveStreams?part=snippet,cdn,contentDetails",
                             data=json.dumps(body).encode(), token=self.access_token())

    def bind(self, broadcast_id, stream_id):
        return _json_request(f"{API}/liveBroadcasts/bind?id={urllib.parse.quote(broadcast_id)}&part=id,contentDetails&streamId={urllib.parse.quote(stream_id)}",
                             data=b"", token=self.access_token())

    def transition(self, broadcast_id, status):
        return _json_request(f"{API}/liveBroadcasts/transition?id={urllib.parse.quote(broadcast_id)}&part=id,status&broadcastStatus={urllib.parse.quote(status)}",
                             data=b"", token=self.access_token())

    def delete_chat_message(self, message_id):
        request = urllib.request.Request(f"{API}/liveChat/messages?id={urllib.parse.quote(message_id)}",
            method="DELETE", headers={"Authorization": f"Bearer {self.access_token()}"})
        with urllib.request.urlopen(request, timeout=60): pass

    def analytics(self, start_date, end_date):
        query = urllib.parse.urlencode({"ids": "channel==MINE", "startDate": start_date,
            "endDate": end_date, "metrics": "views,estimatedMinutesWatched,averageViewDuration,subscribersGained",
            "dimensions": "day", "sort": "day"})
        return _json_request(f"https://youtubeanalytics.googleapis.com/v2/reports?{query}", token=self.access_token())
