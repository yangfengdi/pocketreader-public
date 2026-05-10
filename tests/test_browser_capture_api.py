import os
import tempfile
import unittest
from pathlib import Path


_tmp = tempfile.TemporaryDirectory()
os.environ.update(
    {
        "APP_USERNAME": "test-user",
        "APP_PASSWORD": "CHANGE_ME",
        "APP_SECRET_KEY": "dev-secret",
        "FEED_TOKEN": "feed-token",
        "IMPORT_TOKEN": "import-token",
        "APP_BASE_URL": "http://127.0.0.1:4780",
        "APP_DATA_DIR": _tmp.name,
        "APP_LOG_DIR": _tmp.name,
    }
)

from fastapi.testclient import TestClient  # noqa: E402

from pocketreader import main  # noqa: E402


class BrowserCaptureApiTests(unittest.TestCase):
    def setUp(self) -> None:
        main.db.init()

    def test_browser_capture_creates_queued_item(self) -> None:
        client = TestClient(main.app)

        response = client.post(
            "/api/browser-capture",
            headers={"X-PocketReader-Import-Token": "import-token"},
            json={
                "platform": "gemini",
                "url": "https://gemini.google.com/app/test",
                "title": "Capture Test",
                "reader_mode": "assistant",
                "voice": "zh-CN-XiaoxiaoNeural",
                "messages": [
                    {"role": "User", "text": "问题"},
                    {"role": "AI", "text": "**回答**"},
                ],
            },
        )

        self.assertEqual(response.status_code, 200)
        item = main.db.get_item(response.json()["item_id"])
        self.assertIsNotNone(item)
        assert item is not None
        self.assertEqual(item["title"], "Capture Test")
        self.assertEqual(item["source_type"], "browser:gemini")
        self.assertEqual(item["body"], "回答")
        self.assertEqual(item["status"], "queued")

    def test_browser_capture_rejects_bad_token(self) -> None:
        client = TestClient(main.app)

        response = client.post(
            "/api/browser-capture",
            headers={"X-PocketReader-Import-Token": "wrong"},
            json={"messages": [{"role": "AI", "text": "回答"}]},
        )

        self.assertEqual(response.status_code, 401)

    def test_browser_capture_rejects_non_object_payload(self) -> None:
        client = TestClient(main.app)

        response = client.post(
            "/api/browser-capture",
            headers={"X-PocketReader-Import-Token": "import-token"},
            json=[],
        )

        self.assertEqual(response.status_code, 400)

    def test_audio_head_supports_podcast_enclosure_checks(self) -> None:
        client = TestClient(main.app)
        item_id = main.db.create_item(
            title="Podcast Audio",
            body="audio body",
            source_type="text",
            voice="zh-CN-XiaoxiaoNeural",
            reader_mode="assistant",
        )
        audio_path = Path(os.environ["APP_DATA_DIR"]) / "audio" / str(item_id) / "audio.mp3"
        audio_path.parent.mkdir(parents=True, exist_ok=True)
        audio_path.write_bytes(b"fake mp3 bytes")
        main.db.mark_ready(
            item_id,
            audio_path.relative_to(Path(os.environ["APP_DATA_DIR"])).as_posix(),
            1.0,
        )

        response = client.head(f"/audio/{item_id}.mp3?token=feed-token")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"], "audio/mpeg")
        self.assertEqual(response.headers["content-length"], str(len(b"fake mp3 bytes")))
        self.assertEqual(response.headers["accept-ranges"], "bytes")


if __name__ == "__main__":
    unittest.main()
