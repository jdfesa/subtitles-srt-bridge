"""Read-only decoding and structural validation for SRT sidecars."""

from __future__ import annotations

from pathlib import Path
import re

from .models import SubtitleValidation


TIMESTAMP_RE = re.compile(
    r"^\s*(\d+):(\d{2}):(\d{2}),(\d{3})\s*-->\s*"
    r"(\d+):(\d{2}):(\d{2}),(\d{3})(?:\s+.*)?$"
)
BLOCK_SEPARATOR_RE = re.compile(r"\n[ \t]*\n+")


def _decode_srt(data: bytes) -> tuple[str, str]:
    if data.startswith(b"\xef\xbb\xbf"):
        return data.decode("utf-8-sig"), "utf-8-sig"
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16"), "utf-16"
    try:
        return data.decode("utf-8"), "utf-8"
    except UnicodeDecodeError:
        return data.decode("cp1252"), "cp1252"


def _timestamp_milliseconds(parts: tuple[str, ...]) -> int:
    hours, minutes, seconds, milliseconds = (int(part) for part in parts)
    if minutes >= 60 or seconds >= 60:
        raise ValueError("minutes and seconds must be below 60")
    return (((hours * 60) + minutes) * 60 + seconds) * 1000 + milliseconds


def _validate_block(block: str, position: int) -> str | None:
    lines = block.split("\n")
    if len(lines) < 2:
        return f"Cue {position} must contain an index and timestamp"
    if not lines[0].strip().isdigit():
        return f"Cue {position} has a non-numeric index"

    match = TIMESTAMP_RE.fullmatch(lines[1])
    if match is None:
        return f"Cue {position} has an invalid timestamp"

    try:
        start = _timestamp_milliseconds(match.groups()[:4])
        end = _timestamp_milliseconds(match.groups()[4:])
    except ValueError as exc:
        return f"Cue {position} has an invalid timestamp: {exc}"
    if end < start:
        return f"Cue {position} ends before it starts"
    if len(lines) < 3 or not any(line.strip() for line in lines[2:]):
        return f"Cue {position} has no subtitle text"
    return None


class SrtValidator:
    def validate(self, path: Path) -> SubtitleValidation:
        try:
            data = path.read_bytes()
        except OSError as exc:
            return SubtitleValidation(False, 0, error=f"Cannot read SRT: {exc}")
        if not data:
            return SubtitleValidation(False, 0, error="SRT is empty")

        try:
            content, encoding = _decode_srt(data)
        except UnicodeError as exc:
            return SubtitleValidation(False, 0, error=f"Cannot decode SRT: {exc}")

        normalized = content.replace("\r\n", "\n").replace("\r", "\n").strip()
        if not normalized:
            return SubtitleValidation(False, 0, encoding, "SRT has no cues")

        blocks = BLOCK_SEPARATOR_RE.split(normalized)
        for position, block in enumerate(blocks, start=1):
            error = _validate_block(block, position)
            if error is not None:
                return SubtitleValidation(False, position - 1, encoding, error)

        return SubtitleValidation(True, len(blocks), encoding)
