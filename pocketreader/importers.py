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
}


def import_plain_text(text: str, title: str | None = None) -> ImportedContent:
    body = normalize_text(text)
    return ImportedContent(title=title or title_from_markdown(text), body=body)


def import_markdown(markdown: str, title: str | None = None) -> ImportedContent:
    body = markdown_to_speech_text(markdown)
    return ImportedContent(title=title or title_from_markdown(markdown), body=body)


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
        response.raise_for_status()
        html = response.text

    title, messages = extract_conversation_messages(html)
    if messages:
        body = render_messages(messages, reader_mode)
        if body:
            return ImportedContent(title=title, body=body)

    page_title, body = html_to_text(html)
    if not body:
        raise ValueError("Could not extract readable text from this URL.")
    return ImportedContent(title=title or page_title, body=body)


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
        if reader_mode == "all":
            parts.append(f"{role}: {message['text']}")
        else:
            parts.append(message["text"])
    return normalize_text("\n\n".join(parts))

