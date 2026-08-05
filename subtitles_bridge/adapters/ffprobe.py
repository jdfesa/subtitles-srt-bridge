"""FFprobe adapter that maps JSON output into immutable core models."""

from __future__ import annotations

from collections.abc import Callable
import json
import math
from pathlib import Path
import subprocess
from typing import Any

from ..errors import MediaInspectionError
from ..languages import normalize_language_code
from ..models import MediaChapter, MediaInspection, MediaStream, StreamKind


Runner = Callable[..., subprocess.CompletedProcess[str]]


STREAM_KINDS = {
    "attachment": StreamKind.ATTACHMENT,
    "audio": StreamKind.AUDIO,
    "data": StreamKind.DATA,
    "subtitle": StreamKind.SUBTITLE,
    "video": StreamKind.VIDEO,
}


def _metadata(raw: Any) -> tuple[tuple[str, str], ...]:
    if not isinstance(raw, dict):
        return ()
    return tuple(sorted((str(key), str(value)) for key, value in raw.items()))


def _scalar_properties(raw_stream: dict[str, Any]) -> tuple[tuple[str, str], ...]:
    ignored = {"codec_name", "codec_type", "disposition", "index", "tags"}
    return tuple(
        sorted(
            (str(key), str(value))
            for key, value in raw_stream.items()
            if key not in ignored and not isinstance(value, (dict, list))
        )
    )


def _parse_float(value: Any, label: str) -> float | None:
    if value in (None, "", "N/A"):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise MediaInspectionError(f"Invalid {label} from FFprobe: {value}") from exc
    if not math.isfinite(parsed):
        raise MediaInspectionError(f"Invalid {label} from FFprobe: {value}")
    return parsed


class FFprobeMediaProbe:
    def __init__(
        self,
        executable: str = "ffprobe",
        runner: Runner = subprocess.run,
    ) -> None:
        self.executable = executable
        self.runner = runner

    def inspect(self, source: Path) -> MediaInspection:
        command = [
            self.executable,
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            "-show_chapters",
            str(source),
        ]
        try:
            result = self.runner(
                command,
                capture_output=True,
                text=True,
                check=False,
            )
        except OSError as exc:
            raise MediaInspectionError(
                f"Cannot execute FFprobe '{self.executable}': {exc}"
            ) from exc

        if result.returncode != 0:
            message = result.stderr.strip() or f"FFprobe failed for {source}"
            raise MediaInspectionError(message)

        try:
            payload = json.loads(result.stdout)
        except (json.JSONDecodeError, TypeError) as exc:
            raise MediaInspectionError(f"FFprobe returned invalid JSON for {source}") from exc
        if not isinstance(payload, dict):
            raise MediaInspectionError(f"FFprobe returned invalid JSON for {source}")

        streams = self._streams(payload.get("streams", []))
        if not any(stream.kind is StreamKind.VIDEO for stream in streams):
            raise MediaInspectionError(f"Input has no video stream: {source}")

        raw_format = payload.get("format") or {}
        if not isinstance(raw_format, dict):
            raise MediaInspectionError("FFprobe format must be an object")
        duration = _parse_float(raw_format.get("duration"), "media duration")
        chapters = self._chapters(payload.get("chapters", []))
        try:
            return MediaInspection(
                streams=streams,
                format_name=(
                    str(raw_format["format_name"])
                    if raw_format.get("format_name") is not None
                    else None
                ),
                duration_seconds=duration,
                chapters=chapters,
                metadata=_metadata(raw_format.get("tags")),
            )
        except ValueError as exc:
            raise MediaInspectionError(f"Invalid FFprobe inventory: {exc}") from exc

    def _streams(self, raw_streams: Any) -> tuple[MediaStream, ...]:
        if not isinstance(raw_streams, list):
            raise MediaInspectionError("FFprobe streams must be a list")

        streams: list[MediaStream] = []
        for raw_stream in raw_streams:
            if not isinstance(raw_stream, dict) or "index" not in raw_stream:
                raise MediaInspectionError("FFprobe returned a stream without an index")
            try:
                index = int(raw_stream["index"])
            except (TypeError, ValueError) as exc:
                raise MediaInspectionError("FFprobe returned an invalid stream index") from exc

            tags = raw_stream.get("tags") or {}
            if not isinstance(tags, dict):
                tags = {}
            dispositions_raw = raw_stream.get("disposition") or {}
            if not isinstance(dispositions_raw, dict):
                dispositions_raw = {}
            dispositions = frozenset(
                str(name)
                for name, enabled in dispositions_raw.items()
                if bool(enabled)
            )
            try:
                streams.append(
                    MediaStream(
                        index=index,
                        kind=STREAM_KINDS.get(
                            str(raw_stream.get("codec_type")),
                            StreamKind.UNKNOWN,
                        ),
                        codec_name=str(raw_stream.get("codec_name") or "unknown"),
                        language=normalize_language_code(tags.get("language")),
                        title=(
                            str(tags["title"])
                            if tags.get("title") is not None
                            else None
                        ),
                        is_default="default" in dispositions,
                        dispositions=dispositions,
                        metadata=_metadata(tags),
                        properties=_scalar_properties(raw_stream),
                    )
                )
            except ValueError as exc:
                raise MediaInspectionError(f"Invalid FFprobe stream: {exc}") from exc
        return tuple(streams)

    def _chapters(self, raw_chapters: Any) -> tuple[MediaChapter, ...]:
        if not isinstance(raw_chapters, list):
            raise MediaInspectionError("FFprobe chapters must be a list")

        chapters: list[MediaChapter] = []
        for position, raw_chapter in enumerate(raw_chapters):
            if not isinstance(raw_chapter, dict):
                raise MediaInspectionError("FFprobe returned an invalid chapter")
            start = _parse_float(raw_chapter.get("start_time"), "chapter start")
            end = _parse_float(raw_chapter.get("end_time"), "chapter end")
            if start is None or end is None:
                raise MediaInspectionError("FFprobe chapter is missing its time range")
            tags = raw_chapter.get("tags") or {}
            if not isinstance(tags, dict):
                tags = {}
            try:
                chapter_index = int(raw_chapter.get("id", position))
            except (TypeError, ValueError) as exc:
                raise MediaInspectionError("FFprobe returned an invalid chapter id") from exc
            try:
                chapters.append(
                    MediaChapter(
                        index=chapter_index,
                        start_seconds=start,
                        end_seconds=end,
                        title=(
                            str(tags["title"])
                            if tags.get("title") is not None
                            else None
                        ),
                        metadata=_metadata(tags),
                    )
                )
            except ValueError as exc:
                raise MediaInspectionError(f"Invalid FFprobe chapter: {exc}") from exc
        return tuple(chapters)
