"""Read-only workspace discovery and conservative subtitle association."""

from __future__ import annotations

from pathlib import Path

from .errors import SubtitleBridgeError
from .languages import infer_subtitle_metadata, is_subtitle_metadata_token
from .models import (
    ArtifactState,
    DiscoveryIssue,
    DiscoveryIssueKind,
    DiscoveryResult,
    StreamKind,
    SubtitleArtifact,
    SubtitleOrigin,
    VideoInventory,
)
from .paths import VIDEO_EXTENSIONS, WorkspacePaths
from .ports import MediaProbe, SubtitleValidator


FIXED_SUBTITLE_DIRECTORIES = frozenset({"sub", "subs", "subtitles"})


def discover_video_paths(paths: WorkspacePaths) -> tuple[Path, ...]:
    return tuple(
        sorted(
            (
                entry.resolve()
                for entry in paths.root.iterdir()
                if entry.is_file() and entry.suffix.lower() in VIDEO_EXTENSIONS
            ),
            key=lambda path: path.name.casefold(),
        )
    )


def _recognized_subtitle_directory(path: Path) -> bool:
    folded_name = path.name.casefold()
    return (
        path.is_dir()
        and (
            folded_name in FIXED_SUBTITLE_DIRECTORIES
            or (folded_name.startswith("sub_") and len(folded_name) > 4)
        )
    )


def discover_subtitle_paths(paths: WorkspacePaths) -> tuple[Path, ...]:
    candidates = [
        entry.resolve()
        for entry in paths.root.iterdir()
        if entry.is_file() and entry.suffix.lower() == ".srt"
    ]
    for directory in paths.root.iterdir():
        if not _recognized_subtitle_directory(directory):
            continue
        candidates.extend(
            entry.resolve()
            for entry in directory.iterdir()
            if entry.is_file() and entry.suffix.lower() == ".srt"
        )
    return tuple(sorted(set(candidates), key=lambda path: str(path).casefold()))


def _matches_video(subtitle: Path, video: Path) -> bool:
    subtitle_stem = subtitle.stem.casefold()
    video_stem = video.stem.casefold()
    if subtitle_stem == video_stem:
        return True
    if not subtitle_stem.startswith(video_stem):
        return False
    suffix = subtitle_stem[len(video_stem) :]
    if not suffix or suffix[0] not in "._-":
        return False
    first_token = suffix.lstrip("._-").split(".", 1)[0]
    first_token = first_token.split("_", 1)[0].split("-", 1)[0]
    return is_subtitle_metadata_token(first_token)


class WorkspaceDiscovery:
    def __init__(self, probe: MediaProbe, validator: SubtitleValidator) -> None:
        self.probe = probe
        self.validator = validator

    def inspect(self, paths: WorkspacePaths) -> DiscoveryResult:
        videos = discover_video_paths(paths)
        sidecars = discover_subtitle_paths(paths)
        associated: dict[Path, list[SubtitleArtifact]] = {video: [] for video in videos}
        issues: list[DiscoveryIssue] = []

        for sidecar in sidecars:
            candidates = tuple(video for video in videos if _matches_video(sidecar, video))
            if not candidates:
                issues.append(
                    DiscoveryIssue(
                        DiscoveryIssueKind.UNASSOCIATED_SUBTITLE,
                        sidecar,
                        f"No video matches subtitle: {sidecar.name}",
                    )
                )
                continue
            if len(candidates) > 1:
                issues.append(
                    DiscoveryIssue(
                        DiscoveryIssueKind.AMBIGUOUS_SUBTITLE,
                        sidecar,
                        f"Subtitle matches multiple videos: {sidecar.name}",
                        candidates,
                    )
                )
                continue

            video = candidates[0]
            validation = self.validator.validate(sidecar)
            metadata = infer_subtitle_metadata(
                sidecar,
                video.stem,
                sidecar.parent.name if sidecar.parent != paths.root else None,
            )
            if not validation.is_valid:
                state = ArtifactState.INVALID
                message = validation.error
            elif metadata.conflict is not None:
                state = ArtifactState.AMBIGUOUS
                message = metadata.conflict
            else:
                state = ArtifactState.VALID
                message = None
            associated[video].append(
                SubtitleArtifact(
                    origin=SubtitleOrigin.EXTERNAL,
                    state=state,
                    language=metadata.language,
                    title=metadata.title,
                    path=sidecar,
                    validation=validation,
                    message=message,
                )
            )

        inventories: list[VideoInventory] = []
        for video in videos:
            try:
                inspection = self.probe.inspect(video)
            except SubtitleBridgeError as exc:
                issues.append(
                    DiscoveryIssue(
                        DiscoveryIssueKind.INSPECTION_FAILED,
                        video,
                        str(exc),
                    )
                )
                continue

            embedded = tuple(
                SubtitleArtifact(
                    origin=SubtitleOrigin.EMBEDDED,
                    state=ArtifactState.VALID,
                    language=stream.language,
                    title=stream.title,
                    stream_index=stream.index,
                )
                for stream in inspection.streams
                if stream.kind is StreamKind.SUBTITLE
            )
            external = tuple(
                sorted(
                    associated[video],
                    key=lambda subtitle: str(subtitle.path).casefold(),
                )
            )
            output_path = paths.output_for(video)
            trash_path = paths.trash_for(video)
            inventories.append(
                VideoInventory(
                    source=video,
                    streams=inspection.streams,
                    subtitles=embedded + external,
                    existing_output=output_path if output_path.exists() else None,
                    existing_trash=trash_path if trash_path.exists() else None,
                    format_name=inspection.format_name,
                    duration_seconds=inspection.duration_seconds,
                    chapters=inspection.chapters,
                    metadata=inspection.metadata,
                )
            )

        return DiscoveryResult(tuple(inventories), tuple(issues))
