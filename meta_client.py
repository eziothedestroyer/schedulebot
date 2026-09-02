"""Meta OAuth, Facebook Page posting, and Instagram professional publishing."""
from __future__ import annotations
import json, secrets, time, urllib.parse, urllib.request, webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from credential_store import get as get_secret, set_secret

GRAPH_VERSION = "v23.0"
GRAPH = f"https://graph.facebook.com/{GRAPH_VERSION}"
REDIRECT = "http://localhost:53682/callback/"
SCOPES = "pages_show_list,pages_read_engagement,pages_manage_posts,instagram_basic,instagram_content_publish"

def _call(url, params=None, method="GET"):
    encoded = urllib.parse.urlencode(params or {}).encode()
    request = urllib.request.Request(url, data=encoded if method == "POST" else None)
    if method == "GET" and params:
        request.full_url += "?" + encoded.decode()
    with urllib.request.urlopen(request, timeout=90) as response:
        return json.loads(response.read().decode())

class MetaClient:
    def __init__(self, app_id, app_secret):
        self.app_id, self.app_secret = app_id.strip(), app_secret.strip()

    @classmethod
    def from_private_files(cls):
        root = Path.home() / "ScheduleBot" / "private"
        return cls((root / "meta-app-id.txt").read_text().strip(),
                   (root / "meta-app-secret.txt").read_text().strip())

    def connect(self):
        state, result = secrets.token_urlsafe(24), {}
        class Handler(BaseHTTPRequestHandler):
            def do_GET(inner):
                q = urllib.parse.parse_qs(urllib.parse.urlparse(inner.path).query)
                result.update({k: v[0] for k, v in q.items()})
                inner.send_response(200); inner.end_headers()
                inner.wfile.write(b"ScheduleBot connected to Meta. You may close this tab.")
            def log_message(self, *_): pass
        server = HTTPServer(("127.0.0.1", 53682), Handler); server.timeout = 180
        query = urllib.parse.urlencode({"client_id": self.app_id, "redirect_uri": REDIRECT,
            "state": state, "scope": SCOPES, "response_type": "code"})
        webbrowser.open(f"https://www.facebook.com/{GRAPH_VERSION}/dialog/oauth?{query}")
        server.handle_request(); server.server_close()
        if result.get("state") != state or not result.get("code"):
            raise RuntimeError(result.get("error_description", "Meta authorization cancelled or timed out."))
        token = _call(f"{GRAPH}/oauth/access_token", {"client_id": self.app_id,
            "client_secret": self.app_secret, "redirect_uri": REDIRECT, "code": result["code"]})
        set_secret("meta_user_access_token", token["access_token"])

    def pages(self):
        token = get_secret("meta_user_access_token")
        result = _call(f"{GRAPH}/me/accounts", {"fields": "id,name,access_token,instagram_business_account",
                                                 "access_token": token})
        return result.get("data", [])

    def facebook_post(self, page, message, link=""):
        params = {"message": message, "access_token": page["access_token"]}
        if link: params["link"] = link
        return _call(f"{GRAPH}/{page['id']}/feed", params, "POST")

    def instagram_post(self, page, media_url, caption):
        account = page.get("instagram_business_account", {}).get("id")
        if not account: raise RuntimeError("This Page has no linked professional Instagram account.")
        field = "video_url" if urllib.parse.urlparse(media_url).path.lower().endswith((".mp4", ".mov")) else "image_url"
        params = {field: media_url, "caption": caption, "access_token": page["access_token"]}
        if field == "video_url": params["media_type"] = "REELS"
        creation = _call(f"{GRAPH}/{account}/media", params, "POST")
        if field == "video_url": time.sleep(8)
        return _call(f"{GRAPH}/{account}/media_publish", {"creation_id": creation["id"],
                     "access_token": page["access_token"]}, "POST")
