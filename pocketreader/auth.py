from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Any

from fastapi import HTTPException, Request, status
from fastapi.responses import RedirectResponse

from pocketreader.config import Settings


SESSION_MAX_AGE_SECONDS = 60 * 60 * 24 * 30


def _b64encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def _sign(payload: str, secret_key: str) -> str:
    digest = hmac.new(secret_key.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256)
    return _b64encode(digest.digest())


def make_session_token(username: str, settings: Settings) -> str:
    payload = {
        "u": username,
        "exp": int(time.time()) + SESSION_MAX_AGE_SECONDS,
    }
    payload_text = _b64encode(
        json.dumps(payload, separators=(",", ":")).encode("utf-8")
    )
    signature = _sign(payload_text, settings.secret_key)
    return f"{payload_text}.{signature}"


def parse_session_token(token: str, settings: Settings) -> dict[str, Any] | None:
    try:
        payload_text, signature = token.split(".", 1)
    except ValueError:
        return None
    expected = _sign(payload_text, settings.secret_key)
    if not hmac.compare_digest(signature, expected):
        return None
    try:
        payload = json.loads(_b64decode(payload_text))
    except (ValueError, json.JSONDecodeError):
        return None
    if int(payload.get("exp", 0)) < int(time.time()):
        return None
    return payload


def password_matches(candidate: str, settings: Settings) -> bool:
    return hmac.compare_digest(candidate, settings.password)


def current_user(request: Request) -> str | None:
    settings: Settings = request.app.state.settings
    token = request.cookies.get(settings.cookie_name)
    if not token:
        return None
    payload = parse_session_token(token, settings)
    if payload is None:
        return None
    username = payload.get("u")
    if username != settings.username:
        return None
    return str(username)


def require_user(request: Request) -> str:
    user = current_user(request)
    if user is None:
        raise HTTPException(status_code=status.HTTP_303_SEE_OTHER, headers={"Location": "/login"})
    return user


def redirect_after_login(request: Request) -> RedirectResponse:
    next_url = request.query_params.get("next") or "/"
    if not next_url.startswith("/"):
        next_url = "/"
    return RedirectResponse(next_url, status_code=status.HTTP_303_SEE_OTHER)


def set_session_cookie(response: RedirectResponse, username: str, settings: Settings) -> None:
    response.set_cookie(
        settings.cookie_name,
        make_session_token(username, settings),
        max_age=SESSION_MAX_AGE_SECONDS,
        httponly=True,
        secure=settings.base_url.startswith("https://"),
        samesite="lax",
    )


def clear_session_cookie(response: RedirectResponse, settings: Settings) -> None:
    response.delete_cookie(settings.cookie_name)

