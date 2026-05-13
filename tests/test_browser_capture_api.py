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

    def test_browser_capture_can_split_ai_conversation_into_turn_items(self) -> None:
        client = TestClient(main.app)

        response = client.post(
            "/api/browser-capture",
            headers={"X-PocketReader-Import-Token": "import-token"},
            json={
                "platform": "claude",
                "url": "https://claude.ai/chat/test",
                "title": "Split Test",
                "reader_mode": "assistant",
                "split_by_turn": True,
                "include_user_question": True,
                "voice": "zh-CN-XiaoxiaoNeural",
                "messages": [
                    {"role": "User", "text": "问题一"},
                    {"role": "AI", "text": "回答一"},
                    {"role": "User", "text": "问题二"},
                    {"role": "AI", "text": "回答二"},
                ],
            },
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["count"], 2)
        self.assertEqual(len(data["item_ids"]), 2)

        first = main.db.get_item(data["item_ids"][0])
        second = main.db.get_item(data["item_ids"][1])
        self.assertIsNotNone(first)
        self.assertIsNotNone(second)
        assert first is not None
        assert second is not None
        self.assertEqual(first["title"], "[1/2] Split Test")
        self.assertEqual(second["title"], "[2/2] Split Test")
        self.assertEqual(first["body"], "User: 问题一\n\nAI: 回答一")
        self.assertEqual(second["body"], "User: 问题二\n\nAI: 回答二")
        self.assertEqual(first["source_type"], "browser:claude:turn")
        self.assertEqual(second["reader_mode"], "all")

    def test_browser_capture_split_can_exclude_user_questions(self) -> None:
        client = TestClient(main.app)

        response = client.post(
            "/api/browser-capture",
            headers={"X-PocketReader-Import-Token": "import-token"},
            json={
                "platform": "chatgpt",
                "title": "Answer Only",
                "split_by_turn": True,
                "include_user_question": False,
                "messages": [
                    {"role": "User", "text": "问题"},
                    {"role": "AI", "text": "回答"},
                ],
            },
        )

        self.assertEqual(response.status_code, 200)
        item = main.db.get_item(response.json()["item_ids"][0])
        self.assertIsNotNone(item)
        assert item is not None
        self.assertEqual(item["title"], "[1/1] Answer Only")
        self.assertEqual(item["body"], "回答")
        self.assertEqual(item["reader_mode"], "assistant")

    def test_browser_capture_creates_separate_items_for_generated_files(self) -> None:
        client = TestClient(main.app)

        response = client.post(
            "/api/browser-capture",
            headers={"X-PocketReader-Import-Token": "import-token"},
            json={
                "platform": "chatgpt",
                "url": "https://chatgpt.com/c/test",
                "title": "Conversation With Files",
                "reader_mode": "all",
                "messages": [
                    {"role": "User", "text": "写一个文件"},
                    {"role": "AI", "text": "文件已生成"},
                ],
                "files": [
                    {"filename": "outline.md", "body": "# 大纲\n\n第一节"},
                    {"filename": "notes.txt", "body": "补充说明"},
                ],
            },
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["count"], 3)
        conversation = main.db.get_item(data["item_ids"][0])
        first_file = main.db.get_item(data["item_ids"][1])
        second_file = main.db.get_item(data["item_ids"][2])
        self.assertIsNotNone(conversation)
        self.assertIsNotNone(first_file)
        self.assertIsNotNone(second_file)
        assert conversation is not None
        assert first_file is not None
        assert second_file is not None
        self.assertEqual(conversation["source_type"], "browser:chatgpt")
        self.assertEqual(conversation["body"], "User: 写一个文件\n\nAI: 文件已生成")
        self.assertEqual(first_file["title"], "[文件 1/2] outline.md")
        self.assertEqual(first_file["body"], "大纲\n\n第一节")
        self.assertEqual(first_file["source_type"], "browser:chatgpt:file")
        self.assertEqual(first_file["source_filename"], "outline.md")
        self.assertEqual(second_file["title"], "[文件 2/2] notes.txt")

    def test_browser_capture_accepts_file_only_payload(self) -> None:
        client = TestClient(main.app)

        response = client.post(
            "/api/browser-capture",
            headers={"X-PocketReader-Import-Token": "import-token"},
            json={
                "platform": "claude",
                "files": [
                    {"filename": "artifact.txt", "body": "独立文件内容"},
                ],
            },
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["count"], 1)
        item = main.db.get_item(data["item_id"])
        self.assertIsNotNone(item)
        assert item is not None
        self.assertEqual(item["title"], "[文件] artifact.txt")
        self.assertEqual(item["body"], "独立文件内容")
        self.assertEqual(item["source_type"], "browser:claude:file")

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

    def test_browser_snapshot_parse_and_create_split_claude_turns(self) -> None:
        client = TestClient(main.app)

        parse_response = client.post(
            "/api/browser-snapshot",
            headers={"X-PocketReader-Import-Token": "import-token"},
            json={
                "platform": "claude",
                "url": "https://claude.ai/chat/test",
                "title": "AI时代的儿童教育长期规划",
                "snapshot": {
                    "blocks": [
                        claude_block(0, "User", "问题一"),
                        claude_block(1, "AI", "回答一"),
                        claude_block(2, "User", "问题二"),
                        claude_block(3, "AI", "回答二"),
                        claude_block(4, "User", "问题三"),
                        claude_block(5, "AI", "回答三"),
                    ]
                },
            },
        )

        self.assertEqual(parse_response.status_code, 200)
        parsed = parse_response.json()
        self.assertEqual(parsed["summary"]["message_count"], 6)
        self.assertEqual(parsed["summary"]["turn_count"], 3)
        self.assertEqual(parsed["summary"]["file_count"], 0)
        self.assertEqual(parsed["warnings"], [])

        create_response = client.post(
            f"/api/browser-snapshot/{parsed['capture_id']}/create",
            headers={"X-PocketReader-Import-Token": "import-token"},
            json={
                "title": "AI时代的儿童教育长期规划",
                "reader_mode": "all",
                "split_by_turn": True,
                "include_user_question": True,
                "voice": "zh-CN-XiaoxiaoNeural",
            },
        )

        self.assertEqual(create_response.status_code, 200)
        data = create_response.json()
        self.assertEqual(data["count"], 3)
        first = main.db.get_item(data["item_ids"][0])
        third = main.db.get_item(data["item_ids"][2])
        self.assertIsNotNone(first)
        self.assertIsNotNone(third)
        assert first is not None
        assert third is not None
        self.assertEqual(first["title"], "[1/3] AI时代的儿童教育长期规划")
        self.assertEqual(first["body"], "User: 问题一\n\nAI: 回答一")
        self.assertEqual(third["title"], "[3/3] AI时代的儿童教育长期规划")
        self.assertEqual(third["body"], "User: 问题三\n\nAI: 回答三")

    def test_browser_snapshot_does_not_treat_plain_claude_reply_as_file(self) -> None:
        client = TestClient(main.app)

        response = client.post(
            "/api/browser-snapshot",
            headers={"X-PocketReader-Import-Token": "import-token"},
            json={
                "platform": "claude",
                "title": "普通 Claude 回复",
                "snapshot": {
                    "blocks": [
                        claude_block(0, "User", "请帮我规划一个课题"),
                        claude_block(
                            1,
                            "AI",
                            "这是一个非常有价值的课题。\n\n一、定位判断\n\n这里是正文，不是文件。",
                        ),
                        {
                            "index": 2,
                            "tag": "div",
                            "kind_hint": "message",
                            "attrs": {"class": "right-side-panel"},
                            "text": "这是右侧展示的一大段普通文本，但没有 artifact 或文件标记。",
                        },
                    ]
                },
            },
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["summary"]["message_count"], 2)
        self.assertEqual(data["summary"]["turn_count"], 1)
        self.assertEqual(data["summary"]["file_count"], 0)

    def test_browser_snapshot_extracts_open_claude_artifact_document(self) -> None:
        client = TestClient(main.app)
        file_body = (
            "AI 时代的家庭教育：7 件值得做的事，6 件不要做的事\n\n"
            "我有个上高中的孩子。最近一两年我反复在想一个问题：AI 在以肉眼可见的速度变强，"
            "他未来 5 到 10 年要进入的，是一个被 AI 重新塑造过的世界。\n\n"
            "在 AI 时代，孩子真正稀缺的能力，不是会用 AI，而是在 AI 给的选项之外，"
            "自己造出新选项的能力。\n\n"
            "家庭教育所有的具体动作，都应该围绕这个核心展开。下面是我给自己定的清单："
            "让他做结构需要自己造的事，让他承担真实代价，保护无聊和独处，让他在一个领域深下去。"
            "不要替他规避所有困难，不要把答案当成教育，不要用焦虑管理孩子。"
        ) * 2

        parse_response = client.post(
            "/api/browser-snapshot",
            headers={"X-PocketReader-Import-Token": "import-token"},
            json={
                "platform": "claude",
                "title": "Claude Artifact",
                "snapshot": {
                    "blocks": [
                        claude_block(0, "User", "请整理成一篇文章"),
                        claude_block(1, "AI", "我把它做成了一份 Markdown 文件，方便你直接复制使用。"),
                        {
                            "index": 2,
                            "tag": "div",
                            "kind_hint": "artifact",
                            "attrs": {"class": "group/artifact-block"},
                            "text": "Ai时代的家庭教育Document · MD",
                        },
                        {
                            "index": 3,
                            "tag": "div",
                            "kind_hint": "artifact",
                            "attrs": {"class": "artifact-block-cell"},
                            "text": "Ai时代的家庭教育Document · MD",
                        },
                        {
                            "index": 4,
                            "tag": "div",
                            "role_hint": "AI",
                            "kind_hint": "message",
                            "attrs": {"class": "mx-auto w-full max-w-3xl leading-[1.65rem]"},
                            "text": file_body,
                        },
                        {
                            "index": 5,
                            "tag": "div",
                            "role_hint": "AI",
                            "kind_hint": "message",
                            "attrs": {"class": "standard-markdown grid-cols-1 font-claude-response"},
                            "text": file_body,
                        },
                        {
                            "index": 6,
                            "tag": "h1",
                            "role_hint": "AI",
                            "kind_hint": "message",
                            "attrs": {"class": "text-text-100 font-bold"},
                            "text": "AI 时代的家庭教育：7 件值得做的事，6 件不要做的事",
                        },
                    ]
                },
            },
        )

        self.assertEqual(parse_response.status_code, 200)
        parsed = parse_response.json()
        self.assertEqual(parsed["summary"]["message_count"], 2)
        self.assertEqual(parsed["summary"]["turn_count"], 1)
        self.assertEqual(parsed["summary"]["file_count"], 1)
        self.assertEqual(parsed["files"][0]["filename"], "Ai时代的家庭教育.md")

        create_response = client.post(
            f"/api/browser-snapshot/{parsed['capture_id']}/create",
            headers={"X-PocketReader-Import-Token": "import-token"},
            json={
                "reader_mode": "all",
                "split_by_turn": True,
                "include_user_question": True,
            },
        )

        self.assertEqual(create_response.status_code, 200)
        data = create_response.json()
        self.assertEqual(data["count"], 2)
        turn = main.db.get_item(data["item_ids"][0])
        file_item = main.db.get_item(data["item_ids"][1])
        self.assertIsNotNone(turn)
        self.assertIsNotNone(file_item)
        assert turn is not None
        assert file_item is not None
        self.assertEqual(turn["body"], "User: 请整理成一篇文章\n\nAI: 我把它做成了一份 Markdown 文件，方便你直接复制使用。")
        self.assertEqual(file_item["title"], "[文件] Ai时代的家庭教育")
        self.assertIn("AI 时代的家庭教育", file_item["body"])
        self.assertEqual(file_item["source_type"], "browser:claude:file")

    def test_browser_snapshot_coalesces_claude_fallback_answer_blocks(self) -> None:
        client = TestClient(main.app)

        parse_response = client.post(
            "/api/browser-snapshot",
            headers={"X-PocketReader-Import-Token": "import-token"},
            json={
                "platform": "claude",
                "title": "Fallback Blocks",
                "snapshot": {
                    "blocks": [
                        claude_block(0, "User", "问题一"),
                        {
                            "index": 1,
                            "tag": "p",
                            "role_hint": "AI",
                            "kind_hint": "message",
                            "attrs": {},
                            "text": "回答一第一段",
                        },
                        {
                            "index": 2,
                            "tag": "p",
                            "role_hint": "AI",
                            "kind_hint": "message",
                            "attrs": {},
                            "text": "回答一第二段",
                        },
                        claude_block(3, "User", "问题二"),
                        {
                            "index": 4,
                            "tag": "p",
                            "role_hint": "AI",
                            "kind_hint": "message",
                            "attrs": {},
                            "text": "回答二",
                        },
                    ]
                },
            },
        )

        self.assertEqual(parse_response.status_code, 200)
        parsed = parse_response.json()
        self.assertEqual(parsed["summary"]["message_count"], 4)
        self.assertEqual(parsed["summary"]["turn_count"], 2)

        create_response = client.post(
            f"/api/browser-snapshot/{parsed['capture_id']}/create",
            headers={"X-PocketReader-Import-Token": "import-token"},
            json={
                "reader_mode": "all",
                "split_by_turn": True,
                "include_user_question": True,
            },
        )

        self.assertEqual(create_response.status_code, 200)
        first = main.db.get_item(create_response.json()["item_ids"][0])
        self.assertIsNotNone(first)
        assert first is not None
        self.assertEqual(first["body"], "User: 问题一\n\nAI: 回答一第一段\n\n回答一第二段")

    def test_browser_snapshot_ignores_claude_screen_reader_labels(self) -> None:
        client = TestClient(main.app)

        parse_response = client.post(
            "/api/browser-snapshot",
            headers={"X-PocketReader-Import-Token": "import-token"},
            json={
                "platform": "claude",
                "title": "Screen Reader Labels",
                "snapshot": {
                    "blocks": [
                        {
                            "index": 0,
                            "tag": "h2",
                            "role_hint": "AI",
                            "kind_hint": "message",
                            "attrs": {"class": "sr-only"},
                            "text": "You said: 问题一",
                        },
                        claude_block(1, "User", "问题一"),
                        {
                            "index": 2,
                            "tag": "h2",
                            "role_hint": "AI",
                            "kind_hint": "message",
                            "attrs": {"class": "sr-only"},
                            "text": "Claude responded: 回答一",
                        },
                        {
                            "index": 3,
                            "tag": "p",
                            "role_hint": "AI",
                            "kind_hint": "message",
                            "attrs": {},
                            "text": "回答一",
                        },
                        claude_block(4, "User", "问题二"),
                        {
                            "index": 5,
                            "tag": "p",
                            "role_hint": "AI",
                            "kind_hint": "message",
                            "attrs": {},
                            "text": "回答二",
                        },
                        claude_block(6, "User", "问题三"),
                        {
                            "index": 7,
                            "tag": "p",
                            "role_hint": "AI",
                            "kind_hint": "message",
                            "attrs": {},
                            "text": "回答三",
                        },
                    ]
                },
            },
        )

        self.assertEqual(parse_response.status_code, 200)
        parsed = parse_response.json()
        self.assertEqual(parsed["summary"]["message_count"], 6)
        self.assertEqual(parsed["summary"]["turn_count"], 3)

    def test_browser_snapshot_create_rejects_split_when_questions_are_missing(self) -> None:
        client = TestClient(main.app)

        parse_response = client.post(
            "/api/browser-snapshot",
            headers={"X-PocketReader-Import-Token": "import-token"},
            json={
                "platform": "claude",
                "title": "只有回复",
                "snapshot": {
                    "blocks": [
                        claude_block(0, "AI", "回答一"),
                        claude_block(1, "AI", "回答二"),
                    ]
                },
            },
        )

        self.assertEqual(parse_response.status_code, 200)
        self.assertIn("未完整识别问答双方", parse_response.json()["warnings"])

        create_response = client.post(
            f"/api/browser-snapshot/{parse_response.json()['capture_id']}/create",
            headers={"X-PocketReader-Import-Token": "import-token"},
            json={
                "reader_mode": "all",
                "split_by_turn": True,
                "include_user_question": True,
            },
        )

        self.assertEqual(create_response.status_code, 400)

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

    def test_podcast_feed_includes_pocket_cast_compatibility_metadata(self) -> None:
        item_id = main.db.create_item(
            title="Feed Item",
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
            65.0,
        )

        feed = main.build_podcast_feed()

        self.assertIn('atom:link href="http://127.0.0.1:4780/feed/feed-token.xml"', feed)
        self.assertIn("<lastBuildDate>", feed)
        self.assertIn('guid isPermaLink="false"', feed)
        self.assertIn("<itunes:duration>1:05</itunes:duration>", feed)
        self.assertIn("<itunes:explicit>false</itunes:explicit>", feed)


def claude_block(index: int, role: str, text: str) -> dict[str, object]:
    test_id = "user-message" if role == "User" else "assistant-message"
    class_name = "font-user-message" if role == "User" else "font-claude-message"
    return {
        "index": index,
        "tag": "div",
        "role_hint": role,
        "kind_hint": "message",
        "attrs": {"data-testid": test_id, "class": class_name},
        "text": text,
    }


if __name__ == "__main__":
    unittest.main()
