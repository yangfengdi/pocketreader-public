from __future__ import annotations

import json
import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

from pocketreader.text import html_to_text, markdown_to_speech_text, normalize_text, title_from_markdown


@dataclass(frozen=True)
class ImportedContent:
    title: str | None
    body: str


ROLE_MAP = {
    "assistant": "AI",
    "model": "AI",
    "ai": "AI",
    "bot": "AI",
    "claude": "AI",
    "chatgpt": "AI",
    "user": "User",
    "human": "User",
    "you": "User",
}


def import_plain_text(text: str, title: str | None = None) -> ImportedContent:
    body = normalize_text(text)
    return ImportedContent(title=title or title_from_markdown(text), body=body)


def import_markdown(markdown: str, title: str | None = None) -> ImportedContent:
    body = markdown_to_speech_text(markdown)
    return ImportedContent(title=title or title_from_markdown(markdown), body=body)


def import_messages(
    messages: list[dict[str, Any]],
    reader_mode: str,
    title: str | None = None,
) -> ImportedContent:
    normalized_messages = normalize_messages(messages)
    body = render_messages(normalized_messages, reader_mode)
    return ImportedContent(title=title or title_from_markdown(body), body=body)


def normalize_messages(
    messages: list[dict[str, Any]],
    *,
    dedupe: bool = True,
) -> list[dict[str, str]]:
    normalized: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for message in messages:
        if not isinstance(message, dict):
            continue
        role = normalize_message_role(message.get("role"))
        text = normalize_text(str(message.get("text") or ""))
        if role is None or not text:
            continue
        key = (role, text)
        if dedupe and key in seen:
            continue
        seen.add(key)
        normalized.append({"role": role, "text": text})
    return normalized


def split_messages_into_turns(messages: list[dict[str, Any]]) -> list[list[dict[str, str]]]:
    normalized_messages = normalize_messages(messages, dedupe=False)
    turns: list[list[dict[str, str]]] = []
    current_turn: list[dict[str, str]] = []
    has_ai_message = False

    for message in normalized_messages:
        if message["role"] == "User":
            if has_ai_message:
                turns.append(current_turn)
                current_turn = []
                has_ai_message = False
            current_turn.append(message)
            continue

        current_turn.append(message)
        has_ai_message = True

    if current_turn and has_ai_message:
        turns.append(current_turn)
    return turns


def normalize_message_role(value: Any) -> str | None:
    if value is None:
        return None
    role = ROLE_MAP.get(str(value).strip().lower())
    return role if role in {"AI", "User"} else None


async def import_url(url: str, reader_mode: str) -> ImportedContent:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("Only http and https URLs are supported.")

    async with httpx.AsyncClient(
        timeout=httpx.Timeout(25.0, connect=10.0),
        follow_redirects=True,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
                "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        },
    ) as client:
        response = await client.get(url)
        html = response.text
        if response.status_code >= 400:
            raise_platform_error(parsed.netloc, html, response.status_code)

    platform_title, platform_messages = extract_platform_conversation(parsed.netloc, html)
    if platform_messages:
        body = render_messages(platform_messages, reader_mode)
        if body:
            return ImportedContent(title=platform_title, body=body)
    if is_known_ai_share_host(parsed.netloc):
        raise_no_conversation_error(parsed.netloc, html)

    title, messages = extract_conversation_messages(html)
    if messages:
        body = render_messages(messages, reader_mode)
        if body:
            return ImportedContent(title=title, body=body)

    page_title, body = html_to_text(html)
    if not body:
        raise ValueError("Could not extract readable text from this URL.")
    return ImportedContent(title=title or page_title, body=body)


def extract_platform_conversation(
    host: str, html: str
) -> tuple[str | None, list[dict[str, str]]]:
    host = host.lower()
    if host in {"chatgpt.com", "chat.openai.com"}:
        return extract_chatgpt_share(html)
    if host == "gemini.google.com":
        return extract_gemini_share(html)
    if host in {"claude.ai", "claude.com"}:
        return extract_claude_share(html)
    return None, []


def is_known_ai_share_host(host: str) -> bool:
    return host.lower() in {
        "chatgpt.com",
        "chat.openai.com",
        "gemini.google.com",
        "claude.ai",
        "claude.com",
    }


def raise_platform_error(host: str, html: str, status_code: int) -> None:
    host = host.lower()
    if host in {"claude.ai", "claude.com"} and _looks_like_cloudflare_challenge(html):
        raise ValueError("Claude 分享页被 Cloudflare challenge 拦截，服务器无法直接读取正文。")
    raise httpx.HTTPStatusError(
        f"HTTP {status_code} while fetching URL.",
        request=httpx.Request("GET", f"https://{host}/"),
        response=httpx.Response(status_code),
    )


def raise_no_conversation_error(host: str, html: str) -> None:
    host = host.lower()
    if host == "gemini.google.com":
        raise ValueError(
            "Gemini 分享页在未登录的服务器请求中没有返回对话正文。请先把对话内容复制为文本导入。"
        )
    if host in {"claude.ai", "claude.com"}:
        if "app-unavailable-in-region" in html or "App unavailable in region" in html:
            raise ValueError("Claude 分享页在当前服务器区域不可用，无法直接读取正文。")
        if _looks_like_cloudflare_challenge(html):
            raise ValueError("Claude 分享页被 Cloudflare challenge 拦截，服务器无法直接读取正文。")
        raise ValueError("Claude 分享页没有返回可解析的对话正文。")
    if host in {"chatgpt.com", "chat.openai.com"}:
        raise ValueError("ChatGPT 分享页没有返回可解析的对话正文。")
    raise ValueError("没有返回可解析的 AI 对话正文。")


def _looks_like_cloudflare_challenge(html: str) -> bool:
    return (
        "Just a moment..." in html
        or "cf-mitigated" in html
        or "challenges.cloudflare.com" in html
    )


def extract_chatgpt_share(html: str) -> tuple[str | None, list[dict[str, str]]]:
    title = _html_title(html)
    messages: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for payload in _react_router_stream_payloads(html):
        try:
            values = json.loads(payload)
        except json.JSONDecodeError:
            continue
        conversation = _chatgpt_conversation_data(values)
        if not conversation:
            continue
        title_value = _devalue_raw(values, _devalue_object_get(values, conversation, "title"))
        if isinstance(title_value, str):
            title = title_value
        for message in _chatgpt_messages_from_data(values, conversation):
            key = (message["role"], message["text"])
            if key in seen:
                continue
            seen.add(key)
            messages.append(message)
    return title, messages


def _react_router_stream_payloads(html: str) -> Iterable[str]:
    pattern = r"streamController\.enqueue\((\".*?\")\);"
    for match in re.finditer(pattern, html, flags=re.S):
        try:
            payload = json.loads(match.group(1))
        except json.JSONDecodeError:
            continue
        if "serverResponse" in payload:
            yield payload


def _chatgpt_conversation_data(values: list[Any]) -> dict[str, Any] | None:
    try:
        loader_data = _devalue_object_get(values, values[0], "loaderData")
        routes = _devalue_object_get(
            values,
            _devalue_raw(values, loader_data),
            "routes/share.$shareId.($action)",
        )
        server_response = _devalue_object_get(
            values, _devalue_raw(values, routes), "serverResponse"
        )
        data = _devalue_object_get(values, _devalue_raw(values, server_response), "data")
        raw_data = _devalue_raw(values, data)
    except (IndexError, TypeError):
        return None
    return raw_data if isinstance(raw_data, dict) else None


def _chatgpt_messages_from_data(
    values: list[Any], data: dict[str, Any]
) -> Iterable[dict[str, str]]:
    linear_ref = _devalue_object_get(values, data, "linear_conversation")
    linear = _devalue_raw(values, linear_ref)
    if not isinstance(linear, list):
        return
    for node_ref in linear:
        node = _devalue_raw(values, node_ref)
        if not isinstance(node, dict):
            continue
        message_ref = _devalue_object_get(values, node, "message")
        message = _devalue_raw(values, message_ref)
        if not isinstance(message, dict):
            continue
        parsed = _chatgpt_message(values, message)
        if parsed is not None:
            yield parsed


def _chatgpt_message(values: list[Any], message: dict[str, Any]) -> dict[str, str] | None:
    author = _devalue_raw(values, _devalue_object_get(values, message, "author"))
    content = _devalue_raw(values, _devalue_object_get(values, message, "content"))
    if not isinstance(author, dict) or not isinstance(content, dict):
        return None
    raw_role = _devalue_raw(values, _devalue_object_get(values, author, "role"))
    role = ROLE_MAP.get(str(raw_role).lower())
    if role is None:
        return None
    content_type = _devalue_raw(values, _devalue_object_get(values, content, "content_type"))
    if content_type not in {"text", "multimodal_text"}:
        return None
    parts = _devalue_raw(values, _devalue_object_get(values, content, "parts"))
    if not isinstance(parts, list):
        return None
    strings = [_devalue_raw(values, part) for part in parts]
    text = normalize_text("\n".join(part for part in strings if isinstance(part, str)))
    if not text:
        return None
    return {"role": role, "text": text}


def _devalue_object_get(values: list[Any], obj: Any, key: str) -> int | None:
    if not isinstance(obj, dict):
        return None
    for raw_key, raw_value in obj.items():
        if not (
            isinstance(raw_key, str)
            and raw_key.startswith("_")
            and raw_key[1:].isdigit()
        ):
            continue
        key_index = int(raw_key[1:])
        if key_index < len(values) and values[key_index] == key:
            return raw_value if isinstance(raw_value, int) else None
    return None


def _devalue_raw(values: list[Any], ref: Any) -> Any:
    if not isinstance(ref, int):
        return ref
    if ref < 0:
        return None
    if ref >= len(values):
        return None
    return values[ref]


def extract_gemini_share(html: str) -> tuple[str | None, list[dict[str, str]]]:
    title = _html_title(html)
    return title, []


def extract_claude_share(html: str) -> tuple[str | None, list[dict[str, str]]]:
    title, messages = extract_conversation_messages(html)
    if messages:
        return title, messages
    return _html_title(html), []


def _html_title(html: str) -> str | None:
    soup = BeautifulSoup(html, "html.parser")
    return soup.title.string.strip() if soup.title and soup.title.string else None


def extract_conversation_messages(html: str) -> tuple[str | None, list[dict[str, str]]]:
    soup = BeautifulSoup(html, "html.parser")
    title = soup.title.string.strip() if soup.title and soup.title.string else None
    messages: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()

    for script in soup.find_all("script"):
        script_type = (script.get("type") or "").lower()
        raw = script.string or script.get_text()
        if not raw:
            continue
        candidates: list[Any] = []
        if "json" in script_type or script.get("id") in {"__NEXT_DATA__", "vite-plugin-ssr_pageContext"}:
            try:
                candidates.append(json.loads(raw))
            except json.JSONDecodeError:
                pass
        candidates.extend(_json_objects_from_text(raw))
        for candidate in candidates:
            for message in _walk_for_messages(candidate):
                key = (message["role"], message["text"])
                if key not in seen:
                    seen.add(key)
                    messages.append(message)

    return title, messages


def _json_objects_from_text(text: str) -> Iterable[Any]:
    if len(text) > 2_000_000:
        return []
    objects: list[Any] = []
    for match in re.finditer(r"(\{[^{}]{20,}\})", text):
        snippet = match.group(1)
        if not any(key in snippet for key in ("role", "content", "message", "author")):
            continue
        try:
            objects.append(json.loads(snippet))
        except json.JSONDecodeError:
            continue
    return objects


def _walk_for_messages(value: Any) -> Iterable[dict[str, str]]:
    if isinstance(value, dict):
        message = _message_from_dict(value)
        if message is not None:
            yield message
        for child in value.values():
            yield from _walk_for_messages(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_for_messages(child)


def _message_from_dict(value: dict[str, Any]) -> dict[str, str] | None:
    role = _extract_role(value)
    text = _extract_text(value)
    if role is None or text is None:
        return None
    clean_text = normalize_text(text)
    if len(clean_text) < 2:
        return None
    return {"role": role, "text": clean_text}


def _extract_role(value: dict[str, Any]) -> str | None:
    role = value.get("role") or value.get("sender") or value.get("author_role")
    if role is None and isinstance(value.get("author"), dict):
        role = value["author"].get("role") or value["author"].get("name")
    if role is None and isinstance(value.get("participant"), dict):
        role = value["participant"].get("role")
    if role is None:
        return None
    return ROLE_MAP.get(str(role).lower(), str(role))


def _extract_text(value: dict[str, Any]) -> str | None:
    for key in ("text", "message", "markdown", "response"):
        if isinstance(value.get(key), str):
            return value[key]
    content = value.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, dict):
        parts = content.get("parts")
        if isinstance(parts, list):
            return "\n".join(str(part) for part in parts if isinstance(part, str))
        for key in ("text", "markdown", "value"):
            if isinstance(content.get(key), str):
                return content[key]
    if isinstance(content, list):
        strings: list[str] = []
        for part in content:
            if isinstance(part, str):
                strings.append(part)
            elif isinstance(part, dict):
                text = _extract_text(part)
                if text:
                    strings.append(text)
        if strings:
            return "\n".join(strings)
    return None


def render_messages(messages: list[dict[str, str]], reader_mode: str) -> str:
    parts: list[str] = []
    for message in messages:
        role = message["role"]
        if reader_mode == "assistant" and role != "AI":
            continue
        text = markdown_to_speech_text(message["text"])
        if not text:
            continue
        if reader_mode == "all":
            parts.append(f"{role}: {text}")
        else:
            parts.append(text)
    return normalize_text("\n\n".join(parts))
