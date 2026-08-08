"""Portable content identity for subtitle sidecars."""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path

from .errors import SubtitleIntegrityError

SUBTITLE_SHA256_METADATA_KEY = "subtitles_bridge_sha256"


def subtitle_sha256(path: Path) -> str:
    digest = sha256()
    try:
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise SubtitleIntegrityError(
            f"Cannot calculate subtitle SHA-256 for {path}: {exc}"
        ) from exc
    return digest.hexdigest()
