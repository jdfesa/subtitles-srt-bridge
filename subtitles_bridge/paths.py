"""Pure workspace path policy for non-recursive MP4/MKV processing."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .errors import InputPathError, SourceVideoError

VIDEO_EXTENSIONS = frozenset({".mp4", ".mkv"})


@dataclass(frozen=True, slots=True)
class WorkspacePaths:
    root: Path

    @classmethod
    def from_directory(cls, raw_path: str | Path) -> WorkspacePaths:
        candidate = Path(raw_path).expanduser()
        try:
            root = candidate.resolve(strict=True)
        except FileNotFoundError as exc:
            raise InputPathError(
                f"Input directory does not exist: {candidate}"
            ) from exc

        if not root.is_dir():
            raise InputPathError(f"Input path is not a directory: {root}")
        return cls(root=root)

    @property
    def output_directory(self) -> Path:
        return self.root / "output"

    @property
    def trash_directory(self) -> Path:
        return self.root / "trash"

    @property
    def staging_directory(self) -> Path:
        return self.root / "staging"

    def source_video(self, raw_path: str | Path) -> Path:
        candidate = Path(raw_path).expanduser()
        try:
            source = candidate.resolve(strict=True)
        except FileNotFoundError as exc:
            raise SourceVideoError(f"Source video does not exist: {candidate}") from exc

        if not source.is_file():
            raise SourceVideoError(f"Source video is not a file: {source}")
        if source.parent != self.root:
            raise SourceVideoError(
                f"Source video must be directly inside the input directory: {source}"
            )
        if source.suffix.lower() not in VIDEO_EXTENSIONS:
            raise SourceVideoError(f"Unsupported video extension: {source.suffix}")
        return source

    def output_for(self, raw_source: str | Path) -> Path:
        source = self.source_video(raw_source)
        return self.output_directory / f"{source.stem}.subtitled.mkv"

    def trash_for(self, raw_source: str | Path) -> Path:
        source = self.source_video(raw_source)
        return self.trash_directory / source.stem

    def generated_subtitle_target(self, raw_source: str | Path) -> Path:
        source = self.source_video(raw_source)
        return self.staging_directory / f"{source.stem}.generated.srt"

    def staged_output_for(self, raw_source: str | Path) -> Path:
        source = self.source_video(raw_source)
        return self.staging_directory / f"{source.stem}.subtitled.mkv"
