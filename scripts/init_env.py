#!/usr/bin/env python3
"""Generate an instance's credentials without printing them or overwriting files."""
from __future__ import annotations

import argparse
import ipaddress
import os
from pathlib import Path
import secrets
from urllib.parse import urlsplit


def create_env(output: Path, base_url: str, container: bool = False) -> None:
    url = urlsplit(base_url)
    loopback = url.hostname == "localhost"
    try:
        loopback = loopback or ipaddress.ip_address(url.hostname or "").is_loopback
    except ValueError:
        pass
    if (not url.hostname or url.username or url.password or url.query or url.fragment
            or url.path not in ("", "/")
            or not (url.scheme == "https" or (url.scheme == "http" and loopback))):
        raise ValueError("Use an HTTPS origin, or HTTP on localhost for development.")
    values = {
        "APP_USERNAME": "admin",
        "APP_PASSWORD": secrets.token_urlsafe(24),
        "APP_SECRET_KEY": secrets.token_hex(32),
        "FEED_TOKEN": secrets.token_urlsafe(32),
        "IMPORT_TOKEN": secrets.token_urlsafe(32),
        "APP_BASE_URL": base_url.rstrip("/"),
        "APP_DATA_DIR": "/data" if container else "data",
        "APP_LOG_DIR": "/logs" if container else "logs",
        "DEFAULT_VOICE": "zh-CN-XiaoxiaoNeural",
        "TTS_MAX_CHARS_PER_CHUNK": "1800",
        "TTS_RETRIES": "3",
    }
    output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    # O_EXCL also refuses an existing symlink. Never silently rotate credentials.
    fd = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as stream:
        stream.write("".join(f"{key}={value}\n" for key, value in values.items()))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path(".env"))
    parser.add_argument("--base-url", default="http://127.0.0.1:4780")
    parser.add_argument("--container", action="store_true", help="Use /data and /logs")
    args = parser.parse_args()
    try:
        create_env(args.output, args.base_url, args.container)
    except (OSError, ValueError) as exc:
        parser.exit(1, f"Configuration not written: {exc}\n")
    print(f"Created private configuration: {args.output}. Open locally to read login credentials.")


if __name__ == "__main__":
    main()
