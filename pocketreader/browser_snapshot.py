from __future__ import annotations

import re
from typing import Any

from pocketreader.importers import normalize_message_role, normalize_messages, split_messages_into_turns
from pocketreader.text import normalize_text


PARSER_VERSION = "2026-05-15.1"
MAX_TEXT_CHARS = 300_000
TEXT_FILE_EXTENSIONS = {
    "txt",
    "md",
    "markdown",
    "csv",
    "tsv",
    "json",
    "jsonl",
    "yaml",
    "yml",
    "xml",
    "html",
    "htm",
    "rtf",
    "log",
    "py",
    "js",
    "ts",
    "tsx",
    "jsx",
    "css",
    "scss",
    "sql",
    "sh",
    "bash",
    "zsh",
    "toml",
    "ini",
    "conf",
    "tex",
}
BINARY_FILE_EXTENSIONS = {"docx"}
SUPPORTED_FILE_EXTENSIONS = TEXT_FILE_EXTENSIONS | BINARY_FILE_EXTENSIONS


def parse_browser_snapshot(payload: dict[str, Any]) -> dict[str, Any]:
    snapshot = payload.get("snapshot") if isinstance(payload.get("snapshot"), dict) else payload
    page = snapshot.get("page") if isinstance(snapshot.get("page"), dict) else {}
    platform = normalize_platform(payload.get("platform") or snapshot.get("platform") or page.get("platform"))
    source_url = clean_string(payload.get("url") or snapshot.get("url") or page.get("url"))
    title = clean_title(
        payload.get("title")
        or snapshot.get("title")
        or page.get("title")
        or payload.get("page_title")
        or ""
    )

    blocks = snapshot_blocks(snapshot)
    inferred_files, file_block_indexes = infer_file_blocks(platform, blocks)
    messages = parse_messages(platform, blocks, excluded_indexes=file_block_indexes)
    files = parse_files(snapshot, blocks, inferred_files=inferred_files)
    turns = split_messages_into_turns(messages)
    warnings: list[str] = []

    if messages and not has_both_roles(messages):
        warnings.append("未完整识别问答双方")
    if not messages and not files:
        warnings.append("没有识别到可导入的对话文本或文本文件")

    return {
        "parser_version": PARSER_VERSION,
        "platform": platform,
        "source_url": source_url,
        "title": title or title_from_messages(messages) or f"{platform} conversation",
        "messages": messages,
        "files": files,
        "turn_count": len(turns),
        "message_count": len(messages),
        "file_count": len(files),
        "has_user_messages": any(message["role"] == "User" for message in messages),
        "has_ai_messages": any(message["role"] == "AI" for message in messages),
        "warnings": warnings,
    }


def snapshot_blocks(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    raw_blocks = snapshot.get("blocks")
    if not isinstance(raw_blocks, list):
        return []
    blocks: list[dict[str, Any]] = []
    for index, raw_block in enumerate(raw_blocks):
        if not isinstance(raw_block, dict):
            continue
        text = normalize_text(str(raw_block.get("text") or ""))[:MAX_TEXT_CHARS]
        if len(text) < 2:
            continue
        attrs = raw_block.get("attrs")
        attrs = attrs if isinstance(attrs, dict) else {}
        block = {
            "index": int_value(raw_block.get("index"), index),
            "tag": clean_string(raw_block.get("tag")).lower(),
            "text": text,
            "attrs": {str(key): clean_string(value) for key, value in attrs.items()},
            "role_hint": clean_string(raw_block.get("role_hint")),
            "kind_hint": clean_string(raw_block.get("kind_hint")).lower(),
            "path": clean_string(raw_block.get("path")),
        }
        blocks.append(block)
    return sorted(blocks, key=lambda block: int_value(block.get("index"), 0))


def parse_messages(
    platform: str,
    blocks: list[dict[str, Any]],
    *,
    excluded_indexes: set[int] | None = None,
) -> list[dict[str, str]]:
    excluded_indexes = excluded_indexes or set()
    candidates: list[dict[str, Any]] = []
    for block in blocks:
        if int_value(block.get("index"), 0) in excluded_indexes:
            continue
        if explicit_file_block(block) or hidden_accessibility_block(block):
            continue
        role = role_from_block(platform, block)
        if role is None:
            continue
        text = clean_message_text(block.get("text"))
        if len(text) < 2 or mostly_ui_text(text):
            continue
        candidates.append({"role": role, "text": text, "index": int_value(block.get("index"), 0)})

    candidates = coalesce_consecutive_messages(dedupe_message_candidates(candidates))
    return normalize_messages(candidates, dedupe=False)


def parse_files(
    snapshot: dict[str, Any],
    blocks: list[dict[str, Any]],
    *,
    inferred_files: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    files: list[dict[str, Any]] = []
    for raw_file in snapshot_files(snapshot):
        file_payload = normalize_file_payload(raw_file)
        if file_payload:
            add_file(files, file_payload)

    for block in blocks:
        file_payload = file_payload_from_block(block)
        if file_payload:
            add_file(files, file_payload)
    for file_payload in inferred_files or []:
        add_file(files, file_payload)
    return files


def infer_file_blocks(platform: str, blocks: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], set[int]]:
    if platform != "claude":
        return [], set()
    return infer_claude_open_document_files(blocks)


def infer_claude_open_document_files(blocks: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], set[int]]:
    files: list[dict[str, Any]] = []
    excluded_indexes: set[int] = set()
    ordered_blocks = sorted(blocks, key=lambda block: int_value(block.get("index"), 0))

    for anchor in ordered_blocks:
        if clean_string(anchor.get("kind_hint")).lower() != "artifact":
            continue
        title = clean_claude_artifact_title(anchor.get("text"))
        if not title:
            continue
        candidate = claude_document_body_after_anchor(anchor, ordered_blocks)
        if candidate is None:
            continue

        body = normalize_text(str(candidate.get("text") or ""))[:MAX_TEXT_CHARS]
        if len(body) < 400:
            continue
        filename = f"{safe_filename(title)}.md"
        add_file(
            files,
            {
                "title": title,
                "filename": filename,
                "body": body,
            },
        )
        excluded_indexes.update(
            claude_document_block_indexes(
                anchor_index=int_value(anchor.get("index"), 0),
                body=body,
                blocks=ordered_blocks,
            )
        )
    return files, excluded_indexes


def claude_document_body_after_anchor(
    anchor: dict[str, Any],
    blocks: list[dict[str, Any]],
) -> dict[str, Any] | None:
    anchor_index = int_value(anchor.get("index"), 0)
    candidates: list[dict[str, Any]] = []
    for block in blocks:
        block_index = int_value(block.get("index"), 0)
        if block_index <= anchor_index:
            continue
        if block_index - anchor_index > 60:
            break
        if normalize_message_role(block.get("role_hint")) == "User":
            break
        if clean_string(block.get("kind_hint")).lower() == "artifact":
            continue
        if hidden_accessibility_block(block):
            continue
        if role_from_block("claude", block) != "AI":
            continue
        text = normalize_text(str(block.get("text") or ""))
        if len(text) < 400:
            continue
        if not looks_like_claude_document_body(block):
            continue
        candidates.append(block)
    if not candidates:
        return None
    return max(candidates, key=lambda block: len(str(block.get("text") or "")))


def looks_like_claude_document_body(block: dict[str, Any]) -> bool:
    attrs = block.get("attrs") if isinstance(block.get("attrs"), dict) else {}
    class_name = clean_string(attrs.get("class")).lower()
    tag = clean_string(block.get("tag")).lower()
    if tag in {"article", "main", "textarea", "pre", "code"}:
        return True
    return any(
        marker in class_name
        for marker in (
            "standard-markdown",
            "prosemirror",
            "cm-content",
            "max-w-3xl",
            "artifact",
            "document",
            "preview",
            "editor",
        )
    )


def claude_document_block_indexes(
    *,
    anchor_index: int,
    body: str,
    blocks: list[dict[str, Any]],
) -> set[int]:
    body_text = comparable_text(body)
    excluded: set[int] = set()
    for block in blocks:
        block_index = int_value(block.get("index"), 0)
        if block_index <= anchor_index:
            continue
        if block_index - anchor_index > 90:
            break
        if normalize_message_role(block.get("role_hint")) == "User":
            break
        if role_from_block("claude", block) != "AI":
            continue
        text = comparable_text(str(block.get("text") or ""))
        if len(text) >= 20 and text in body_text:
            excluded.add(block_index)
    return excluded


def clean_claude_artifact_title(value: object) -> str:
    title = clean_string(value)
    for marker in ("Document", "Markdown", "Code", "Text", "文件", "文档", "·", "•"):
        title = title.replace(marker, " ")
    title = re.sub(r"\b(md|txt|csv|json|yaml|yml|xml|html|py|js|ts|tsx|jsx|css)\b", " ", title, flags=re.I)
    title = re.sub(r"\s+", " ", title).strip()
    if not title or mostly_ui_text(title):
        return ""
    return title[:120]


def snapshot_files(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    raw_files = snapshot.get("files")
    if not isinstance(raw_files, list):
        return []
    return [file for file in raw_files if isinstance(file, dict)]


def normalize_file_payload(raw_file: dict[str, Any]) -> dict[str, Any] | None:
    title = clean_string(raw_file.get("title") or raw_file.get("filename") or "AI 生成文件")
    filename = clean_string(raw_file.get("filename") or title)
    body = normalize_text(str(raw_file.get("body") or raw_file.get("text") or ""))[:MAX_TEXT_CHARS]
    data_base64 = clean_string(raw_file.get("data_base64"))
    url = clean_string(raw_file.get("url"))

    if not (body or data_base64):
        return None
    if filename and not supported_filename(filename) and not explicit_file_dict(raw_file):
        return None

    payload: dict[str, Any] = {"title": title or filename or "AI 生成文件"}
    if filename:
        payload["filename"] = filename
    if body:
        payload["body"] = body
    if data_base64:
        payload["data_base64"] = data_base64
    if url:
        payload["url"] = url
    content_type = clean_string(raw_file.get("content_type"))
    if content_type:
        payload["content_type"] = content_type
    return payload


def file_payload_from_block(block: dict[str, Any]) -> dict[str, Any] | None:
    if not explicit_file_block(block):
        return None
    text = normalize_text(str(block.get("text") or ""))[:MAX_TEXT_CHARS]
    if len(text) < 40:
        return None
    attrs = block_attrs_text(block)
    filename = match_filename(attrs) or match_filename(text)
    if filename and not supported_filename(filename):
        return None
    if not filename and block.get("kind_hint") != "artifact":
        return None
    title = clean_file_title(
        attribute_value(block, "title")
        or attribute_value(block, "aria-label")
        or filename
        or first_text_line(text)
        or "AI 生成文件"
    )
    return {
        "title": title or filename or "AI 生成文件",
        "filename": filename or f"{safe_filename(title or 'ai-generated-file')}.md",
        "body": text,
    }


def add_file(files: list[dict[str, Any]], candidate: dict[str, Any]) -> None:
    candidate_body = normalize_text(str(candidate.get("body") or ""))
    candidate_filename = clean_string(candidate.get("filename") or candidate.get("title"))
    for index, existing in enumerate(files):
        existing_body = normalize_text(str(existing.get("body") or ""))
        existing_filename = clean_string(existing.get("filename") or existing.get("title"))
        if candidate_filename and candidate_filename == existing_filename:
            if len(candidate_body) > len(existing_body):
                files[index] = candidate
            return
        if candidate_body and existing_body and text_contains_either(existing_body, candidate_body):
            if len(candidate_body) > len(existing_body):
                files[index] = candidate
            return
    files.append(candidate)


def role_from_block(platform: str, block: dict[str, Any]) -> str | None:
    if platform == "claude" and claude_collapsed_user_preview_block(block):
        return "User"

    role = normalize_message_role(block.get("role_hint"))
    if role:
        return role

    attrs = block.get("attrs") if isinstance(block.get("attrs"), dict) else {}
    author_role = clean_string(attrs.get("data-message-author-role")).lower()
    if author_role:
        role = normalize_message_role(author_role)
        if role:
            return role

    haystack = " ".join(
        [
            platform,
            clean_string(block.get("tag")),
            clean_string(attrs.get("data-testid")),
            clean_string(attrs.get("data-test-id")),
            clean_string(attrs.get("class")),
            clean_string(attrs.get("aria-label")),
            clean_string(attrs.get("role")),
            clean_string(block.get("path")),
        ]
    ).lower()
    if any(
        marker in haystack
        for marker in (
            "assistant-message",
            "model-response",
            "model_response",
            "font-claude-message",
            "message-content",
            "response-container",
        )
    ):
        return "AI"
    if any(
        marker in haystack
        for marker in (
            "user-message",
            "user_query",
            "user-query",
            "font-user-message",
            "query-text",
        )
    ):
        return "User"
    return None


def claude_collapsed_user_preview_block(block: dict[str, Any]) -> bool:
    attrs = block.get("attrs") if isinstance(block.get("attrs"), dict) else {}
    class_name = clean_string(attrs.get("class")).lower()
    if "line-clamp" not in class_name:
        return False
    if not any(marker in class_name for marker in ("text-[8px]", "break-all", "overflow-hidden", "min-w-0")):
        return False

    haystack = " ".join(
        [
            clean_string(attrs.get("data-testid")),
            clean_string(attrs.get("class")),
            clean_string(attrs.get("aria-label")),
            clean_string(attrs.get("title")),
            clean_string(block.get("path")),
        ]
    ).lower()
    if any(
        marker in haystack
        for marker in (
            "assistant-message",
            "font-claude-message",
            "artifact",
            "canvas",
            "pocketreader-capture-root",
        )
    ):
        return False

    rect = block.get("rect") if isinstance(block.get("rect"), dict) else {}
    width = float_value(rect.get("width"), 0.0)
    if width and width > 260:
        return False

    return looks_like_user_prompt_text(clean_string(block.get("text")))


def looks_like_user_prompt_text(text: str) -> bool:
    value = normalize_text(text)
    if len(value) < 40 or mostly_ui_text(value):
        return False
    return bool(
        re.search(
            r"(请你|帮我|想请你|麻烦你|我想|我希望|我觉得|我认为|我感觉|我的看法|你可以|能不能|可不可以)",
            value,
        )
    )


def explicit_file_block(block: dict[str, Any]) -> bool:
    kind_hint = clean_string(block.get("kind_hint")).lower()
    if kind_hint in {"file", "artifact"}:
        return True
    haystack = block_attrs_text(block).lower()
    if match_filename(haystack):
        return any(marker in haystack for marker in ("download", "file", "attachment", "artifact"))
    return ("artifact" in haystack or "canvas" in haystack) and any(
        prefix in haystack for prefix in ("data-testid=", "class=", "aria-label=", "title=")
    )


def hidden_accessibility_block(block: dict[str, Any]) -> bool:
    attrs = block.get("attrs") if isinstance(block.get("attrs"), dict) else {}
    class_name = clean_string(attrs.get("class")).lower()
    if "sr-only" in class_name or "screen-reader" in class_name:
        return True
    if clean_string(attrs.get("aria-hidden")).lower() == "true":
        return True
    return False


def explicit_file_dict(raw_file: dict[str, Any]) -> bool:
    haystack = " ".join(clean_string(value).lower() for value in raw_file.values())
    return any(marker in haystack for marker in ("artifact", "download", "file", "attachment"))


def dedupe_message_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    for candidate in sorted(candidates, key=lambda item: int_value(item.get("index"), 0)):
        duplicate_index = -1
        for index, existing in enumerate(deduped):
            if candidate["role"] != existing["role"]:
                continue
            if text_contains_either(existing["text"], candidate["text"]):
                duplicate_index = index
                break
        if duplicate_index >= 0:
            if len(candidate["text"]) > len(deduped[duplicate_index]["text"]):
                deduped[duplicate_index] = candidate
            continue
        deduped.append(candidate)
    return sorted(deduped, key=lambda item: int_value(item.get("index"), 0))


def coalesce_consecutive_messages(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    coalesced: list[dict[str, Any]] = []
    for candidate in sorted(candidates, key=lambda item: int_value(item.get("index"), 0)):
        if coalesced and coalesced[-1]["role"] == candidate["role"]:
            previous_text = str(coalesced[-1].get("text") or "")
            current_text = str(candidate.get("text") or "")
            if current_text and not text_contains_either(previous_text, current_text):
                coalesced[-1]["text"] = normalize_text(f"{previous_text}\n\n{current_text}")
            elif len(current_text) > len(previous_text):
                coalesced[-1]["text"] = current_text
            continue
        coalesced.append(dict(candidate))
    return coalesced


def clean_message_text(value: object) -> str:
    text = normalize_text(str(value or ""))
    text = re.sub(r"^(ChatGPT|Gemini|Claude|You|User|Assistant)\s*\n", "", text, flags=re.I)
    return text[:MAX_TEXT_CHARS].strip()


def mostly_ui_text(text: str) -> bool:
    normalized = re.sub(r"\s+", " ", text).strip().lower()
    return normalized in {
        "copy",
        "share",
        "regenerate",
        "thumbs up",
        "thumbs down",
        "new chat",
        "show drafts",
        "double-check response",
    }


def has_both_roles(messages: list[dict[str, str]]) -> bool:
    roles = {message.get("role") for message in messages}
    return {"User", "AI"}.issubset(roles)


def title_from_messages(messages: list[dict[str, str]]) -> str | None:
    first_user = next((message for message in messages if message["role"] == "User"), None)
    first = first_user or (messages[0] if messages else None)
    if first is None:
        return None
    return first["text"].splitlines()[0][:80]


def block_attrs_text(block: dict[str, Any]) -> str:
    attrs = block.get("attrs") if isinstance(block.get("attrs"), dict) else {}
    parts = []
    for key in ("data-testid", "data-test-id", "class", "aria-label", "title", "download", "href"):
        value = clean_string(attrs.get(key))
        if value:
            parts.append(f"{key}={value}")
    kind_hint = clean_string(block.get("kind_hint"))
    if kind_hint:
        parts.append(f"kind={kind_hint}")
    return " ".join(parts)


def attribute_value(block: dict[str, Any], key: str) -> str:
    attrs = block.get("attrs") if isinstance(block.get("attrs"), dict) else {}
    return clean_string(attrs.get(key))


def supported_filename(filename: str) -> bool:
    extension = file_extension(filename)
    return extension in SUPPORTED_FILE_EXTENSIONS


def file_extension(filename: str) -> str:
    match = re.search(r"\.([a-z0-9]+)$", filename.lower())
    return match.group(1) if match else ""


def match_filename(text: str) -> str:
    extension_pattern = "|".join(sorted(SUPPORTED_FILE_EXTENSIONS, key=len, reverse=True))
    match = re.search(
        rf"([\w\u4e00-\u9fff][\w\u4e00-\u9fff\s._()[\]-]{{0,100}}\.({extension_pattern}))",
        str(text or ""),
        flags=re.I,
    )
    return match.group(1).strip() if match else ""


def text_contains_either(left: str, right: str) -> bool:
    normalized_left = comparable_text(left)
    normalized_right = comparable_text(right)
    if not normalized_left or not normalized_right:
        return False
    if normalized_left == normalized_right:
        return True
    shorter, longer = (
        (normalized_left, normalized_right)
        if len(normalized_left) < len(normalized_right)
        else (normalized_right, normalized_left)
    )
    return len(shorter) >= 20 and shorter in longer


def comparable_text(text: str) -> str:
    return re.sub(r"\s+", " ", normalize_text(text)).strip()


def clean_title(value: object) -> str:
    return (
        clean_string(value)
        .replace(" - ChatGPT", "")
        .replace(" | ChatGPT", "")
        .replace(" - Gemini", "")
        .replace(" | Gemini", "")
        .replace(" - Claude", "")
        .replace(" | Claude", "")
        .removeprefix("Claude - ")
        .strip()
    )


def clean_file_title(value: object) -> str:
    title = clean_string(value)
    title = re.sub(r"\b(artifact|preview|code)\b", "", title, flags=re.I)
    title = re.sub(r"^(复制|下载|预览|代码)\s*", "", title)
    return title.strip()[:120]


def first_text_line(text: str) -> str:
    for line in text.splitlines():
        line = line.strip()
        if 2 <= len(line) <= 120:
            return line
    return ""


def safe_filename(value: str) -> str:
    cleaned = re.sub(r'[\\/:*?"<>|]+', " ", value)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()[:90]
    return cleaned or "ai-generated-file"


def clean_string(value: object) -> str:
    return str(value or "").strip()


def int_value(value: object, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def float_value(value: object, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def normalize_platform(value: object) -> str:
    raw = clean_string(value).lower() or "browser"
    characters = [character for character in raw[:60] if character.isalnum() or character in ("-", "_")]
    return "".join(characters) or "browser"
