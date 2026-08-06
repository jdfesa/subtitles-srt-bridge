"""Contract verification for a staged copy-only MKV."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from pathlib import Path

from .errors import MuxingError, VerificationError
from .models import (
    ArtifactState,
    BatchPlan,
    MediaChapter,
    MediaInspection,
    MediaStream,
    PipelineStage,
    StageAction,
    StreamKind,
    SubtitleArtifact,
    SubtitleOrigin,
    VerifiedOutput,
    VideoInventory,
)
from .muxing import planned_subtitles_for
from .paths import WorkspacePaths
from .ports import MediaProbe, OutputVerifier


GLOBAL_VOLATILE_METADATA = frozenset(
    {
        "compatible_brands",
        "encoder",
        "major_brand",
        "minor_version",
    }
)
STREAM_VOLATILE_METADATA = frozenset(
    {
        "creation_time",
        "encoder",
        "handler_name",
        "language",
        "title",
        "vendor_id",
    }
)
CHAPTER_VOLATILE_METADATA = frozenset({"encoder"})


def _metadata_map(
    metadata: Iterable[tuple[str, str]],
) -> dict[str, str]:
    return {key.casefold(): value for key, value in metadata}


def _is_volatile_metadata(key: str, ignored: frozenset[str]) -> bool:
    folded = key.casefold()
    return (
        folded in ignored
        or folded.startswith("duration")
        or folded.startswith("statistics_")
        or folded.startswith("_statistics")
    )


def _require_metadata_subset(
    source_metadata: Iterable[tuple[str, str]],
    output_metadata: Iterable[tuple[str, str]],
    *,
    ignored: frozenset[str],
    label: str,
) -> None:
    output = _metadata_map(output_metadata)
    for key, value in _metadata_map(source_metadata).items():
        if _is_volatile_metadata(key, ignored):
            continue
        if output.get(key) != value:
            raise VerificationError(
                f"{label} metadata was not preserved: {key}={value!r}"
            )


class OutputContractVerifier:
    def __init__(
        self,
        probe: MediaProbe,
        *,
        duration_tolerance_seconds: float = 1.0,
        chapter_tolerance_seconds: float = 0.05,
    ) -> None:
        if duration_tolerance_seconds < 0:
            raise ValueError("Duration tolerance cannot be negative")
        if chapter_tolerance_seconds < 0:
            raise ValueError("Chapter tolerance cannot be negative")
        self.probe = probe
        self.duration_tolerance_seconds = duration_tolerance_seconds
        self.chapter_tolerance_seconds = chapter_tolerance_seconds

    def verify(
        self,
        inventory: VideoInventory,
        output: Path,
        expected_subtitles: Sequence[SubtitleArtifact],
    ) -> VerifiedOutput:
        before = self._snapshot(output)
        self._validate_expectations(inventory, expected_subtitles)
        try:
            inspection = self.probe.inspect(output)
        except Exception as exc:
            raise VerificationError(
                f"Cannot inspect staged MKV {output}: {exc}"
            ) from exc
        after = self._snapshot(output)
        if before != after:
            raise VerificationError(
                f"Staged MKV changed while it was being verified: {output}"
            )

        self._verify_contract(inventory, inspection, expected_subtitles)
        return VerifiedOutput(
            source=inventory.source,
            staged_path=output,
            inspection=inspection,
            expected_subtitles=tuple(expected_subtitles),
            size_bytes=after[0],
            modified_time_ns=after[1],
        )

    @staticmethod
    def _snapshot(output: Path) -> tuple[int, int]:
        if output.is_symlink():
            raise VerificationError(f"Staged MKV cannot be a symlink: {output}")
        try:
            if not output.is_file():
                raise VerificationError(f"Staged MKV is missing: {output}")
            stat = output.stat()
        except OSError as exc:
            raise VerificationError(
                f"Cannot inspect staged MKV file {output}: {exc}"
            ) from exc
        if stat.st_size <= 0:
            raise VerificationError(f"Staged MKV is empty: {output}")
        return stat.st_size, stat.st_mtime_ns

    @staticmethod
    def _validate_expectations(
        inventory: VideoInventory,
        expected_subtitles: Sequence[SubtitleArtifact],
    ) -> None:
        if any(
            subtitle.state is not ArtifactState.VALID
            for subtitle in expected_subtitles
        ):
            raise VerificationError("Expected subtitles must all be valid")

        expected_embedded = [
            subtitle.stream_index
            for subtitle in expected_subtitles
            if subtitle.origin is SubtitleOrigin.EMBEDDED
        ]
        source_embedded = [
            stream.index
            for stream in inventory.streams
            if stream.kind is StreamKind.SUBTITLE
        ]
        if expected_embedded != source_embedded:
            raise VerificationError(
                "Expected embedded subtitles do not match source subtitle streams"
            )

        seen_sidecars: set[str] = set()
        for subtitle in expected_subtitles:
            if subtitle.origin is SubtitleOrigin.EMBEDDED:
                continue
            if subtitle.validation is None or not subtitle.validation.is_valid:
                raise VerificationError(
                    f"Expected subtitle was not validated: {subtitle.path}"
                )
            assert subtitle.path is not None
            key = str(subtitle.path.resolve()).casefold()
            if key in seen_sidecars:
                raise VerificationError(
                    f"Expected subtitle is duplicated: {subtitle.path}"
                )
            seen_sidecars.add(key)
            try:
                if not subtitle.path.is_file() or subtitle.path.stat().st_size == 0:
                    raise VerificationError(
                        f"Expected subtitle is missing or empty: {subtitle.path}"
                    )
            except OSError as exc:
                raise VerificationError(
                    f"Cannot inspect expected subtitle {subtitle.path}: {exc}"
                ) from exc

    def _verify_contract(
        self,
        inventory: VideoInventory,
        inspection: MediaInspection,
        expected_subtitles: Sequence[SubtitleArtifact],
    ) -> None:
        format_names = {
            item.strip().casefold()
            for item in (inspection.format_name or "").split(",")
        }
        if "matroska" not in format_names:
            raise VerificationError(
                f"Staged output is not Matroska: {inspection.format_name}"
            )

        sidecars = tuple(
            subtitle
            for subtitle in expected_subtitles
            if subtitle.origin is not SubtitleOrigin.EMBEDDED
        )
        expected_stream_count = len(inventory.streams) + len(sidecars)
        if len(inspection.streams) != expected_stream_count:
            raise VerificationError(
                "Stream count mismatch: expected "
                f"{expected_stream_count}, found {len(inspection.streams)}"
            )

        source_outputs = inspection.streams[: len(inventory.streams)]
        for position, (source, output) in enumerate(
            zip(inventory.streams, source_outputs, strict=True)
        ):
            self._verify_source_stream(position, source, output)

        added_outputs = inspection.streams[len(inventory.streams) :]
        for position, (subtitle, output) in enumerate(
            zip(sidecars, added_outputs, strict=True),
            start=1,
        ):
            self._verify_added_subtitle(position, subtitle, output)

        self._verify_duration(inventory, inspection)
        self._verify_chapters(inventory.chapters, inspection.chapters)
        _require_metadata_subset(
            inventory.metadata,
            inspection.metadata,
            ignored=GLOBAL_VOLATILE_METADATA,
            label="Global",
        )

    @staticmethod
    def _verify_source_stream(
        position: int,
        source: MediaStream,
        output: MediaStream,
    ) -> None:
        label = f"Source stream #{source.index} at output position {position}"
        if output.kind is not source.kind:
            raise VerificationError(
                f"{label} changed type: {source.kind.value} -> {output.kind.value}"
            )
        if output.codec_name.casefold() != source.codec_name.casefold():
            raise VerificationError(
                f"{label} changed codec: {source.codec_name} -> {output.codec_name}"
            )
        if output.language != source.language:
            raise VerificationError(
                f"{label} changed language: {source.language} -> {output.language}"
            )
        if output.title != source.title:
            raise VerificationError(
                f"{label} changed title: {source.title!r} -> {output.title!r}"
            )

        expected_dispositions = source.dispositions
        if source.kind is StreamKind.SUBTITLE:
            expected_dispositions = expected_dispositions - {"default"}
        if output.dispositions != expected_dispositions:
            raise VerificationError(
                f"{label} changed dispositions: "
                f"{sorted(expected_dispositions)} -> {sorted(output.dispositions)}"
            )
        _require_metadata_subset(
            source.metadata,
            output.metadata,
            ignored=STREAM_VOLATILE_METADATA,
            label=label,
        )

    @staticmethod
    def _verify_added_subtitle(
        position: int,
        subtitle: SubtitleArtifact,
        output: MediaStream,
    ) -> None:
        label = f"Added subtitle #{position}"
        if output.kind is not StreamKind.SUBTITLE:
            raise VerificationError(f"{label} is not a subtitle stream")
        if output.codec_name.casefold() != "subrip":
            raise VerificationError(
                f"{label} has unexpected codec: {output.codec_name}"
            )
        if subtitle.language.casefold() != "und" and (
            output.language != subtitle.language
        ):
            raise VerificationError(
                f"{label} changed language: {subtitle.language} -> {output.language}"
            )
        if subtitle.title is not None and subtitle.title.strip() and (
            output.title != subtitle.title
        ):
            raise VerificationError(
                f"{label} changed title: {subtitle.title!r} -> {output.title!r}"
            )
        if "default" in output.dispositions or output.is_default:
            raise VerificationError(f"{label} is marked as default")

    def _verify_duration(
        self,
        inventory: VideoInventory,
        inspection: MediaInspection,
    ) -> None:
        if inventory.duration_seconds is None:
            raise VerificationError("Source duration is unavailable")
        if inspection.duration_seconds is None:
            raise VerificationError("Output duration is unavailable")
        difference = abs(
            inventory.duration_seconds - inspection.duration_seconds
        )
        if difference > self.duration_tolerance_seconds:
            raise VerificationError(
                "Duration mismatch: source "
                f"{inventory.duration_seconds:.3f}s, output "
                f"{inspection.duration_seconds:.3f}s, difference "
                f"{difference:.3f}s"
            )

    def _verify_chapters(
        self,
        source_chapters: Sequence[MediaChapter],
        output_chapters: Sequence[MediaChapter],
    ) -> None:
        if len(source_chapters) != len(output_chapters):
            raise VerificationError(
                "Chapter count mismatch: expected "
                f"{len(source_chapters)}, found {len(output_chapters)}"
            )
        for position, (source, output) in enumerate(
            zip(source_chapters, output_chapters, strict=True),
            start=1,
        ):
            if (
                abs(source.start_seconds - output.start_seconds)
                > self.chapter_tolerance_seconds
                or abs(source.end_seconds - output.end_seconds)
                > self.chapter_tolerance_seconds
            ):
                raise VerificationError(
                    f"Chapter #{position} time range was not preserved"
                )
            if source.title != output.title:
                raise VerificationError(
                    f"Chapter #{position} title was not preserved"
                )
            _require_metadata_subset(
                source.metadata,
                output.metadata,
                ignored=CHAPTER_VOLATILE_METADATA,
                label=f"Chapter #{position}",
            )


class VerificationStage:
    def __init__(self, verifier: OutputVerifier) -> None:
        self.verifier = verifier

    def execute(
        self,
        batch_plan: BatchPlan,
        source: Path,
        paths: WorkspacePaths,
        *,
        generated_subtitle: SubtitleArtifact | None = None,
    ) -> VerifiedOutput | None:
        if not batch_plan.is_executable:
            raise VerificationError(
                "Verification batch is not executable until all issues are resolved"
            )
        try:
            plan = batch_plan.plan_for(source)
        except KeyError as exc:
            raise VerificationError(f"No video plan exists for {source}") from exc
        try:
            decision = plan.decision_for(PipelineStage.VERIFY)
        except KeyError as exc:
            raise VerificationError("Plan has no verification decision") from exc

        if decision.action is StageAction.SKIP:
            return None
        if decision.action is StageAction.NEEDS_INPUT or not plan.is_executable:
            raise VerificationError(
                f"Verification plan is not executable: {decision.reason}"
            )
        try:
            expected_subtitles = planned_subtitles_for(
                plan,
                paths,
                generated_subtitle,
            )
        except MuxingError as exc:
            raise VerificationError(str(exc)) from exc

        staged_output = paths.staged_output_for(plan.inventory.source)
        verified = self.verifier.verify(
            plan.inventory,
            staged_output,
            expected_subtitles,
        )
        if not isinstance(verified, VerifiedOutput):
            raise VerificationError("Verifier returned no verification proof")
        if verified.source.resolve() != plan.inventory.source.resolve():
            raise VerificationError("Verification proof belongs to another source")
        if verified.staged_path.resolve() != staged_output.resolve():
            raise VerificationError("Verification proof belongs to another output")
        if verified.expected_subtitles != expected_subtitles:
            raise VerificationError("Verification proof changed expected subtitles")
        return verified
