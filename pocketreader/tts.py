from __future__ import annotations

import asyncio
import shutil
import subprocess
from pathlib import Path

import aiohttp
import edge_tts
from edge_tts import exceptions as edge_tts_exceptions

from pocketreader.text import split_text_for_tts


class TtsError(RuntimeError):
    pass


async def generate_audio(
    *,
    text: str,
    voice: str,
    output_dir: Path,
    max_chars_per_chunk: int,
    retries: int,
) -> tuple[Path, float]:
    output_dir.mkdir(parents=True, exist_ok=True)
    final_path = output_dir / "audio.mp3"
    temp_dir = output_dir / "chunks"
    if temp_dir.exists():
        shutil.rmtree(temp_dir)
    temp_dir.mkdir(parents=True)

    chunks = split_text_for_tts(text, max_chars_per_chunk)
    if not chunks:
        raise TtsError("No readable text to synthesize.")

    chunk_paths: list[Path] = []
    for index, chunk in enumerate(chunks, start=1):
        chunk_path = temp_dir / f"chunk-{index:04d}.mp3"
        await synthesize_chunk(
            text=chunk,
            audio_path=chunk_path,
            voice=voice,
            retries=retries,
        )
        duration = probe_duration(chunk_path)
        if duration > 600:
            raise TtsError(
                f"Generated chunk {index} is {duration:.0f}s, above the 10 minute limit."
            )
        chunk_paths.append(chunk_path)

    if len(chunk_paths) == 1:
        shutil.copyfile(chunk_paths[0], final_path)
    else:
        concat_mp3(chunk_paths, final_path, temp_dir)

    duration_seconds = probe_duration(final_path)
    shutil.rmtree(temp_dir, ignore_errors=True)
    return final_path, duration_seconds


async def synthesize_chunk(
    *,
    text: str,
    audio_path: Path,
    voice: str,
    retries: int,
) -> None:
    temp_audio_path = audio_path.with_suffix(".mp3.part")
    max_attempts = retries + 1
    for attempt in range(1, max_attempts + 1):
        temp_audio_path.unlink(missing_ok=True)
        communicate = edge_tts.Communicate(
            text,
            voice=voice,
            rate="+0%",
            volume="+0%",
            pitch="+0Hz",
            connect_timeout=10,
            receive_timeout=30,
        )
        try:
            with temp_audio_path.open("wb") as audio_file:
                async for packet in communicate.stream():
                    if packet["type"] == "audio":
                        audio_file.write(packet["data"])
            temp_audio_path.replace(audio_path)
            return
        except (
            aiohttp.ClientError,
            asyncio.TimeoutError,
            ConnectionError,
            OSError,
            edge_tts_exceptions.EdgeTTSException,
        ) as exc:
            temp_audio_path.unlink(missing_ok=True)
            if attempt >= max_attempts:
                raise TtsError(f"TTS failed after {max_attempts} attempts: {exc}") from exc
            await asyncio.sleep(min(2 ** (attempt - 1), 8))
        except Exception:
            temp_audio_path.unlink(missing_ok=True)
            raise


def concat_mp3(chunk_paths: list[Path], final_path: Path, temp_dir: Path) -> None:
    concat_file = temp_dir / "concat.txt"
    concat_file.write_text(
        "".join(f"file '{path.as_posix()}'\n" for path in chunk_paths),
        encoding="utf-8",
    )
    temp_final = final_path.with_suffix(".mp3.part")
    temp_final.unlink(missing_ok=True)
    command = [
        "ffmpeg",
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(concat_file),
        "-c:a",
        "libmp3lame",
        "-q:a",
        "2",
        str(temp_final),
    ]
    run_command(command)
    temp_final.replace(final_path)


def probe_duration(audio_path: Path) -> float:
    command = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(audio_path),
    ]
    completed = subprocess.run(command, check=True, capture_output=True, text=True)
    return float(completed.stdout.strip())


def run_command(command: list[str]) -> None:
    completed = subprocess.run(command, capture_output=True, text=True)
    if completed.returncode == 0:
        return
    stderr_tail = "\n".join(completed.stderr.splitlines()[-12:])
    raise TtsError(f"Command failed: {' '.join(command)}\n{stderr_tail}")

