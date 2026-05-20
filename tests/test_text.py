import unittest

from pocketreader.text import markdown_to_speech_text, split_text_for_tts


class TextTests(unittest.TestCase):
    def test_markdown_cleanup_removes_links_and_code(self) -> None:
        text = markdown_to_speech_text("# Title\n\n[Link](https://example.com)\n\n`code`")
        self.assertIn("Title", text)
        self.assertIn("Link", text)
        self.assertNotIn("https://example.com", text)
        self.assertIn("code", text)

    def test_markdown_cleanup_preserves_heading_text_without_markers(self) -> None:
        text = markdown_to_speech_text(
            "# 一级标题 #\n\n"
            "二级标题\n"
            "------\n\n"
            "## 三级标题 ###\n\n"
            "正文"
        )

        self.assertIn("一级标题", text)
        self.assertIn("二级标题", text)
        self.assertIn("三级标题", text)
        self.assertIn("正文", text)
        self.assertNotIn("#", text)
        self.assertNotIn("---", text)

    def test_markdown_cleanup_preserves_table_content_without_table_syntax(self) -> None:
        text = markdown_to_speech_text(
            "| 标题 | 内容 |\n"
            "| --- | --- |\n"
            "| 第一项 | 说明文字 |\n"
        )

        self.assertIn("标题，内容", text)
        self.assertIn("第一项，说明文字", text)
        self.assertNotIn("|", text)
        self.assertNotIn("---", text)

    def test_split_text_for_tts_respects_limit(self) -> None:
        chunks = split_text_for_tts("第一句。" * 1000, 200)
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(chunk) <= 220 for chunk in chunks))


if __name__ == "__main__":
    unittest.main()
