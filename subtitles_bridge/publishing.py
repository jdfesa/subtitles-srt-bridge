"""Plan-gated publication that accepts only a current verification proof."""

from __future__ import annotations

from pathlib import Path

from .errors import MuxingError, PublicationCollisionError, PublicationError
from .models import (
    BatchPlan,
    PipelineStage,
    PublishedOutput,
    StageAction,
    VerifiedOutput,
)
from .muxing import planned_subtitles_for
from .paths import WorkspacePaths
from .ports import OutputPublisher


class PublishingStage:
    def __init__(self, publisher: OutputPublisher) -> None:
        self.publisher = publisher

    def execute(
        self,
        batch_plan: BatchPlan,
        source: Path,
        paths: WorkspacePaths,
        verified_output: VerifiedOutput | None,
    ) -> PublishedOutput | None:
        if not batch_plan.is_executable:
            raise PublicationError(
                "Publication batch is not executable until all issues are resolved"
            )
        try:
            plan = batch_plan.plan_for(source)
        except KeyError as exc:
            raise PublicationError(f"No video plan exists for {source}") from exc
        try:
            decision = plan.decision_for(PipelineStage.PUBLISH)
        except KeyError as exc:
            raise PublicationError("Plan has no publication decision") from exc

        if decision.action is StageAction.SKIP:
            return None
        if decision.action is StageAction.NEEDS_INPUT or not plan.is_executable:
            raise PublicationError(
                f"Publication plan is not executable: {decision.reason}"
            )
        if verified_output is None:
            raise PublicationError("Publication requires a verification proof")

        staged_output = paths.staged_output_for(plan.inventory.source)
        final_output = paths.output_for(plan.inventory.source)
        if plan.output_path.resolve() != final_output.resolve():
            raise PublicationError("Plan output does not match workspace policy")
        if verified_output.source.resolve() != plan.inventory.source.resolve():
            raise PublicationError("Verification proof belongs to another source")
        if verified_output.staged_path.resolve() != staged_output.resolve():
            raise PublicationError("Verification proof belongs to another output")
        try:
            transcription = plan.decision_for(PipelineStage.TRANSCRIBE)
            generated = (
                verified_output.expected_subtitles[0]
                if transcription.action is StageAction.RUN
                and len(verified_output.expected_subtitles) == 1
                else None
            )
            expected_subtitles = planned_subtitles_for(plan, paths, generated)
        except (KeyError, MuxingError) as exc:
            raise PublicationError(
                f"Verification proof does not match the plan: {exc}"
            ) from exc
        if verified_output.expected_subtitles != expected_subtitles:
            raise PublicationError(
                "Verification proof does not contain the planned subtitles"
            )
        self._require_current_snapshot(verified_output)

        if final_output.exists() or final_output.is_symlink():
            raise PublicationCollisionError(
                f"Final output already exists: {final_output}"
            )
        self.publisher.publish(staged_output, final_output)

        try:
            if not final_output.is_file() or final_output.stat().st_size == 0:
                raise PublicationError(
                    f"Publisher did not create a usable final output: {final_output}"
                )
            final_stat = final_output.stat()
        except OSError as exc:
            raise PublicationError(
                f"Cannot inspect published output {final_output}: {exc}"
            ) from exc
        if staged_output.exists() or staged_output.is_symlink():
            raise PublicationError(
                f"Publisher left the staged output in place: {staged_output}"
            )
        if (
            final_stat.st_size != verified_output.size_bytes
            or final_stat.st_mtime_ns != verified_output.modified_time_ns
        ):
            raise PublicationError(
                f"Published output no longer matches verification proof: {final_output}"
            )
        return PublishedOutput(
            source=verified_output.source,
            final_path=final_output,
            inspection=verified_output.inspection,
            expected_subtitles=verified_output.expected_subtitles,
            size_bytes=final_stat.st_size,
            modified_time_ns=final_stat.st_mtime_ns,
        )

    @staticmethod
    def _require_current_snapshot(verified_output: VerifiedOutput) -> None:
        path = verified_output.staged_path
        if path.is_symlink():
            raise PublicationError(f"Verified staged output became a symlink: {path}")
        try:
            if not path.is_file():
                raise PublicationError(f"Verified staged output is missing: {path}")
            stat = path.stat()
        except OSError as exc:
            raise PublicationError(
                f"Cannot inspect verified staged output {path}: {exc}"
            ) from exc
        if (
            stat.st_size != verified_output.size_bytes
            or stat.st_mtime_ns != verified_output.modified_time_ns
        ):
            raise PublicationError(f"Staged output changed after verification: {path}")
