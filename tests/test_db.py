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
                title="[AI答 001] Queued",
                body="body",
                source_type="text",
                voice="zh-CN-XiaoxiaoNeural",
                reader_mode="assistant",
                turn_index=1,
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
            self.assertEqual(db.get_item(queued_id)["turn_index"], 1)
            self.assertEqual(db.get_item(error_id)["status"], "error")
            self.assertEqual(db.get_item(error_id)["error"], "failed")

    def test_requeue_interrupted_items_resets_processing_jobs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db = Database(Path(temp_dir) / "test.sqlite3")
            db.init()
            item_id = db.create_item(
                title="Processing",
                body="body",
                source_type="text",
                voice="zh-CN-XiaoxiaoNeural",
                reader_mode="assistant",
            )
            claimed = db.claim_next_item()
            self.assertEqual(claimed["id"], item_id)
            self.assertEqual(claimed["status"], "processing")

            count = db.requeue_interrupted_items()

            self.assertEqual(count, 1)
            self.assertEqual(db.get_item(item_id)["status"], "queued")
            with db.connect() as conn:
                jobs = list(
                    conn.execute(
                        "SELECT status, completed_at FROM jobs WHERE item_id = ? ORDER BY id",
                        (item_id,),
                    )
                )
            self.assertEqual([job["status"] for job in jobs], ["interrupted", "queued"])
            self.assertIsNotNone(jobs[0]["completed_at"])
            self.assertIsNone(jobs[1]["completed_at"])


if __name__ == "__main__":
    unittest.main()
