"""Plan-gated transcription with resumable, validated staging output."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from pathlib import Path
import re
from uuid import uuid4

from .errors import (
    GeneratedSubtitleError,
    StagingCollisionError,
    SubtitleBridgeError,
    TranscriptionError,
)
from .languages import normalize_trusted_language
from .models import (
    ArtifactState,
    BatchPlan,
    MediaStream,
    PipelineStage,
    SpeechTranscript,
    StageAction,
    StreamKind,
    SubtitleArtifact,
    SubtitleOrigin,
)
from .paths import WorkspacePaths
from .ports import (
    AudioExtractor,
    SpeechRecognizer,
    SubtitleTranscriber,
    SubtitleValidator,
)


TemporaryAudioFactory = Callable[[Path], Path]


def _default_temporary_audio(target: Path) -> Path:
    return target.with_name(f".{target.stem}.audio-{uuid4().hex}.wav")


def _format_timestamp(seconds: float) -> str:
    milliseconds = round(seconds * 1000)
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    whole_seconds, milliseconds = divmod(remainder, 1_000)
    return f"{hours:02d}:{minutes:02d}:{whole_seconds:02d},{milliseconds:03d}"


def render_srt(transcript: SpeechTranscript) -> str:
    blocks = []
    for index, segment in enumerate(transcript.segments, start=1):
        text = segment.text.replace("\r\n", "\n").replace("\r", "\n").strip()
        blocks.append(
            "\n".join(
                (
                    str(index),
                    (
                        f"{_format_timestamp(segment.start_seconds)} --> "
                        f"{_format_timestamp(segment.end_seconds)}"
                    ),
                    text,
                )
            )
        )
    return "\n\n".join(blocks) + ("\n" if blocks else "")


class StagedSubtitleTranscriber:
    def __init__(
        self,
        extractor: AudioExtractor,
        recognizer: SpeechRecognizer,
        validator: SubtitleValidator,
        *,
        temporary_audio_factory: TemporaryAudioFactory = _default_temporary_audio,
    ) -> None:
        self.extractor = extractor
        self.recognizer = recognizer
        self.validator = validator
        self.temporary_audio_factory = temporary_audio_factory

    def transcribe(
        self,
        source: Path,
        audio_stream: MediaStream,
        destination: Path,
    ) -> SubtitleArtifact:
        if audio_stream.kind is not StreamKind.AUDIO:
            raise TranscriptionError(
                f"Stream #{audio_stream.index} is not an audio stream"
            )
        if destination.suffix.casefold() != ".srt":
            raise TranscriptionError(
                f"Generated subtitle destination must use .srt: {destination}"
            )

        existing = self._existing_candidate(destination)
        if existing is not None:
            return existing

        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise TranscriptionError(
                f"Cannot create staging directory {destination.parent}: {exc}"
            ) from exc

        temporary_audio = self.temporary_audio_factory(destination)
        self._validate_temporary_audio(source, destination, temporary_audio)
        if temporary_audio.exists():
            raise StagingCollisionError(
                f"Temporary audio path already exists: {temporary_audio}"
            )

        created_subtitle: Path | None = None
        subtitle_created = False
        try:
            self.extractor.extract(source, audio_stream, temporary_audio)
            transcript = self.recognizer.transcribe(temporary_audio)
            language = normalize_trusted_language(transcript.language)
            created_subtitle = destination.with_name(
                f"{destination.stem}.{language}.srt"
            )
            if created_subtitle.exists():
                raise StagingCollisionError(
                    f"Generated subtitle already exists: {created_subtitle}"
                )

            content = render_srt(transcript)
            try:
                with created_subtitle.open(
                    "x", encoding="utf-8", newline="\n"
                ) as output:
                    subtitle_created = True
                    output.write(content)
            except FileExistsError as exc:
                raise StagingCollisionError(
                    f"Generated subtitle already exists: {created_subtitle}"
                ) from exc
            except OSError as exc:
                raise TranscriptionError(
                    f"Cannot write generated subtitle {created_subtitle}: {exc}"
                ) from exc

            validation = self.validator.validate(created_subtitle)
            if not validation.is_valid:
                raise GeneratedSubtitleError(
                    f"Generated subtitle is invalid: {validation.error}"
                )
            artifact = SubtitleArtifact(
                origin=SubtitleOrigin.GENERATED,
                state=ArtifactState.VALID,
                language=language,
                title=f"Whisper transcription ({language})",
                path=created_subtitle,
                validation=validation,
            )
        except Exception as exc:
            created_paths = [temporary_audio]
            if subtitle_created and created_subtitle is not None:
                created_paths.append(created_subtitle)
            cleanup_errors = self._remove_created_paths(created_paths)
            if cleanup_errors:
                raise TranscriptionError(
                    f"{exc}; staging cleanup also failed: {cleanup_errors}"
                ) from exc
            if isinstance(exc, SubtitleBridgeError):
                raise
            raise TranscriptionError(f"Transcription failed: {exc}") from exc

        cleanup_errors = self._remove_created_paths((temporary_audio,))
        if cleanup_errors:
            raise TranscriptionError(
                "Generated subtitle is valid, but temporary audio cleanup failed: "
                f"{cleanup_errors}"
            )
        return artifact

    def _existing_candidate(self, destination: Path) -> SubtitleArtifact | None:
        candidates = []
        if destination.exists():
            candidates.append(destination)
        candidates.extend(destination.parent.glob(f"{destination.stem}.*.srt"))
        unique_candidates = tuple(
            sorted(
                {candidate.resolve() for candidate in candidates},
                key=lambda path: str(path).casefold(),
            )
        )
        if not unique_candidates:
            return None
        staging_parent = destination.parent.resolve()
        if any(
            candidate.parent != staging_parent for candidate in unique_candidates
        ):
            raise StagingCollisionError(
                "Generated subtitle candidate resolves outside staging"
            )
        if len(unique_candidates) > 1:
            names = ", ".join(path.name for path in unique_candidates)
            raise StagingCollisionError(
                f"Multiple generated subtitle candidates exist: {names}"
            )

        candidate = unique_candidates[0]
        validation = self.validator.validate(candidate)
        if not validation.is_valid:
            raise StagingCollisionError(
                f"Existing generated subtitle is invalid: {candidate}: "
                f"{validation.error}"
            )
        language = self._candidate_language(candidate, destination)
        return SubtitleArtifact(
            origin=SubtitleOrigin.GENERATED,
            state=ArtifactState.VALID,
            language=language,
            title=f"Whisper transcription ({language}, resumed)",
            path=candidate,
            validation=validation,
        )

    @staticmethod
    def _candidate_language(candidate: Path, destination: Path) -> str:
        if candidate.name == destination.name:
            return "und"
        prefix = f"{destination.stem}."
        suffix = candidate.stem.removeprefix(prefix)
        if re.fullmatch(r"[a-zA-Z]{2,3}", suffix) is None:
            raise StagingCollisionError(
                f"Generated subtitle has no trusted language suffix: {candidate}"
            )
        return normalize_trusted_language(suffix)

    @staticmethod
    def _validate_temporary_audio(
        source: Path,
        destination: Path,
        temporary_audio: Path,
    ) -> None:
        staging_parent = destination.parent.resolve()
        if temporary_audio.parent.resolve() != staging_parent:
            raise TranscriptionError(
                "Temporary audio must be created inside the staging directory"
            )
        if temporary_audio.suffix.casefold() != ".wav":
            raise TranscriptionError("Temporary audio must use the .wav extension")
        if temporary_audio.resolve() in {source.resolve(), destination.resolve()}:
            raise TranscriptionError("Temporary audio path conflicts with an input path")

    @staticmethod
    def _remove_created_paths(paths: Iterable[Path]) -> str | None:
        errors = []
        for path in paths:
            try:
                path.unlink(missing_ok=True)
            except OSError as exc:
                errors.append(f"{path}: {exc}")
        return "; ".join(errors) or None


class TranscriptionStage:
    def __init__(self, transcriber: SubtitleTranscriber) -> None:
        self.transcriber = transcriber

    def execute(
        self,
        batch_plan: BatchPlan,
        source: Path,
        paths: WorkspacePaths,
    ) -> SubtitleArtifact | None:
        if not batch_plan.is_executable:
            raise TranscriptionError(
                "Transcription batch is not executable until all issues are resolved"
            )
        try:
            plan = batch_plan.plan_for(source)
        except KeyError as exc:
            raise TranscriptionError(f"No video plan exists for {source}") from exc
        try:
            decision = plan.decision_for(PipelineStage.TRANSCRIBE)
        except KeyError as exc:
            raise TranscriptionError("Plan has no transcription decision") from exc

        if decision.action is StageAction.SKIP:
            return None
        if decision.action is StageAction.NEEDS_INPUT or not plan.is_executable:
            raise TranscriptionError(
                f"Transcription plan is not executable: {decision.reason}"
            )
        if plan.inventory.has_valid_subtitles:
            raise TranscriptionError(
                "Refusing to invoke Whisper because a valid subtitle already exists"
            )
        if plan.transcription_audio_index is None:
            raise TranscriptionError("Plan does not select an audio stream")

        audio_stream = next(
            (
                stream
                for stream in plan.inventory.audio_streams
                if stream.index == plan.transcription_audio_index
            ),
            None,
        )
        if audio_stream is None:
            raise TranscriptionError(
                f"Selected audio stream is missing: #{plan.transcription_audio_index}"
            )

        staging_directory = paths.staging_directory
        if staging_directory.is_symlink() or (
            staging_directory.exists() and not staging_directory.is_dir()
        ):
            raise StagingCollisionError(
                f"Staging path is not a safe directory: {staging_directory}"
            )
        destination = paths.generated_subtitle_target(plan.inventory.source)
        artifact = self.transcriber.transcribe(
            plan.inventory.source,
            audio_stream,
            destination,
        )
        if artifact.origin is not SubtitleOrigin.GENERATED:
            raise TranscriptionError("Transcriber returned a non-generated subtitle")
        if artifact.state is not ArtifactState.VALID:
            raise TranscriptionError("Transcriber returned an invalid subtitle")
        if (
            artifact.path is None
            or artifact.path.resolve().parent != paths.staging_directory.resolve()
        ):
            raise TranscriptionError("Generated subtitle is outside staging")
        if not artifact.path.is_file() or artifact.path.stat().st_size == 0:
            raise TranscriptionError("Generated subtitle is missing or empty")
        if artifact.validation is None or not artifact.validation.is_valid:
            raise TranscriptionError("Generated subtitle was not validated")
        return artifact
