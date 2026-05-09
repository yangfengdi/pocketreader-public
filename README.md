# PocketReader

PocketReader is a personal read-it-later audio service. It imports text,
Markdown, files, and public links, generates MP3 files with Microsoft Edge TTS,
then lets an iPhone play, pause, resume, cache, and continue through the queue.

The first production target is a self-hosted Web/PWA deployment at:

```text
https://reader.example.com
```

## What It Does

- Import plain text or Markdown from a desktop or phone.
- Upload multiple `.txt` / `.md` files in one batch.
- Import public URLs, including best-effort parsing for AI share links.
- Choose from multiple TTS voices in the web UI.
- Generate long audio by splitting text into safe chunks, then merging MP3 files.
- Keep item metadata: created time, generated time, first played, last played,
  completed time, and playback position.
- Play on iPhone with resume, skip, playback speed, and auto-next.
- Cache an audio file from the item page for offline listening.
- Expose a private podcast feed protected by a long random token.

## Current Product Decisions

- First version is Web/PWA, not a native iOS app.
- Single-owner login is enough.
- Default AI conversation mode is "AI replies only".
- URL import is best-effort. Public pages work best; private pages that require a
  browser login should be pasted as text or Markdown.
- Audio is stored on the server and is not automatically deleted yet.

## Repository Layout

```text
pocketreader/                 FastAPI application package
  main.py                     HTTP routes, worker lifecycle, podcast feed
  db.py                       SQLite schema and data access
  tts.py                      edge-tts generation, chunking, ffmpeg merge
  importers.py                text, Markdown, URL, and AI-link extraction
  text.py                     cleanup and split helpers
  templates/                  server-rendered HTML
  static/                     CSS, JS, PWA manifest, service worker
deploy/
  pocketreader.caddy          Caddy snippet for the production domain
  pocketreader.env.example    Environment template
docs/
  requirements.md             Product requirements and usage model
  architecture.md             System design
  deployment.md               Server deployment and rollback
  operations.md               Common maintenance tasks
tests/                        Lightweight regression tests
```

## Local Development

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
APP_USERNAME=admin \
APP_PASSWORD=CHANGE_ME \
APP_SECRET_KEY=dev-secret \
FEED_TOKEN=dev-feed-token \
APP_BASE_URL=http://127.0.0.1:4780 \
.venv/bin/uvicorn pocketreader.main:app --host 127.0.0.1 --port 4780
```

Open:

```text
http://127.0.0.1:4780
```

## Production Deployment

Production is isolated from the existing `other_app` / other-app app:

```text
/opt/apps/pocketreader
/var/lib/apps/pocketreader
/etc/apps/pocketreader
/var/log/apps/pocketreader
```

The backend only binds to the host loopback address:

```text
127.0.0.1:4780
```

Public HTTPS is handled by Caddy through:

```text
/etc/caddy/apps/pocketreader.caddy
```

Full steps are in [docs/deployment.md](docs/deployment.md).

## TTS Notes

The TTS implementation follows the existing `../pte_speaking` approach:

- `edge-tts` provides speech synthesis.
- `ffmpeg` and `ffprobe` merge and validate MP3 duration.
- Text is split into chunks with a default 1800-character ceiling, which keeps
  each request well below the free API's practical 10-minute MP3 limit.

## Security Notes

- Do not commit `/etc/apps/pocketreader/pocketreader.env`.
- Do not reuse the server root password as the app password.
- Podcast audio URLs use a long random feed token.
- The provided production password can be changed by editing the env file and
  recreating the Docker container.

