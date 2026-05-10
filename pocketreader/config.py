from __future__ import annotations

import os
import secrets
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Voice:
    id: str
    label: str
    language: str


VOICE_OPTIONS: tuple[Voice, ...] = (
    Voice("zh-CN-XiaoxiaoNeural", "中文女声 - Xiaoxiao", "zh-CN"),
    Voice("zh-CN-XiaoyiNeural", "中文女声 - Xiaoyi", "zh-CN"),
    Voice("zh-CN-YunxiNeural", "中文男声 - Yunxi", "zh-CN"),
    Voice("zh-CN-YunjianNeural", "中文男声 - Yunjian", "zh-CN"),
    Voice("zh-TW-HsiaoChenNeural", "台湾中文女声 - HsiaoChen", "zh-TW"),
    Voice("en-US-EmmaMultilingualNeural", "中英混合女声 - Emma", "en-US"),
    Voice("en-US-AriaNeural", "英文女声 - Aria", "en-US"),
    Voice("en-US-GuyNeural", "英文男声 - Guy", "en-US"),
)


@dataclass(frozen=True)
class Settings:
    username: str
    password: str
    secret_key: str
    feed_token: str
    import_token: str
    base_url: str
    data_dir: Path
    log_dir: Path
    default_voice: str
    tts_max_chars_per_chunk: int
    tts_retries: int
    cookie_name: str = "pocketreader_session"


def get_settings() -> Settings:
    data_dir = Path(os.environ.get("APP_DATA_DIR", "data")).resolve()
    log_dir = Path(os.environ.get("APP_LOG_DIR", "logs")).resolve()
    data_dir.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)
    audio_dir = data_dir / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)

    return Settings(
        username=os.environ.get("APP_USERNAME", "test-user"),
        password=os.environ.get("APP_PASSWORD", "CHANGE_ME"),
        secret_key=os.environ.get("APP_SECRET_KEY", secrets.token_hex(32)),
        feed_token=os.environ.get("FEED_TOKEN", secrets.token_urlsafe(32)),
        import_token=os.environ.get("IMPORT_TOKEN", ""),
        base_url=os.environ.get("APP_BASE_URL", "http://127.0.0.1:4780").rstrip("/"),
        data_dir=data_dir,
        log_dir=log_dir,
        default_voice=os.environ.get("DEFAULT_VOICE", "zh-CN-XiaoxiaoNeural"),
        tts_max_chars_per_chunk=max(
            500, int(os.environ.get("TTS_MAX_CHARS_PER_CHUNK", "1800"))
        ),
        tts_retries=max(0, int(os.environ.get("TTS_RETRIES", "3"))),
    )


def voice_ids() -> set[str]:
    return {voice.id for voice in VOICE_OPTIONS}
