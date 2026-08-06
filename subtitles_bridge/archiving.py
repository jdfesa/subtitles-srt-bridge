"""Plan-gated quarantine of inputs consumed by a published output."""

from __future__ import annotations

from pathlib import Path

from .errors import (
    ArchivingError,
    ArchivingPartialError,
    MuxingError,
    SubtitleIntegrityError,
)
from .integrity import subtitle_sha256
from .models import (
    ArchivedInputs,
    BatchPlan,
    PipelineStage,
    PublishedOutput,
    StageAction,
    SubtitleArtifact,
    SubtitleOrigin,
    VideoPlan,
)
from .muxing import planned_subtitles_for, validate_generated_subtitle
from .paths import WorkspacePaths
from .ports import InputArchiver


class ArchivingStage:
    def __init__(self, archiver: InputArchiver) -> None:
        self.archiver = archiver

    def execute(
        self,
        batch_plan: BatchPlan,
        source: Path,
        paths: WorkspacePaths,
        published_output: PublishedOutput | None,
    ) -> ArchivedInputs | None:
        if not batch_plan.is_executable:
            raise ArchivingError(
                "Archiving batch is not executable until all issues are resolved"
            )
        try:
            plan = batch_plan.plan_for(source)
        except KeyError as exc:
            raise ArchivingError(f"No video plan exists for {source}") from exc
        try:
            decision = plan.decision_for(PipelineStage.ARCHIVE)
        except KeyError as exc:
            raise ArchivingError("Plan has no archiving decision") from exc

        if decision.action is StageAction.SKIP:
            return None
        if decision.action is StageAction.NEEDS_INPUT or not plan.is_executable:
            raise ArchivingError(
                f"Archiving plan is not executable: {decision.reason}"
            )
        if published_output is None:
            raise ArchivingError("Archiving requires a published output proof")

        final_output = paths.output_for(plan.inventory.source)
        destination = paths.trash_for(plan.inventory.source)
        if plan.output_path.resolve() != final_output.resolve():
            raise ArchivingError("Plan output does not match workspace policy")
        if plan.trash_path.resolve() != destination.resolve():
            raise ArchivingError(
                "Plan trash destination does not match workspace policy"
            )
        if published_output.source.resolve() != plan.inventory.source.resolve():
            raise ArchivingError("Published output proof belongs to another source")
        if published_output.final_path.resolve() != final_output.resolve():
            raise ArchivingError("Published output proof belongs to another output")

        self._require_current_output(published_output)
        expected_subtitles = self._expected_subtitles(
            plan,
            paths,
            published_output,
        )
        sidecars = tuple(
            subtitle.path
            for subtitle in expected_subtitles
            if subtitle.origin is not SubtitleOrigin.EMBEDDED
            and subtitle.path is not None
        )
        self._require_current_sidecars(expected_subtitles)
        expected_originals = (plan.inventory.source, *sidecars)
        expected_archived = tuple(
            destination / path.name for path in expected_originals
        )

        try:
            receipt = self.archiver.archive(
                plan.inventory.source,
                sidecars,
                destination,
            )
        except ArchivingPartialError:
            raise
        except ArchivingError as exc:
            raise ArchivingPartialError(
                "Published output remains valid, but input archiving is "
                f"incomplete: {exc}"
            ) from exc
        if not isinstance(receipt, ArchivedInputs):
            raise ArchivingError("Archiver returned no completion receipt")
        if receipt.source.resolve() != plan.inventory.source.resolve():
            raise ArchivingError("Archive receipt belongs to another source")
        if receipt.destination.resolve() != destination.resolve():
            raise ArchivingError("Archive receipt belongs to another destination")
        if self._path_keys(receipt.original_paths) != self._path_keys(
            expected_originals
        ):
            raise ArchivingError("Archive receipt changed the planned inputs")
        if self._path_keys(receipt.archived_paths) != self._path_keys(
            expected_archived
        ):
            raise ArchivingError("Archive receipt changed the planned destinations")

        self._require_completed_archive(receipt)
        self._require_current_output(published_output)
        return receipt

    @staticmethod
    def _expected_subtitles(
        plan: VideoPlan,
        paths: WorkspacePaths,
        published_output: PublishedOutput,
    ) -> tuple[SubtitleArtifact, ...]:
        expected = published_output.expected_subtitles
        generated = tuple(
            subtitle
            for subtitle in expected
            if subtitle.origin is SubtitleOrigin.GENERATED
        )
        if plan.uses_verified_output:
            if generated:
                if len(expected) != 1 or plan.selected_subtitles:
                    raise ArchivingError(
                        "Published output has an invalid generated subtitle set"
                    )
                try:
                    validate_generated_subtitle(plan, paths, generated[0])
                except MuxingError as exc:
                    raise ArchivingError(str(exc)) from exc
            elif expected != plan.selected_subtitles:
                raise ArchivingError(
                    "Published output does not contain the planned subtitles"
                )
            return expected

        try:
            transcription = plan.decision_for(PipelineStage.TRANSCRIBE)
            generated_subtitle = (
                generated[0]
                if transcription.action is StageAction.RUN
                and len(generated) == 1
                and len(expected) == 1
                else None
            )
            planned = planned_subtitles_for(plan, paths, generated_subtitle)
        except (KeyError, MuxingError) as exc:
            raise ArchivingError(
                f"Published output does not match the plan: {exc}"
            ) from exc
        if expected != planned:
            raise ArchivingError(
                "Published output does not contain the planned subtitles"
            )
        return expected

    @staticmethod
    def _require_current_sidecars(
        subtitles: tuple[SubtitleArtifact, ...],
    ) -> None:
        for subtitle in subtitles:
            if subtitle.origin is SubtitleOrigin.EMBEDDED:
                continue
            assert subtitle.path is not None
            if subtitle.content_sha256 is None:
                continue
            try:
                current_sha256 = subtitle_sha256(subtitle.path)
            except SubtitleIntegrityError as exc:
                raise ArchivingError(str(exc)) from exc
            if current_sha256 != subtitle.content_sha256:
                raise ArchivingError(
                    f"Subtitle sidecar changed after publication: {subtitle.path}"
                )

    @staticmethod
    def _require_current_output(published_output: PublishedOutput) -> None:
        path = published_output.final_path
        if path.is_symlink():
            raise ArchivingError(f"Published output became a symlink: {path}")
        try:
            if not path.is_file():
                raise ArchivingError(f"Published output is missing: {path}")
            stat = path.stat()
        except OSError as exc:
            raise ArchivingError(
                f"Cannot inspect published output {path}: {exc}"
            ) from exc
        if (
            stat.st_size != published_output.size_bytes
            or stat.st_mtime_ns != published_output.modified_time_ns
        ):
            raise ArchivingError(f"Published output changed: {path}")

    @staticmethod
    def _require_completed_archive(receipt: ArchivedInputs) -> None:
        for original, archived in zip(
            receipt.original_paths,
            receipt.archived_paths,
            strict=True,
        ):
            if original.exists() or original.is_symlink():
                raise ArchivingError(f"Archive left an input in place: {original}")
            if archived.is_symlink() or not archived.is_file():
                raise ArchivingError(f"Archived input is unavailable: {archived}")
            try:
                if archived.stat().st_size <= 0:
                    raise ArchivingError(f"Archived input is empty: {archived}")
            except OSError as exc:
                raise ArchivingError(
                    f"Cannot inspect archived input {archived}: {exc}"
                ) from exc

    @staticmethod
    def _path_keys(paths: tuple[Path, ...]) -> tuple[str, ...]:
        return tuple(str(path.resolve()).casefold() for path in paths)
