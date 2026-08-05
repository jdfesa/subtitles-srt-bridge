"""Immutable domain models shared by the application and its adapters."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class StreamKind(str, Enum):
    VIDEO = "video"
    AUDIO = "audio"
    SUBTITLE = "subtitle"
    ATTACHMENT = "attachment"
    DATA = "data"
    UNKNOWN = "unknown"


class SubtitleOrigin(str, Enum):
    EXTERNAL = "external"
    EMBEDDED = "embedded"
    GENERATED = "generated"


class ArtifactState(str, Enum):
    VALID = "valid"
    INVALID = "invalid"
    AMBIGUOUS = "ambiguous"


class PipelineStage(str, Enum):
    INSPECT = "inspect"
    PLAN = "plan"
    TRANSCRIBE = "transcribe"
    MUX = "mux"
    VERIFY = "verify"
    PUBLISH = "publish"
    ARCHIVE = "archive"


class StageAction(str, Enum):
    RUN = "run"
    SKIP = "skip"
    NEEDS_INPUT = "needs-input"


class ResultStatus(str, Enum):
    COMPLETED = "completed"
    SKIPPED = "skipped"
    NEEDS_INPUT = "needs-input"
    PARTIAL = "partial"
    FAILED = "failed"


class DiscoveryIssueKind(str, Enum):
    AMBIGUOUS_SUBTITLE = "ambiguous-subtitle"
    UNASSOCIATED_SUBTITLE = "unassociated-subtitle"
    INSPECTION_FAILED = "inspection-failed"


@dataclass(frozen=True, slots=True)
class MediaStream:
    index: int
    kind: StreamKind
    codec_name: str
    language: str = "und"
    title: str | None = None
    is_default: bool = False
    dispositions: frozenset[str] = frozenset()
    metadata: tuple[tuple[str, str], ...] = ()
    properties: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        if self.index < 0:
            raise ValueError("Stream index cannot be negative")
        if not self.codec_name.strip():
            raise ValueError("Stream codec cannot be empty")
        if not self.language.strip():
            raise ValueError("Stream language cannot be empty; use 'und'")


@dataclass(frozen=True, slots=True)
class MediaChapter:
    index: int
    start_seconds: float
    end_seconds: float
    title: str | None = None
    metadata: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        if self.index < 0:
            raise ValueError("Chapter index cannot be negative")
        if self.start_seconds < 0:
            raise ValueError("Chapter start cannot be negative")
        if self.end_seconds < self.start_seconds:
            raise ValueError("Chapter end cannot precede its start")


@dataclass(frozen=True, slots=True)
class MediaInspection:
    streams: tuple[MediaStream, ...]
    format_name: str | None = None
    duration_seconds: float | None = None
    chapters: tuple[MediaChapter, ...] = ()
    metadata: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        indices = [stream.index for stream in self.streams]
        if len(indices) != len(set(indices)):
            raise ValueError("Stream indices must be unique within an inspection")
        if self.duration_seconds is not None and self.duration_seconds < 0:
            raise ValueError("Media duration cannot be negative")


@dataclass(frozen=True, slots=True)
class SubtitleValidation:
    is_valid: bool
    cue_count: int
    encoding: str | None = None
    error: str | None = None

    def __post_init__(self) -> None:
        if self.cue_count < 0:
            raise ValueError("Subtitle cue count cannot be negative")
        if self.is_valid and self.cue_count == 0:
            raise ValueError("A valid subtitle must contain at least one cue")
        if self.is_valid and self.error is not None:
            raise ValueError("A valid subtitle cannot contain a validation error")
        if not self.is_valid and not self.error:
            raise ValueError("An invalid subtitle requires a validation error")


@dataclass(frozen=True, slots=True)
class SubtitleArtifact:
    origin: SubtitleOrigin
    state: ArtifactState
    language: str = "und"
    title: str | None = None
    path: Path | None = None
    stream_index: int | None = None
    validation: SubtitleValidation | None = None
    message: str | None = None

    def __post_init__(self) -> None:
        if not self.language.strip():
            raise ValueError("Subtitle language cannot be empty; use 'und'")

        if self.origin is SubtitleOrigin.EMBEDDED:
            if self.stream_index is None or self.stream_index < 0:
                raise ValueError("Embedded subtitles require a non-negative stream index")
            if self.path is not None:
                raise ValueError("Embedded subtitles cannot reference an external path")
            return

        if self.path is None:
            raise ValueError("External and generated subtitles require a path")
        if self.stream_index is not None:
            raise ValueError("External and generated subtitles cannot use a stream index")
        if self.validation is not None:
            if self.state is ArtifactState.VALID and not self.validation.is_valid:
                raise ValueError("Subtitle state must match its validation result")
            if self.state is ArtifactState.INVALID and self.validation.is_valid:
                raise ValueError("Subtitle state must match its validation result")


@dataclass(frozen=True, slots=True)
class VideoInventory:
    source: Path
    streams: tuple[MediaStream, ...] = ()
    subtitles: tuple[SubtitleArtifact, ...] = ()
    existing_output: Path | None = None
    format_name: str | None = None
    duration_seconds: float | None = None
    chapters: tuple[MediaChapter, ...] = ()
    metadata: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        indices = [stream.index for stream in self.streams]
        if len(indices) != len(set(indices)):
            raise ValueError("Stream indices must be unique within an inventory")

    @property
    def video_streams(self) -> tuple[MediaStream, ...]:
        return tuple(stream for stream in self.streams if stream.kind is StreamKind.VIDEO)

    @property
    def audio_streams(self) -> tuple[MediaStream, ...]:
        return tuple(stream for stream in self.streams if stream.kind is StreamKind.AUDIO)

    @property
    def embedded_subtitles(self) -> tuple[SubtitleArtifact, ...]:
        return tuple(
            subtitle
            for subtitle in self.subtitles
            if subtitle.origin is SubtitleOrigin.EMBEDDED
        )

    @property
    def valid_subtitles(self) -> tuple[SubtitleArtifact, ...]:
        return tuple(
            subtitle
            for subtitle in self.subtitles
            if subtitle.state is ArtifactState.VALID
        )

    @property
    def has_valid_subtitles(self) -> bool:
        return bool(self.valid_subtitles)


@dataclass(frozen=True, slots=True)
class PlanDecision:
    stage: PipelineStage
    action: StageAction
    reason: str

    def __post_init__(self) -> None:
        if not self.reason.strip():
            raise ValueError("Plan decisions require a reason")


@dataclass(frozen=True, slots=True)
class VideoPlan:
    inventory: VideoInventory
    output_path: Path
    trash_path: Path
    decisions: tuple[PlanDecision, ...]

    def __post_init__(self) -> None:
        stages = [decision.stage for decision in self.decisions]
        if len(stages) != len(set(stages)):
            raise ValueError("Each pipeline stage can appear only once in a plan")

    def decision_for(self, stage: PipelineStage) -> PlanDecision:
        for decision in self.decisions:
            if decision.stage is stage:
                return decision
        raise KeyError(stage)


@dataclass(frozen=True, slots=True)
class VideoResult:
    source: Path
    status: ResultStatus
    message: str = ""
    output_path: Path | None = None


@dataclass(frozen=True, slots=True)
class DiscoveryIssue:
    kind: DiscoveryIssueKind
    path: Path
    message: str
    candidate_videos: tuple[Path, ...] = ()

    def __post_init__(self) -> None:
        if not self.message.strip():
            raise ValueError("Discovery issues require a message")


@dataclass(frozen=True, slots=True)
class DiscoveryResult:
    inventories: tuple[VideoInventory, ...]
    issues: tuple[DiscoveryIssue, ...] = ()

    def inventory_for(self, source: Path) -> VideoInventory:
        resolved_source = source.resolve()
        for inventory in self.inventories:
            if inventory.source.resolve() == resolved_source:
                return inventory
        raise KeyError(source)
