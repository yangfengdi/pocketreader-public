import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from pocketreader.tts import concat_mp3, probe_duration


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "ffmpeg required")
class TtsConcatTests(unittest.TestCase):
    def test_concat_uses_mp3_output_for_temp_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir_name:
            temp_dir = Path(temp_dir_name)
            chunk_paths = [temp_dir / "chunk-1.mp3", temp_dir / "chunk-2.mp3"]
            for chunk_path in chunk_paths:
                subprocess.run(
                    [
                        "ffmpeg",
                        "-y",
                        "-f",
                        "lavfi",
                        "-i",
                        "anullsrc=r=24000:cl=mono",
                        "-t",
                        "0.1",
                        "-c:a",
                        "libmp3lame",
                        "-q:a",
                        "9",
                        str(chunk_path),
                    ],
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )

            final_path = temp_dir / "audio.mp3"
            concat_mp3(chunk_paths, final_path, temp_dir)

            self.assertTrue(final_path.exists())
            self.assertGreater(probe_duration(final_path), 0)


if __name__ == "__main__":
    unittest.main()

