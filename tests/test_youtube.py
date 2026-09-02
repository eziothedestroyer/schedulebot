import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from youtube_client import YouTubeClient


class FakeResponse:
    def __init__(self, payload=b"", headers=None):
        self.payload = payload
        self.headers = headers or {}

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return self.payload


class YouTubeUploadTests(unittest.TestCase):
    def client(self):
        client = YouTubeClient.__new__(YouTubeClient)
        client.access_token = lambda: "test-token"
        return client

    def test_uploads_video_and_reports_progress(self):
        with tempfile.TemporaryDirectory() as directory:
            video = Path(directory) / "vod.mp4"
            video.write_bytes(b"video-content")
            complete = FakeResponse(json.dumps({"id": "abc123"}).encode())
            start = FakeResponse(headers={"Location": "https://upload.example/session"})
            progress = []
            with patch("youtube_client.urllib.request.urlopen", side_effect=[start, complete]) as urlopen:
                result = self.client().upload_video(
                    video, "My VOD", privacy="unlisted",
                    progress_callback=lambda sent, total: progress.append((sent, total)))
            self.assertEqual(result["id"], "abc123")
            self.assertEqual(progress, [(len(b"video-content"), len(b"video-content"))])
            self.assertEqual(urlopen.call_args_list[0].args[0].method, "POST")
            self.assertEqual(urlopen.call_args_list[1].args[0].method, "PUT")

    def test_rejects_missing_and_empty_files(self):
        with self.assertRaises(FileNotFoundError):
            self.client().upload_video("missing.mp4", "Title")
        with tempfile.TemporaryDirectory() as directory:
            empty = Path(directory) / "empty.mp4"
            empty.touch()
            with self.assertRaises(ValueError):
                self.client().upload_video(empty, "Title")

    def test_requires_title(self):
        with tempfile.TemporaryDirectory() as directory:
            video = Path(directory) / "video.mp4"
            video.write_bytes(b"x")
            with self.assertRaises(ValueError):
                self.client().upload_video(video, "  ")


if __name__ == "__main__":
    unittest.main()
