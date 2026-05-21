from __future__ import annotations

import re
from html import unescape

from bs4 import BeautifulSoup


WHITESPACE_RE = re.compile(r"[ \t\r\f\v]+")
BLANK_LINES_RE = re.compile(r"\n{3,}")


def normalize_text(text: str) -> str:
    text = unescape(text).replace("\u00a0", " ")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [WHITESPACE_RE.sub(" ", line).strip() for line in text.splitlines()]
    text = "\n".join(line for line in lines)
    text = BLANK_LINES_RE.sub("\n\n", text)
    return text.strip()


def markdown_to_speech_text(markdown: str) -> str:
    text = markdown
    text = re.sub(r"```[^\n]*\n(.*?)\n?```", r"\1", text, flags=re.S)
    text = re.sub(r"~~~[^\n]*\n(.*?)\n?~~~", r"\1", text, flags=re.S)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"(\*\*|__)(.*?)\1", r"\2", text)
    text = re.sub(r"(?<!\*)\*([^*\n]+)\*(?!\*)", r"\1", text)
    text = re.sub(r"(?<!_)_([^_\n]+)_(?!_)", r"\1", text)
    text = re.sub(r"~~(.*?)~~", r"\1", text)
    text = re.sub(r"!\[([^\]]*)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"^[ \t]{0,3}#{1,6}[ \t]*(.*?)[ \t]*#*[ \t]*$", r"\1", text, flags=re.M)
    text = re.sub(r"^[ \t]{0,3}(=+|-+)[ \t]*$", "", text, flags=re.M)
    text = re.sub(r"^[ \t]{0,3}([-*_])(?:[ \t]*\1){2,}[ \t]*$", "", text, flags=re.M)
    text = "\n".join(markdown_table_line_to_text(line) for line in text.splitlines())
    text = re.sub(r"^\s*[-*+]\s+(?:\[[ xX]\]\s*)?", "", text, flags=re.M)
    text = re.sub(r"^\s*>\s?", "", text, flags=re.M)
    text = re.sub(r"<[^>]+>", " ", text)
    return normalize_text(text)


def title_from_markdown(markdown: str) -> str | None:
    for raw_line in markdown.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("#"):
            return re.sub(r"\s+#*$", "", line.lstrip("#").strip())[:120] or None
        return line[:120]
    return None


def markdown_table_line_to_text(line: str) -> str:
    stripped = line.strip()
    if not (stripped.startswith("|") and stripped.endswith("|")):
        return line
    cells = [cell.strip() for cell in stripped.strip("|").split("|")]
    if cells and all(re.fullmatch(r":?-{3,}:?", cell.replace(" ", "")) for cell in cells):
        return ""
    return "，".join(cell for cell in cells if cell)


def html_to_text(html: str) -> tuple[str | None, str]:
    soup = BeautifulSoup(html, "html.parser")
    title = None
    if soup.title and soup.title.string:
        title = soup.title.string.strip()
    for selector in ("script", "style", "noscript", "svg", "nav", "footer", "header"):
        for tag in soup.select(selector):
            tag.decompose()
    for br in soup.find_all("br"):
        br.replace_with("\n")
    for block in soup.find_all(["p", "div", "li", "h1", "h2", "h3", "h4", "section"]):
        block.append("\n")
    text = soup.get_text("\n")
    return title, normalize_text(text)


def split_text_for_tts(text: str, max_chars: int) -> list[str]:
    clean = normalize_text(text)
    if len(clean) <= max_chars:
        return [clean] if clean else []

    paragraphs = [part.strip() for part in re.split(r"\n{2,}", clean) if part.strip()]
    chunks: list[str] = []
    current = ""
    for paragraph in paragraphs:
        pieces = _split_paragraph(paragraph, max_chars)
        for piece in pieces:
            candidate = piece if not current else f"{current}\n\n{piece}"
            if len(candidate) <= max_chars:
                current = candidate
                continue
            if current:
                chunks.append(current)
            current = piece
    if current:
        chunks.append(current)
    return chunks


def _split_paragraph(paragraph: str, max_chars: int) -> list[str]:
    if len(paragraph) <= max_chars:
        return [paragraph]
    sentences = re.split(r"(?<=[。！？!?；;.!?])\s*", paragraph)
    pieces: list[str] = []
    current = ""
    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
        if len(sentence) > max_chars:
            if current:
                pieces.append(current)
                current = ""
            pieces.extend(
                sentence[index : index + max_chars]
                for index in range(0, len(sentence), max_chars)
            )
            continue
        candidate = sentence if not current else f"{current} {sentence}"
        if len(candidate) <= max_chars:
            current = candidate
        else:
            pieces.append(current)
            current = sentence
    if current:
        pieces.append(current)
    return pieces
