from __future__ import annotations

import asyncio
import hmac
import shutil
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from email.utils import format_datetime as format_rfc2822_datetime
from pathlib import Path
from typing import Annotated, Any

from fastapi import (
    FastAPI,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from pocketreader.auth import (
    clear_session_cookie,
    current_user,
    password_matches,
    redirect_after_login,
    require_user,
    set_session_cookie,
)
from pocketreader.config import VOICE_OPTIONS, get_settings, voice_ids
from pocketreader.db import Database, derive_title
from pocketreader.importers import import_markdown, import_messages, import_plain_text, import_url
from pocketreader.text import normalize_text
from pocketreader.tts import generate_audio


settings = get_settings()
db = Database(settings.data_dir / "pocketreader.sqlite3")
app = FastAPI(title="PocketReader")
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
app.mount("/static", StaticFiles(directory=str(Path(__file__).parent / "static")), name="static")
templates.env.filters["duration"] = lambda value: format_duration(value)
templates.env.filters["datetime"] = lambda value: format_datetime(value)
templates.env.filters["status_label"] = lambda value: status_label(value)


@app.on_event("startup")
async def on_startup() -> None:
    db.init()
    db.requeue_interrupted_items()
    app.state.settings = settings
    app.state.db = db
    app.state.worker_task = asyncio.create_task(worker_loop())


@app.on_event("shutdown")
async def on_shutdown() -> None:
    task: asyncio.Task | None = getattr(app.state, "worker_task", None)
    if task is not None:
        task.cancel()


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.head("/health")
async def health_head() -> Response:
    return Response(status_code=200)


@app.head("/")
async def index_head(request: Request) -> Response:
    if current_user(request) is None:
        return Response(status_code=status.HTTP_303_SEE_OTHER, headers={"Location": "/login"})
    return Response(status_code=200)


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request) -> HTMLResponse:
    if current_user(request):
        return RedirectResponse("/", status_code=status.HTTP_303_SEE_OTHER)
    return templates.TemplateResponse(
        request,
        "login.html",
        {"error": None, "settings": settings},
    )


@app.post("/login")
async def login(
    request: Request,
    username: Annotated[str, Form()],
    password: Annotated[str, Form()],
) -> Response:
    if username != settings.username or not password_matches(password, settings):
        return templates.TemplateResponse(
            request,
            "login.html",
            {"error": "用户名或密码不正确。", "settings": settings},
            status_code=status.HTTP_401_UNAUTHORIZED,
        )
    response = redirect_after_login(request)
    set_session_cookie(response, username, settings)
    return response


@app.post("/logout")
async def logout() -> RedirectResponse:
    response = RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)
    clear_session_cookie(response, settings)
    return response


@app.get("/", response_class=HTMLResponse)
async def index(request: Request, status_filter: str | None = None) -> HTMLResponse:
    require_user(request)
    valid_status = status_filter if status_filter in {"queued", "processing", "ready", "error"} else None
    all_items = db.list_items()
    items = [item for item in all_items if item["status"] == valid_status] if valid_status else all_items
    has_active_jobs = any(item["status"] in {"queued", "processing"} for item in all_items)
    counts = {
        "total": len(all_items),
        "ready": sum(1 for item in all_items if item["status"] == "ready"),
        "active": sum(1 for item in all_items if item["status"] in {"queued", "processing"}),
        "error": sum(1 for item in all_items if item["status"] == "error"),
        "completed": sum(1 for item in all_items if item["completed_at"]),
    }
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "items": items,
            "counts": counts,
            "has_active_jobs": has_active_jobs,
            "status_filter": valid_status,
            "voices": VOICE_OPTIONS,
            "default_voice": settings.default_voice,
            "feed_url": f"{settings.base_url}/feed/{settings.feed_token}.xml",
            "settings": settings,
        },
    )


@app.get("/extension", response_class=HTMLResponse)
async def extension_page(request: Request) -> HTMLResponse:
    require_user(request)
    return templates.TemplateResponse(
        request,
        "extension.html",
        {
            "settings": settings,
            "import_token": settings.import_token,
        },
    )


@app.post("/items/text")
async def create_text_item(
    request: Request,
    title: Annotated[str, Form()] = "",
    text: Annotated[str, Form()] = "",
    voice: Annotated[str, Form()] = settings.default_voice,
    reader_mode: Annotated[str, Form()] = "assistant",
) -> RedirectResponse:
    require_user(request)
    voice = normalize_voice(voice)
    reader_mode = normalize_reader_mode(reader_mode)
    imported = import_markdown(text, title.strip() or None)
    if not imported.body:
        raise HTTPException(status_code=400, detail="Text is empty.")
    item_id = db.create_item(
        title=imported.title or derive_title(imported.body),
        body=imported.body,
        source_type="text",
        voice=voice,
        reader_mode=reader_mode,
    )
    return RedirectResponse(f"/items/{item_id}", status_code=status.HTTP_303_SEE_OTHER)


@app.post("/items/files")
async def upload_files(
    request: Request,
    files: Annotated[list[UploadFile], File()],
    voice: Annotated[str, Form()] = settings.default_voice,
    reader_mode: Annotated[str, Form()] = "assistant",
) -> RedirectResponse:
    require_user(request)
    voice = normalize_voice(voice)
    reader_mode = normalize_reader_mode(reader_mode)
    created_ids: list[int] = []
    for upload in files:
        content = await upload.read()
        if not content:
            continue
        text = decode_upload(content)
        filename = upload.filename or "upload.txt"
        if filename.lower().endswith((".md", ".markdown")):
            imported = import_markdown(text)
        else:
            imported = import_plain_text(text)
        if not imported.body:
            continue
        item_id = db.create_item(
            title=imported.title or Path(filename).stem,
            body=imported.body,
            source_type="file",
            source_filename=filename,
            voice=voice,
            reader_mode=reader_mode,
        )
        created_ids.append(item_id)
    target = f"/items/{created_ids[0]}" if len(created_ids) == 1 else "/"
    return RedirectResponse(target, status_code=status.HTTP_303_SEE_OTHER)


@app.post("/items/url")
async def create_url_item(
    request: Request,
    url: Annotated[str, Form()],
    title: Annotated[str, Form()] = "",
    voice: Annotated[str, Form()] = settings.default_voice,
    reader_mode: Annotated[str, Form()] = "assistant",
) -> RedirectResponse:
    require_user(request)
    voice = normalize_voice(voice)
    reader_mode = normalize_reader_mode(reader_mode)
    try:
        imported = await import_url(url.strip(), reader_mode)
    except Exception as exc:
        body = f"原始链接：{url.strip()}"
        item_id = db.create_item(
            title=title.strip() or "URL 导入失败",
            body=body,
            source_type="url",
            source_url=url.strip(),
            voice=voice,
            reader_mode=reader_mode,
            status="error",
            error=f"URL 导入失败：{exc}",
        )
        return RedirectResponse(f"/items/{item_id}", status_code=status.HTTP_303_SEE_OTHER)
    if not imported.body:
        raise HTTPException(status_code=400, detail="Could not extract readable URL content.")
    item_id = db.create_item(
        title=title.strip() or imported.title or derive_title(imported.body),
        body=imported.body,
        source_type="url",
        source_url=url.strip(),
        voice=voice,
        reader_mode=reader_mode,
    )
    return RedirectResponse(f"/items/{item_id}", status_code=status.HTTP_303_SEE_OTHER)


@app.get("/items/{item_id}", response_class=HTMLResponse)
async def item_detail(request: Request, item_id: int) -> HTMLResponse:
    require_user(request)
    item = db.get_item(item_id)
    if item is None:
        raise HTTPException(status_code=404)
    return templates.TemplateResponse(
        request,
        "item.html",
        {
            "item": item,
            "next_ready_id": db.next_ready_item_id(item_id),
            "voices": VOICE_OPTIONS,
            "settings": settings,
        },
    )


@app.post("/items/{item_id}/retry")
async def retry_item(request: Request, item_id: int) -> RedirectResponse:
    require_user(request)
    if db.get_item(item_id) is None:
        raise HTTPException(status_code=404)
    db.retry_item(item_id)
    return RedirectResponse(f"/items/{item_id}", status_code=status.HTTP_303_SEE_OTHER)


@app.post("/items/{item_id}/title")
async def update_title(
    request: Request,
    item_id: int,
    title: Annotated[str, Form()],
) -> RedirectResponse:
    require_user(request)
    if db.get_item(item_id) is None:
        raise HTTPException(status_code=404)
    db.update_title(item_id, title)
    return RedirectResponse(f"/items/{item_id}", status_code=status.HTTP_303_SEE_OTHER)


@app.post("/items/{item_id}/delete")
async def delete_item(request: Request, item_id: int) -> RedirectResponse:
    require_user(request)
    db.delete_item(item_id)
    shutil.rmtree(settings.data_dir / "audio" / str(item_id), ignore_errors=True)
    return RedirectResponse("/", status_code=status.HTTP_303_SEE_OTHER)


@app.get("/audio/{item_id}.mp3")
async def audio_file(request: Request, item_id: int, token: str | None = None) -> FileResponse:
    item, audio_path = ready_audio_file(request, item_id, token)
    filename = safe_audio_filename(item["title"])
    return FileResponse(audio_path, media_type="audio/mpeg", filename=filename)


@app.head("/audio/{item_id}.mp3")
async def audio_file_head(request: Request, item_id: int, token: str | None = None) -> Response:
    _, audio_path = ready_audio_file(request, item_id, token)
    return Response(
        status_code=200,
        media_type="audio/mpeg",
        headers={
            "Accept-Ranges": "bytes",
            "Content-Length": str(audio_path.stat().st_size),
        },
    )


def ready_audio_file(request: Request, item_id: int, token: str | None) -> tuple[Any, Path]:
    if token != settings.feed_token and current_user(request) is None:
        raise HTTPException(status_code=404)
    item = db.get_item(item_id)
    if item is None or item["status"] != "ready" or not item["audio_path"]:
        raise HTTPException(status_code=404)
    audio_path = settings.data_dir / item["audio_path"]
    if not audio_path.is_file():
        raise HTTPException(status_code=404)
    return item, audio_path


@app.post("/api/items/{item_id}/event")
async def record_event(request: Request, item_id: int) -> dict[str, str]:
    require_user(request)
    payload = await request.json()
    event_type = str(payload.get("event", "progress"))
    position = float(payload.get("position", 0) or 0)
    if event_type not in {"play", "pause", "progress", "seek", "ended"}:
        event_type = "progress"
    db.record_event(item_id, event_type, position)
    return {"status": "ok"}


@app.post("/api/browser-capture")
async def browser_capture(request: Request) -> dict[str, object]:
    payload = await request.json()
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Expected a JSON object.")
    require_import_token(request, payload)

    title = str(payload.get("title") or "").strip()
    source_url = str(payload.get("url") or "").strip()
    platform = normalize_capture_platform(payload.get("platform"))
    voice = normalize_voice(str(payload.get("voice") or settings.default_voice))
    reader_mode = normalize_reader_mode(str(payload.get("reader_mode") or "assistant"))
    messages = payload.get("messages")
    body = payload.get("body")

    if isinstance(messages, list):
        imported = import_messages(messages, reader_mode, title or None)
    elif isinstance(body, str):
        imported = import_markdown(body, title or None)
    else:
        raise HTTPException(status_code=400, detail="No captured content was provided.")

    if not imported.body:
        raise HTTPException(status_code=400, detail="Captured content is empty.")

    item_id = db.create_item(
        title=imported.title or derive_title(imported.body),
        body=imported.body,
        source_type=f"browser:{platform}",
        source_url=source_url or None,
        voice=voice,
        reader_mode=reader_mode,
    )
    return {
        "status": "ok",
        "item_id": item_id,
        "item_url": f"{settings.base_url}/items/{item_id}",
    }


@app.get("/feed/{token}.xml")
async def podcast_feed(token: str) -> Response:
    if token != settings.feed_token:
        raise HTTPException(status_code=404)
    rss = build_podcast_feed()
    return Response(rss, media_type="application/rss+xml; charset=utf-8")


@app.get("/sw.js")
async def service_worker() -> FileResponse:
    return FileResponse(Path(__file__).parent / "static" / "sw.js", media_type="text/javascript")


async def worker_loop() -> None:
    while True:
        item = db.claim_next_item()
        if item is None:
            await asyncio.sleep(2)
            continue
        try:
            output_dir = settings.data_dir / "audio" / str(item["id"])
            audio_path, duration_seconds = await generate_audio(
                text=item["body"],
                voice=item["voice"],
                output_dir=output_dir,
                max_chars_per_chunk=settings.tts_max_chars_per_chunk,
                retries=settings.tts_retries,
            )
            relative_path = audio_path.relative_to(settings.data_dir).as_posix()
            db.mark_ready(int(item["id"]), relative_path, duration_seconds)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            db.mark_error(int(item["id"]), str(exc))


def normalize_voice(voice: str) -> str:
    return voice if voice in voice_ids() else settings.default_voice


def normalize_reader_mode(reader_mode: str) -> str:
    return reader_mode if reader_mode in {"assistant", "all"} else "assistant"


def normalize_capture_platform(value: object) -> str:
    raw = str(value or "browser").strip().lower()
    characters = [
        character for character in raw[:60] if character.isalnum() or character in ("-", "_")
    ]
    return "".join(characters) or "browser"


def require_import_token(request: Request, payload: object) -> None:
    if not settings.import_token:
        raise HTTPException(status_code=503, detail="IMPORT_TOKEN is not configured.")
    body_token = payload.get("token") if isinstance(payload, dict) else None
    candidate = request.headers.get("x-pocketreader-import-token") or str(body_token or "")
    if not hmac.compare_digest(candidate, settings.import_token):
        raise HTTPException(status_code=401, detail="Invalid import token.")


def decode_upload(content: bytes) -> str:
    for encoding in ("utf-8", "utf-8-sig", "gb18030"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    return content.decode("utf-8", errors="replace")


def safe_audio_filename(title: str) -> str:
    allowed = []
    for character in title:
        if character.isalnum() or character in ("-", "_", " "):
            allowed.append(character)
    name = "".join(allowed).strip()[:80] or "pocketreader"
    return f"{name}.mp3"


def build_podcast_feed() -> str:
    atom_namespace = "http://www.w3.org/2005/Atom"
    itunes_namespace = "http://www.itunes.com/dtds/podcast-1.0.dtd"
    ET.register_namespace("atom", atom_namespace)
    ET.register_namespace("itunes", itunes_namespace)
    ready_items = db.ready_items_for_feed()
    rss = ET.Element("rss", version="2.0")
    channel = ET.SubElement(rss, "channel")
    ET.SubElement(channel, "title").text = "PocketReader"
    ET.SubElement(channel, "link").text = settings.base_url
    ET.SubElement(channel, "description").text = "Private PocketReader audio feed"
    ET.SubElement(channel, "language").text = "zh-cn"
    ET.SubElement(channel, "generator").text = "PocketReader"
    ET.SubElement(channel, "ttl").text = "60"
    ET.SubElement(channel, f"{{{itunes_namespace}}}author").text = "PocketReader"
    ET.SubElement(channel, f"{{{itunes_namespace}}}explicit").text = "false"
    ET.SubElement(
        channel,
        f"{{{atom_namespace}}}link",
        {
            "href": f"{settings.base_url}/feed/{settings.feed_token}.xml",
            "rel": "self",
            "type": "application/rss+xml",
        },
    )
    if ready_items:
        latest_updated = max(str(item["updated_at"] or item["created_at"]) for item in ready_items)
        ET.SubElement(channel, "lastBuildDate").text = format_rss_datetime(latest_updated)
        ET.SubElement(channel, "pubDate").text = format_rss_datetime(ready_items[0]["created_at"])
    for item in ready_items:
        episode = ET.SubElement(channel, "item")
        ET.SubElement(episode, "title").text = item["title"]
        ET.SubElement(episode, "link").text = f"{settings.base_url}/items/{item['id']}"
        ET.SubElement(episode, "description").text = (item["body"] or "")[:500]
        guid = ET.SubElement(episode, "guid", {"isPermaLink": "false"})
        guid.text = f"pocketreader-{item['id']}"
        ET.SubElement(episode, "pubDate").text = format_rss_datetime(item["created_at"])
        ET.SubElement(episode, f"{{{itunes_namespace}}}duration").text = format_podcast_duration(
            item["duration_seconds"]
        )
        ET.SubElement(episode, f"{{{itunes_namespace}}}explicit").text = "false"
        audio_url = f"{settings.base_url}/audio/{item['id']}.mp3?token={settings.feed_token}"
        enclosure = ET.SubElement(episode, "enclosure")
        enclosure.set("url", audio_url)
        enclosure.set("type", "audio/mpeg")
        audio_path = settings.data_dir / item["audio_path"]
        enclosure.set("length", str(audio_path.stat().st_size if audio_path.exists() else 0))
    return ET.tostring(rss, encoding="utf-8", xml_declaration=True).decode("utf-8")


def format_rss_datetime(value: object) -> str:
    try:
        date_value = datetime.fromisoformat(str(value))
    except ValueError:
        date_value = datetime.now(UTC)
    if date_value.tzinfo is None:
        date_value = date_value.replace(tzinfo=UTC)
    return format_rfc2822_datetime(date_value)


def format_podcast_duration(value: object) -> str:
    if value is None:
        return "0:00"
    seconds = max(0, int(round(float(value))))
    minutes, secs = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def format_duration(value: object) -> str:
    if value is None:
        return "--:--"
    seconds = max(0, int(float(value)))
    minutes, secs = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def format_datetime(value: object) -> str:
    if not value:
        return "-"
    text = str(value)
    return text.replace("T", " ").replace("+00:00", " UTC")


def status_label(value: object) -> str:
    return {
        "queued": "排队中",
        "processing": "生成中",
        "ready": "可播放",
        "error": "出错",
    }.get(str(value), str(value))
