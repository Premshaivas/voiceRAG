from __future__ import annotations

import json
import subprocess
from pathlib import Path

from .config import Settings, settings

ALLOWED_CODECS = {"aac", "alac", "flac", "mp3", "opus", "pcm_s16le", "vorbis", "ac3", "eac3"}


def validate_media(path: str | Path, active_settings: Settings = settings) -> dict:
    command = ["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=codec_type,codec_name", "-of", "json", str(path)]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=30, check=True)
    except FileNotFoundError as exc:
        raise RuntimeError("ffprobe is required for media validation") from exc
    except subprocess.CalledProcessError as exc:
        raise ValueError(f"ffprobe rejected the media: {exc.stderr.strip()}") from exc
    data = json.loads(result.stdout)
    duration = float((data.get("format") or {}).get("duration") or 0)
    if duration <= 0 or duration > active_settings.max_audio_duration_seconds:
        raise ValueError(f"Audio duration must be between 0 and {active_settings.max_audio_duration_seconds} seconds")
    streams = data.get("streams") or []
    audio_streams = [stream for stream in streams if stream.get("codec_type") == "audio"]
    if not audio_streams:
        raise ValueError("Media contains no audio stream")
    codecs = {stream.get("codec_name") for stream in audio_streams}
    if not codecs.intersection(ALLOWED_CODECS):
        raise ValueError(f"Audio codec is not allowed: {sorted(codecs)}")
    return {"duration_seconds": duration, "codecs": sorted(codecs)}
