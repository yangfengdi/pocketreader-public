import unittest

from pocketreader.text import markdown_to_speech_text, split_text_for_tts


class TextTests(unittest.TestCase):
    def test_markdown_cleanup_removes_links_and_code(self) -> None:
        text = markdown_to_speech_text("# Title\n\n[Link](https://example.com)\n\n`code`")
        self.assertIn("Title", text)
        self.assertIn("Link", text)
        self.assertNotIn("https://example.com", text)
        self.assertIn("code", text)

    def test_markdown_cleanup_preserves_fenced_code_content_without_fences(self) -> None:
        text = markdown_to_speech_text(
            "说明\n\n"
            "```python\n"
            "print('hello')\n"
            "```\n\n"
            "结束"
        )

        self.assertIn("说明", text)
        self.assertIn("print('hello')", text)
        self.assertIn("结束", text)
        self.assertNotIn("```", text)
        self.assertNotIn("python\n", text)

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

    def test_markdown_cleanup_preserves_bold_heading_text(self) -> None:
        text = markdown_to_speech_text(
            "**艺术与品味**\n\n"
            "这是正文，标题文字必须保留。"
        )

        self.assertIn("艺术与品味", text)
        self.assertIn("这是正文", text)
        self.assertNotIn("**", text)

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
