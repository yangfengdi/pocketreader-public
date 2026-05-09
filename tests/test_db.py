import tempfile
import unittest
from pathlib import Path

from pocketreader.db import Database


class DatabaseTests(unittest.TestCase):
    def test_create_item_supports_default_and_error_status(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db = Database(Path(temp_dir) / "test.sqlite3")
            db.init()
            queued_id = db.create_item(
                title="Queued",
                body="body",
                source_type="text",
                voice="zh-CN-XiaoxiaoNeural",
                reader_mode="assistant",
            )
            error_id = db.create_item(
                title="Error",
                body="body",
                source_type="url",
                voice="zh-CN-XiaoxiaoNeural",
                reader_mode="assistant",
                status="error",
                error="failed",
            )
            self.assertEqual(db.get_item(queued_id)["status"], "queued")
            self.assertEqual(db.get_item(error_id)["status"], "error")
            self.assertEqual(db.get_item(error_id)["error"], "failed")


if __name__ == "__main__":
    unittest.main()

