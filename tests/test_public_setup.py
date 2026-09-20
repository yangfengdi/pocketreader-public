import importlib.util
import os
from pathlib import Path
import stat
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from pocketreader.config import get_settings
from scripts.init_env import create_env
from scripts import check_public_content as guard


class ConfigurationTests(unittest.TestCase):
    def test_generated_config_is_private_unique_and_does_not_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / ".env"
            create_env(output, "http://127.0.0.1:4780")
            original = output.read_text()
            values = dict(line.split("=", 1) for line in original.splitlines())
            credentials = [values[k] for k in ("APP_PASSWORD", "APP_SECRET_KEY", "FEED_TOKEN", "IMPORT_TOKEN")]
            self.assertEqual(len(set(credentials)), 4)
            self.assertTrue(all(len(value) >= 32 for value in credentials))
            self.assertEqual(stat.S_IMODE(output.stat().st_mode), 0o600)
            with self.assertRaises(FileExistsError):
                create_env(output, "https://reader.example.com", container=True)
            self.assertEqual(output.read_text(), original)
            with patch.dict(os.environ, {**values, "APP_DATA_DIR": tmp, "APP_LOG_DIR": tmp}, clear=True):
                settings = get_settings()
            self.assertEqual(settings.password, values["APP_PASSWORD"])

    def test_refuses_symlink_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "existing"
            target.write_text("keep")
            link = Path(tmp) / ".env"
            link.symlink_to(target)
            with self.assertRaises(FileExistsError):
                create_env(link, "https://reader.example.com")
            self.assertEqual(target.read_text(), "keep")

    def test_refuses_insecure_or_credential_bearing_remote_url(self):
        with tempfile.TemporaryDirectory() as tmp:
            for url in ("http://reader.example.com", "https://reader.example.com/path", "https://reader.example.com?token=example"):
                with self.subTest(url=url), self.assertRaises(ValueError):
                    create_env(Path(tmp) / ".env", url)

    def test_missing_or_placeholder_credentials_fail_without_disclosing_values(self):
        keys = ("APP_PASSWORD", "APP_SECRET_KEY", "FEED_TOKEN", "IMPORT_TOKEN")
        for missing in keys:
            env = {key: "test-config-value" for key in keys if key != missing}
            with self.subTest(key=missing), patch.dict(os.environ, env, clear=True):
                with self.assertRaisesRegex(RuntimeError, missing):
                    get_settings()
        with patch.dict(os.environ, {key: "CHANGE_ME" for key in keys}, clear=True):
            with self.assertRaises(RuntimeError) as result:
                get_settings()
            self.assertNotIn("CHANGE_ME", str(result.exception))


class PublicGuardTests(unittest.TestCase):
    def test_private_paths_even_when_forced_into_git(self):
        for name in (".env", ".env.production", "deploy/server.env", ".local/notes.md", "data/capture.json", "backup.bundle"):
            self.assertTrue(guard.inspect(name, b"", []), name)
        self.assertFalse(guard.private_path("deploy/pocketreader.env.example"))

    def test_ip_and_known_values_without_leaking_values(self):
        address = ".".join(map(str, [10, 23, 45, 67])).encode()
        self.assertEqual(guard.inspect("docs.md", address, []), ["non-example IPv4 address"])
        self.assertEqual(guard.inspect("docs.md", b"127.0.0.1 203.0.113.10", []), [])
        self.assertEqual(guard.inspect("x.md", b"example-secret", [b"example-secret"]), ["known private value"])
        self.assertEqual(guard.inspect("x.md", b"longwordreader", [b"longword"]), [])

    def test_deleted_secret_and_commit_messages_remain_in_history(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(guard, "ROOT", Path(tmp)):
            def git(*args):
                return subprocess.check_output(["git", *args], cwd=tmp, stderr=subprocess.DEVNULL)
            git("init")
            git("config", "user.name", "Test")
            git("config", "user.email", "test@example.com")
            secret = b"synthetic-history-value"
            (Path(tmp) / "note.txt").write_bytes(secret)
            git("add", "note.txt")
            git("commit", "-m", "synthetic-history-message")
            git("rm", "note.txt")
            git("commit", "-m", "remove current copy")
            findings = [finding for name, data in guard.blobs(["HEAD"])
                        for finding in guard.inspect(name, data, [secret, b"synthetic-history-message"])]
            self.assertGreaterEqual(findings.count("known private value"), 2)


if __name__ == "__main__":
    unittest.main()
