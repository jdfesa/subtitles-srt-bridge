"""Copy-only FFmpeg adapter for building a staged Matroska file."""

from __future__ import annotations

import os
import subprocess
from collections.abc import Callable, Sequence
from pathlib import Path
from uuid import uuid4

from ..errors import MuxingCollisionError, MuxingError, SubtitleIntegrityError
from ..integrity import SUBTITLE_SHA256_METADATA_KEY, subtitle_sha256
from ..models import (
    ArtifactState,
    StreamKind,
    SubtitleArtifact,
    SubtitleOrigin,
    VideoInventory,
)

Runner = Callable[..., subprocess.CompletedProcess[str]]
TemporaryOutputFactory = Callable[[Path], Path]


def _temporary_output(destination: Path) -> Path:
    return destination.with_name(f".{destination.stem}.mux-{uuid4().hex}.mkv")


def _sidecar_encoding(subtitle: SubtitleArtifact) -> str | None:
    if subtitle.validation is None or not subtitle.validation.is_valid:
        raise MuxingError(f"Subtitle was not validated: {subtitle.path}")
    encoding = (subtitle.validation.encoding or "").casefold()
    if encoding in {"utf-8", "utf-8-sig"}:
        return None
    if encoding == "utf-16":
        return "UTF-16"
    if encoding == "cp1252":
        return "CP1252"
    raise MuxingError(
        f"Subtitle uses an unsupported validated encoding: {subtitle.path}: "
        f"{subtitle.validation.encoding}"
    )


def _validated_sidecars(
    inventory: VideoInventory,
    subtitles: Sequence[SubtitleArtifact],
) -> tuple[SubtitleArtifact, ...]:
    source_subtitle_indices = {
        stream.index
        for stream in inventory.streams
        if stream.kind is StreamKind.SUBTITLE
    }
    sidecars: list[SubtitleArtifact] = []
    sidecar_keys: set[str] = set()
    for subtitle in subtitles:
        if subtitle.state is not ArtifactState.VALID:
            raise MuxingError("Muxing accepts only valid subtitle artifacts")
        if subtitle.origin is SubtitleOrigin.EMBEDDED:
            if subtitle.stream_index not in source_subtitle_indices:
                raise MuxingError(
                    "Embedded subtitle does not belong to a source subtitle stream: "
                    f"#{subtitle.stream_index}"
                )
            continue

        assert subtitle.path is not None
        if subtitle.path.suffix.casefold() != ".srt":
            raise MuxingError(f"Subtitle sidecar must use .srt: {subtitle.path}")
        _sidecar_encoding(subtitle)
        key = str(subtitle.path.resolve()).casefold()
        if key in sidecar_keys:
            raise MuxingError(f"Subtitle sidecar is duplicated: {subtitle.path}")
        sidecar_keys.add(key)
        sidecars.append(subtitle)
    return tuple(sidecars)


def build_ffmpeg_mux_command(
    inventory: VideoInventory,
    subtitles: Sequence[SubtitleArtifact],
    destination: Path,
    *,
    executable: str = "ffmpeg",
) -> list[str]:
    """Build a copy-only command; filesystem effects belong to the adapter."""

    if not executable.strip():
        raise ValueError("FFmpeg executable cannot be empty")
    if destination.suffix.casefold() != ".mkv":
        raise MuxingError(f"Staged output must use .mkv: {destination}")
    if not inventory.video_streams:
        raise MuxingError("Source inventory has no video stream")

    sidecars = _validated_sidecars(inventory, subtitles)
    command = [
        executable,
        "-v",
        "error",
        "-nostdin",
        "-n",
        "-copy_unknown",
        "-i",
        str(inventory.source),
    ]
    for subtitle in sidecars:
        encoding = _sidecar_encoding(subtitle)
        if encoding is not None:
            command.extend(("-sub_charenc", encoding))
        command.extend(("-i", str(subtitle.path)))

    command.extend(("-map", "0"))
    for input_index in range(1, len(sidecars) + 1):
        command.extend(("-map", f"{input_index}:0"))
    command.extend(("-map_metadata", "0", "-map_chapters", "0", "-c", "copy"))

    embedded_count = sum(
        stream.kind is StreamKind.SUBTITLE for stream in inventory.streams
    )
    for offset, subtitle in enumerate(sidecars):
        output_index = embedded_count + offset
        if subtitle.language.casefold() != "und":
            command.extend(
                (f"-metadata:s:s:{output_index}", f"language={subtitle.language}")
            )
        if subtitle.title is not None and subtitle.title.strip():
            command.extend((f"-metadata:s:s:{output_index}", f"title={subtitle.title}"))
        if subtitle.content_sha256 is not None:
            command.extend(
                (
                    f"-metadata:s:s:{output_index}",
                    f"{SUBTITLE_SHA256_METADATA_KEY}={subtitle.content_sha256}",
                )
            )

    for output_index in range(embedded_count + len(sidecars)):
        command.extend((f"-disposition:s:{output_index}", "-default"))
    command.extend(("-default_mode", "passthrough", "-f", "matroska", str(destination)))
    return command


class FFmpegMediaMuxer:
    def __init__(
        self,
        executable: str = "ffmpeg",
        runner: Runner = subprocess.run,
        *,
        temporary_output_factory: TemporaryOutputFactory = _temporary_output,
    ) -> None:
        self.executable = executable
        self.runner = runner
        self.temporary_output_factory = temporary_output_factory

    def mux(
        self,
        inventory: VideoInventory,
        subtitles: Sequence[SubtitleArtifact],
        destination: Path,
    ) -> None:
        self._validate_filesystem_inputs(inventory, subtitles, destination)
        working_output = self.temporary_output_factory(destination)
        self._validate_working_output(
            inventory,
            subtitles,
            destination,
            working_output,
        )

        try:
            destination.touch(exist_ok=False)
        except FileExistsError as exc:
            raise MuxingCollisionError(
                f"Staged output already exists: {destination}"
            ) from exc
        except OSError as exc:
            raise MuxingError(
                f"Cannot reserve staged output {destination}: {exc}"
            ) from exc

        try:
            command = build_ffmpeg_mux_command(
                inventory,
                subtitles,
                working_output,
                executable=self.executable,
            )
            result = self.runner(
                command,
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode != 0:
                message = (
                    result.stderr.strip() or "FFmpeg could not build the staged MKV"
                )
                raise MuxingError(message)
            if not working_output.is_file() or working_output.stat().st_size == 0:
                raise MuxingError(
                    f"FFmpeg did not create a usable staged MKV: {working_output}"
                )
            os.replace(working_output, destination)
        except OSError as exc:
            error = MuxingError(f"Cannot execute or finalize FFmpeg remux: {exc}")
            self._raise_after_cleanup(error, destination, working_output)
        except Exception as exc:
            error = exc if isinstance(exc, MuxingError) else MuxingError(str(exc))
            self._raise_after_cleanup(error, destination, working_output)

    @staticmethod
    def _validate_filesystem_inputs(
        inventory: VideoInventory,
        subtitles: Sequence[SubtitleArtifact],
        destination: Path,
    ) -> None:
        if not inventory.source.is_file():
            raise MuxingError(f"Source video is missing: {inventory.source}")
        if destination.exists() or destination.is_symlink():
            raise MuxingCollisionError(f"Staged output already exists: {destination}")
        if not destination.parent.is_dir():
            raise MuxingError(f"Staging directory does not exist: {destination.parent}")

        sidecars = _validated_sidecars(inventory, subtitles)
        protected_paths = {inventory.source.resolve(), destination.resolve()}
        for subtitle in sidecars:
            assert subtitle.path is not None
            try:
                if not subtitle.path.is_file() or subtitle.path.stat().st_size == 0:
                    raise MuxingError(
                        f"Subtitle sidecar is missing or empty: {subtitle.path}"
                    )
            except OSError as exc:
                raise MuxingError(
                    f"Cannot inspect subtitle sidecar {subtitle.path}: {exc}"
                ) from exc
            if subtitle.path.resolve() in protected_paths:
                raise MuxingError(
                    "Subtitle sidecar conflicts with a managed media path: "
                    f"{subtitle.path}"
                )
            try:
                current_sha256 = subtitle_sha256(subtitle.path)
            except SubtitleIntegrityError as exc:
                raise MuxingError(str(exc)) from exc
            if (
                subtitle.content_sha256 is not None
                and current_sha256 != subtitle.content_sha256
            ):
                raise MuxingError(
                    f"Subtitle sidecar changed after validation: {subtitle.path}"
                )

    @staticmethod
    def _validate_working_output(
        inventory: VideoInventory,
        subtitles: Sequence[SubtitleArtifact],
        destination: Path,
        working_output: Path,
    ) -> None:
        if working_output.parent.resolve() != destination.parent.resolve():
            raise MuxingError("Temporary MKV must be created inside staging")
        if working_output.suffix.casefold() != ".mkv":
            raise MuxingError("Temporary MKV must use the .mkv extension")
        if working_output.exists() or working_output.is_symlink():
            raise MuxingCollisionError(
                f"Temporary MKV already exists: {working_output}"
            )
        protected_paths = {inventory.source.resolve(), destination.resolve()}
        protected_paths.update(
            subtitle.path.resolve()
            for subtitle in subtitles
            if subtitle.path is not None
        )
        if working_output.resolve() in protected_paths:
            raise MuxingError("Temporary MKV conflicts with an input or output path")

    @staticmethod
    def _cleanup(paths: Sequence[Path]) -> str | None:
        errors = []
        for path in paths:
            try:
                path.unlink(missing_ok=True)
            except OSError as exc:
                errors.append(f"{path}: {exc}")
        return "; ".join(errors) or None

    @classmethod
    def _raise_after_cleanup(
        cls,
        error: MuxingError,
        destination: Path,
        working_output: Path,
    ) -> None:
        cleanup_error = cls._cleanup((working_output, destination))
        if cleanup_error is not None:
            raise MuxingError(
                f"{error}; staged MKV cleanup also failed: {cleanup_error}"
            ) from error
        raise error
