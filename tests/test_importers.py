import json
import unittest

from pocketreader.importers import (
    extract_chatgpt_share,
    import_messages,
    render_messages,
    split_messages_into_turns,
)


def chatgpt_fixture_html() -> str:
    values = [None]

    def add(value):
        values.append(value)
        return len(values) - 1

    key_loader_data = add("loaderData")
    key_route = add("routes/share.$shareId.($action)")
    key_server_response = add("serverResponse")
    key_data = add("data")
    key_title = add("title")
    key_linear = add("linear_conversation")
    key_message = add("message")
    key_author = add("author")
    key_content = add("content")
    key_role = add("role")
    key_content_type = add("content_type")
    key_parts = add("parts")

    def message_node(role: str, text: str, content_type: str = "text"):
        role_ref = add(role)
        text_ref = add(text)
        parts_ref = add([text_ref])
        author_ref = add({f"_{key_role}": role_ref})
        content_ref = add(
            {f"_{key_content_type}": add(content_type), f"_{key_parts}": parts_ref}
        )
        message_ref = add({f"_{key_author}": author_ref, f"_{key_content}": content_ref})
        return add({f"_{key_message}": message_ref})

    title_ref = add("Synthetic ChatGPT Share")
    nodes_ref = add(
        [
            message_node("user", "用户问题"),
            message_node("assistant", "## 回答\n\n这是 **AI** 回复。"),
            message_node("tool", "redacted"),
        ]
    )
    data_ref = add({f"_{key_title}": title_ref, f"_{key_linear}": nodes_ref})
    server_response_ref = add({f"_{key_data}": data_ref})
    route_ref = add({f"_{key_server_response}": server_response_ref})
    loader_ref = add({f"_{key_route}": route_ref})
    values[0] = {f"_{key_loader_data}": loader_ref}

    payload = json.dumps(values, ensure_ascii=False)
    js_string = json.dumps(payload, ensure_ascii=False)
    return (
        "<html><title>fallback</title><script>"
        f"window.__reactRouterContext.streamController.enqueue({js_string});"
        "</script></html>"
    )


class ImporterTests(unittest.TestCase):
    def test_extract_chatgpt_share_decodes_react_router_payload(self) -> None:
        title, messages = extract_chatgpt_share(chatgpt_fixture_html())

        self.assertEqual(title, "Synthetic ChatGPT Share")
        self.assertEqual(
            messages,
            [
                {"role": "User", "text": "用户问题"},
                {"role": "AI", "text": "## 回答\n\n这是 **AI** 回复。"},
            ],
        )

    def test_render_messages_defaults_to_ai_only_and_cleans_markdown(self) -> None:
        _, messages = extract_chatgpt_share(chatgpt_fixture_html())

        self.assertEqual(render_messages(messages, "assistant"), "回答\n\n这是 AI 回复。")
        self.assertIn("User: 用户问题", render_messages(messages, "all"))

    def test_import_messages_normalizes_extension_payload(self) -> None:
        imported = import_messages(
            [
                {"role": "human", "text": "用户问题"},
                {"role": "model", "text": "## 回答\n\n这是 **Gemini** 回复。"},
                {"role": "system", "text": "ignore"},
            ],
            "assistant",
            "Gemini Capture",
        )

        self.assertEqual(imported.title, "Gemini Capture")
        self.assertEqual(imported.body, "回答\n\n这是 Gemini 回复。")

    def test_split_messages_into_turns_keeps_each_question_answer_pair(self) -> None:
        turns = split_messages_into_turns(
            [
                {"role": "User", "text": "问题一"},
                {"role": "AI", "text": "回答一"},
                {"role": "AI", "text": "补充一"},
                {"role": "User", "text": "问题二"},
                {"role": "AI", "text": "回答二"},
                {"role": "User", "text": "还没回答的问题"},
            ]
        )

        self.assertEqual(
            turns,
            [
                [
                    {"role": "User", "text": "问题一"},
                    {"role": "AI", "text": "回答一"},
                    {"role": "AI", "text": "补充一"},
                ],
                [
                    {"role": "User", "text": "问题二"},
                    {"role": "AI", "text": "回答二"},
                ],
            ],
        )


if __name__ == "__main__":
    unittest.main()
