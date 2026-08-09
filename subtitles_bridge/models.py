"""Immutable domain models shared by the application and its adapters."""

from __future__ import annotations

import math
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
class SpeechSegment:
    start_seconds: float
    end_seconds: float
    text: str

    def __post_init__(self) -> None:
        if not math.isfinite(self.start_seconds) or not math.isfinite(self.end_seconds):
            raise ValueError("Speech segment timestamps must be finite")
        if self.start_seconds < 0:
            raise ValueError("Speech segment start cannot be negative")
        if self.end_seconds < self.start_seconds:
            raise ValueError("Speech segment end cannot precede its start")
        if not self.text.strip():
            raise ValueError("Speech segment text cannot be empty")


@dataclass(frozen=True, slots=True)
class SpeechTranscript:
    language: str
    segments: tuple[SpeechSegment, ...]

    def __post_init__(self) -> None:
        if not self.language.strip():
            raise ValueError("Transcript language cannot be empty; use 'und'")


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
    content_sha256: str | None = None

    def __post_init__(self) -> None:
        if not self.language.strip():
            raise ValueError("Subtitle language cannot be empty; use 'und'")
        if self.content_sha256 is not None and (
            len(self.content_sha256) != 64
            or any(
                character not in "0123456789abcdef" for character in self.content_sha256
            )
        ):
            raise ValueError(
                "Subtitle SHA-256 must be 64 lowercase hexadecimal characters"
            )

        if self.origin is SubtitleOrigin.EMBEDDED:
            if self.stream_index is None or self.stream_index < 0:
                raise ValueError(
                    "Embedded subtitles require a non-negative stream index"
                )
            if self.path is not None:
                raise ValueError("Embedded subtitles cannot reference an external path")
            if self.content_sha256 is not None:
                raise ValueError("Embedded subtitles cannot use a sidecar SHA-256")
            return

        if self.path is None:
            raise ValueError("External and generated subtitles require a path")
        if self.stream_index is not None:
            raise ValueError(
                "External and generated subtitles cannot use a stream index"
            )
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
    existing_trash: Path | None = None
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
        return tuple(
            stream for stream in self.streams if stream.kind is StreamKind.VIDEO
        )

    @property
    def audio_streams(self) -> tuple[MediaStream, ...]:
        return tuple(
            stream for stream in self.streams if stream.kind is StreamKind.AUDIO
        )

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
class VerifiedOutput:
    source: Path
    staged_path: Path
    inspection: MediaInspection
    expected_subtitles: tuple[SubtitleArtifact, ...]
    size_bytes: int
    modified_time_ns: int

    def __post_init__(self) -> None:
        if self.source.resolve() == self.staged_path.resolve():
            raise ValueError("Verified output cannot replace its source")
        if self.staged_path.suffix.casefold() != ".mkv":
            raise ValueError("Verified output must use the .mkv extension")
        if self.size_bytes <= 0:
            raise ValueError("Verified output size must be positive")
        if self.modified_time_ns < 0:
            raise ValueError("Verified output mtime cannot be negative")
        if not any(
            stream.kind is StreamKind.VIDEO for stream in self.inspection.streams
        ):
            raise ValueError("Verified output must contain a video stream")
        if any(
            subtitle.state is not ArtifactState.VALID
            for subtitle in self.expected_subtitles
        ):
            raise ValueError("Verified output can reference only valid subtitles")


@dataclass(frozen=True, slots=True)
class PublishedOutput:
    source: Path
    final_path: Path
    inspection: MediaInspection
    expected_subtitles: tuple[SubtitleArtifact, ...]
    size_bytes: int
    modified_time_ns: int

    def __post_init__(self) -> None:
        if self.source.resolve() == self.final_path.resolve():
            raise ValueError("Published output cannot replace its source")
        if self.final_path.suffix.casefold() != ".mkv":
            raise ValueError("Published output must use the .mkv extension")
        if self.size_bytes <= 0:
            raise ValueError("Published output size must be positive")
        if self.modified_time_ns < 0:
            raise ValueError("Published output mtime cannot be negative")
        if not any(
            stream.kind is StreamKind.VIDEO for stream in self.inspection.streams
        ):
            raise ValueError("Published output must contain a video stream")
        if any(
            subtitle.state is not ArtifactState.VALID
            for subtitle in self.expected_subtitles
        ):
            raise ValueError("Published output can reference only valid subtitles")


@dataclass(frozen=True, slots=True)
class ArchivedInputs:
    source: Path
    destination: Path
    original_paths: tuple[Path, ...]
    archived_paths: tuple[Path, ...]

    def __post_init__(self) -> None:
        if not self.original_paths:
            raise ValueError("Archived inputs require at least the source")
        if self.original_paths[0].resolve() != self.source.resolve():
            raise ValueError("Archived inputs must list the source first")
        if len(self.original_paths) != len(self.archived_paths):
            raise ValueError("Archived input and destination counts must match")
        original_keys = [str(path.resolve()).casefold() for path in self.original_paths]
        archived_keys = [str(path.resolve()).casefold() for path in self.archived_paths]
        if len(original_keys) != len(set(original_keys)):
            raise ValueError("Archived inputs cannot contain duplicate sources")
        if len(archived_keys) != len(set(archived_keys)):
            raise ValueError("Archived inputs cannot contain duplicate destinations")
        destination = self.destination.resolve()
        for original, archived in zip(
            self.original_paths,
            self.archived_paths,
            strict=True,
        ):
            if archived.resolve().parent != destination:
                raise ValueError("Archived files must be inside the destination")
            if archived.name != original.name:
                raise ValueError("Archived files must preserve their names")


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
    selected_subtitles: tuple[SubtitleArtifact, ...] = ()
    transcription_audio_index: int | None = None
    uses_verified_output: bool = False

    def __post_init__(self) -> None:
        stages = [decision.stage for decision in self.decisions]
        if len(stages) != len(set(stages)):
            raise ValueError("Each pipeline stage can appear only once in a plan")
        if any(
            subtitle.state is not ArtifactState.VALID
            for subtitle in self.selected_subtitles
        ):
            raise ValueError("A plan can select only valid subtitles")

        transcribe = next(
            (
                decision
                for decision in self.decisions
                if decision.stage is PipelineStage.TRANSCRIBE
            ),
            None,
        )
        if transcribe is not None and transcribe.action is StageAction.RUN:
            if self.transcription_audio_index is None:
                raise ValueError("A transcription plan requires an audio stream")
            audio_indices = {stream.index for stream in self.inventory.audio_streams}
            if self.transcription_audio_index not in audio_indices:
                raise ValueError("Transcription audio must belong to the inventory")
        elif self.transcription_audio_index is not None:
            raise ValueError("A skipped or blocked transcription cannot select audio")

        if self.uses_verified_output and self.inventory.existing_output is None:
            raise ValueError("A verified output plan requires an existing output")

    def decision_for(self, stage: PipelineStage) -> PlanDecision:
        for decision in self.decisions:
            if decision.stage is stage:
                return decision
        raise KeyError(stage)

    @property
    def has_needs_input(self) -> bool:
        return any(
            decision.action is StageAction.NEEDS_INPUT for decision in self.decisions
        )

    @property
    def is_executable(self) -> bool:
        return not self.has_needs_input


@dataclass(frozen=True, slots=True)
class PlanningChoice:
    source: Path
    audio_stream_index: int | None = None
    verified_output: Path | None = None

    def __post_init__(self) -> None:
        if self.audio_stream_index is not None and self.audio_stream_index < 0:
            raise ValueError("Selected audio stream cannot be negative")


@dataclass(frozen=True, slots=True)
class FailureDetail:
    error_type: str
    message: str
    target_path: Path | None = None
    stream_index: int | None = None

    def __post_init__(self) -> None:
        if not self.error_type.strip():
            raise ValueError("Failure details require an error type")
        if not self.message.strip():
            raise ValueError("Failure details require a message")
        if self.stream_index is not None and self.stream_index < 0:
            raise ValueError("Failure stream index cannot be negative")


@dataclass(frozen=True, slots=True)
class StageResult:
    stage: PipelineStage
    status: ResultStatus
    message: str
    duration_seconds: float | None = None
    failure: FailureDetail | None = None

    def __post_init__(self) -> None:
        if self.status is ResultStatus.PARTIAL:
            raise ValueError("A single stage cannot have partial status")
        if not self.message.strip():
            raise ValueError("Stage results require a message")
        if self.duration_seconds is not None and (
            not math.isfinite(self.duration_seconds) or self.duration_seconds < 0
        ):
            raise ValueError("Stage duration must be finite and non-negative")
        if self.failure is not None and self.status is not ResultStatus.FAILED:
            raise ValueError("Only a failed stage can carry failure details")


@dataclass(frozen=True, slots=True)
class VideoResult:
    source: Path
    status: ResultStatus
    message: str = ""
    output_path: Path | None = None
    trash_path: Path | None = None
    stages: tuple[StageResult, ...] = ()

    def __post_init__(self) -> None:
        stage_names = [stage.stage for stage in self.stages]
        if len(stage_names) != len(set(stage_names)):
            raise ValueError("A video result can contain each stage only once")
        if self.status is ResultStatus.PARTIAL and self.output_path is None:
            raise ValueError("A partial video result requires a published output")


@dataclass(frozen=True, slots=True)
class BatchResult:
    videos: tuple[VideoResult, ...]
    issues: tuple[DiscoveryIssue, ...] = ()
    message: str = ""

    def __post_init__(self) -> None:
        sources = [str(video.source.resolve()).casefold() for video in self.videos]
        if len(sources) != len(set(sources)):
            raise ValueError("Batch results cannot contain duplicate videos")

    @property
    def status(self) -> ResultStatus:
        statuses = {video.status for video in self.videos}
        if ResultStatus.FAILED in statuses:
            return ResultStatus.FAILED
        if ResultStatus.PARTIAL in statuses:
            return ResultStatus.PARTIAL
        if self.issues or ResultStatus.NEEDS_INPUT in statuses:
            return ResultStatus.NEEDS_INPUT
        if not self.videos:
            return ResultStatus.FAILED
        if statuses == {ResultStatus.SKIPPED}:
            return ResultStatus.SKIPPED
        return ResultStatus.COMPLETED

    @property
    def exit_code(self) -> int:
        return {
            ResultStatus.COMPLETED: 0,
            ResultStatus.SKIPPED: 0,
            ResultStatus.FAILED: 1,
            ResultStatus.NEEDS_INPUT: 2,
            ResultStatus.PARTIAL: 3,
        }[self.status]

    def count(self, status: ResultStatus) -> int:
        return sum(video.status is status for video in self.videos)


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


@dataclass(frozen=True, slots=True)
class BatchPlan:
    videos: tuple[VideoPlan, ...]
    issues: tuple[DiscoveryIssue, ...] = ()

    @property
    def has_needs_input(self) -> bool:
        return bool(self.issues) or any(plan.has_needs_input for plan in self.videos)

    @property
    def is_executable(self) -> bool:
        return not self.has_needs_input

    def plan_for(self, source: Path) -> VideoPlan:
        resolved_source = source.resolve()
        for plan in self.videos:
            if plan.inventory.source.resolve() == resolved_source:
                return plan
        raise KeyError(source)
