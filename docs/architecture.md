# Architecture

## Overview

PocketReader is a small self-hosted FastAPI application. It avoids a separate
frontend build system so it remains easy to maintain on a small VPS.

```text
iPhone/Desktop Browser
        |
        | HTTPS
        v
Caddy reader.example.com
        |
        | reverse_proxy 127.0.0.1:4780
        v
Docker container: FastAPI + worker
        |
        +-- SQLite database
        +-- MP3 files under /var/lib/apps/pocketreader/audio
        +-- edge-tts outbound requests
        +-- ffmpeg / ffprobe
```

```text
Chrome on AI sites
        |
        | extension extracts visible conversation text
        v
POST /api/browser-capture with IMPORT_TOKEN
        |
        v
normal PocketReader item queue
```

## Runtime Components

- `pocketreader.main`
  - FastAPI routes.
  - Login/logout.
  - Import forms.
  - Audio streaming.
  - Podcast feed.
  - Starts one background worker task.

- `pocketreader.db`
  - SQLite schema.
  - Item, job, and listen event persistence.
  - Queue claiming with `BEGIN IMMEDIATE`.

- `pocketreader.tts`
  - Splits text into chunks.
  - Calls `edge_tts.Communicate`.
  - Validates each chunk duration with `ffprobe`.
  - Merges chunks with `ffmpeg`.

- `pocketreader.importers`
  - Plain text and Markdown cleanup.
  - Public URL extraction with `httpx` and BeautifulSoup.
  - Best-effort JSON scanning for shared AI conversations.
  - Normalization for browser-extension message payloads.

- `browser-extension`
  - Manifest V3 Chrome extension.
  - Injects a capture button into ChatGPT, Gemini, and Claude.
  - Sends extracted messages to `/api/browser-capture`.

## Database

The database lives at:

```text
/var/lib/apps/pocketreader/pocketreader.sqlite3
```

Main tables:

- `items`: title, body, source, status, audio path, playback state, timestamps.
- `jobs`: queued/processing/done/error job history.
- `listen_events`: play, pause, progress, seek, and ended events.

## Audio Storage

Each item gets its own folder:

```text
/var/lib/apps/pocketreader/audio/<item_id>/audio.mp3
```

Temporary chunks are created under:

```text
/var/lib/apps/pocketreader/audio/<item_id>/chunks/
```

The chunk directory is removed after a successful merge.

## Security Model

- One configured username and password.
- Session cookie is HMAC-signed by `APP_SECRET_KEY`.
- Audio files require either a valid session or the private `FEED_TOKEN`.
- Browser capture requires the separate private `IMPORT_TOKEN`.
- Docker publishes only `127.0.0.1:4780`.
- Caddy is the only public HTTPS entry point.
