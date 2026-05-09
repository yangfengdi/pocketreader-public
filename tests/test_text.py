import unittest

from pocketreader.text import markdown_to_speech_text, split_text_for_tts


class TextTests(unittest.TestCase):
    def test_markdown_cleanup_removes_links_and_code(self) -> None:
        text = markdown_to_speech_text("# Title\n\n[Link](https://example.com)\n\n`code`")
        self.assertIn("Title", text)
        self.assertIn("Link", text)
        self.assertNotIn("https://example.com", text)
        self.assertIn("code", text)

    def test_split_text_for_tts_respects_limit(self) -> None:
        chunks = split_text_for_tts("第一句。" * 1000, 200)
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(chunk) <= 220 for chunk in chunks))


if __name__ == "__main__":
    unittest.main()
