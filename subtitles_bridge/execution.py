"""Injected orchestration and deterministic results for a planned batch."""

from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Protocol

from .errors import ExecutionError, PlanningError
from .models import (
    ArchivedInputs,
    BatchPlan,
    BatchResult,
    FailureDetail,
    PipelineStage,
    PublishedOutput,
    ResultStatus,
    StageAction,
    StageResult,
    SubtitleArtifact,
    VerifiedOutput,
    VideoPlan,
    VideoResult,
)
from .observability import StageEventKind, StageExecutionEvent
from .paths import WorkspacePaths

EXECUTION_STAGES = (
    PipelineStage.TRANSCRIBE,
    PipelineStage.MUX,
    PipelineStage.VERIFY,
    PipelineStage.PUBLISH,
    PipelineStage.ARCHIVE,
)
Clock = Callable[[], float]
ExecutionObserver = Callable[[StageExecutionEvent], None]


class TranscriptionApplication(Protocol):
    def execute(
        self,
        batch_plan: BatchPlan,
        source: Path,
        paths: WorkspacePaths,
    ) -> SubtitleArtifact | None: ...


class MuxingApplication(Protocol):
    def execute(
        self,
        batch_plan: BatchPlan,
        source: Path,
        paths: WorkspacePaths,
        *,
        generated_subtitle: SubtitleArtifact | None = None,
    ) -> Path | None: ...


class VerificationApplication(Protocol):
    def execute(
        self,
        batch_plan: BatchPlan,
        source: Path,
        paths: WorkspacePaths,
        *,
        generated_subtitle: SubtitleArtifact | None = None,
    ) -> VerifiedOutput | None: ...


class PublishingApplication(Protocol):
    def execute(
        self,
        batch_plan: BatchPlan,
        source: Path,
        paths: WorkspacePaths,
        verified_output: VerifiedOutput | None,
    ) -> PublishedOutput | None: ...


class ArchivingApplication(Protocol):
    def execute(
        self,
        batch_plan: BatchPlan,
        source: Path,
        paths: WorkspacePaths,
        published_output: PublishedOutput | None,
    ) -> ArchivedInputs | None: ...


class BatchExecutor:
    def __init__(
        self,
        transcription: TranscriptionApplication,
        muxing: MuxingApplication,
        verification: VerificationApplication,
        publishing: PublishingApplication,
        archiving: ArchivingApplication,
        *,
        clock: Clock = time.monotonic,
    ) -> None:
        self.transcription = transcription
        self.muxing = muxing
        self.verification = verification
        self.publishing = publishing
        self.archiving = archiving
        self.clock = clock

    def execute(
        self,
        batch_plan: BatchPlan,
        paths: WorkspacePaths,
        *,
        published_outputs: Sequence[PublishedOutput] = (),
        observer: ExecutionObserver | None = None,
    ) -> BatchResult:
        published_by_source = self._published_map(
            batch_plan,
            published_outputs,
        )
        if not batch_plan.videos:
            return BatchResult(
                (),
                batch_plan.issues,
                "No videos were planned",
            )
        if not batch_plan.is_executable:
            return BatchResult(
                tuple(
                    self._blocked_result(plan, batch_plan) for plan in batch_plan.videos
                ),
                batch_plan.issues,
                "Batch execution is blocked until all issues are resolved",
            )

        results = tuple(
            self._execute_video(
                batch_plan,
                plan,
                paths,
                published_by_source.get(self._source_key(plan.inventory.source)),
                observer,
            )
            for plan in batch_plan.videos
        )
        return BatchResult(results, batch_plan.issues)

    def _execute_video(
        self,
        batch_plan: BatchPlan,
        plan: VideoPlan,
        paths: WorkspacePaths,
        resumed_output: PublishedOutput | None,
        observer: ExecutionObserver | None,
    ) -> VideoResult:
        generated: SubtitleArtifact | None = None
        verified: VerifiedOutput | None = None
        published = resumed_output
        archived: ArchivedInputs | None = None
        stage_results: list[StageResult] = []

        for position, stage in enumerate(EXECUTION_STAGES):
            try:
                decision = plan.decision_for(stage)
            except KeyError:
                return self._failed_result(
                    plan,
                    stage,
                    position,
                    stage_results,
                    ExecutionError(f"Plan has no {stage.value} decision"),
                    published,
                    paths,
                )
            if decision.action is StageAction.SKIP:
                stage_results.append(
                    StageResult(stage, ResultStatus.SKIPPED, decision.reason)
                )
                continue
            if decision.action is StageAction.NEEDS_INPUT:
                stage_results.append(
                    StageResult(stage, ResultStatus.NEEDS_INPUT, decision.reason)
                )
                return VideoResult(
                    plan.inventory.source,
                    ResultStatus.NEEDS_INPUT,
                    decision.reason,
                    stages=tuple(stage_results),
                )

            target_path = self._stage_target(plan, stage, paths)
            started_at = self.clock()
            if observer is not None:
                observer(
                    StageExecutionEvent(
                        StageEventKind.STARTED,
                        plan.inventory.source,
                        stage,
                        target_path,
                        f"Running {stage.value} for {plan.inventory.source}",
                    )
                )
            try:
                if stage is PipelineStage.TRANSCRIBE:
                    generated = self.transcription.execute(
                        batch_plan,
                        plan.inventory.source,
                        paths,
                    )
                    self._require_type(stage, generated, SubtitleArtifact)
                    message = f"Generated subtitle: {generated.path}"
                elif stage is PipelineStage.MUX:
                    staged = self.muxing.execute(
                        batch_plan,
                        plan.inventory.source,
                        paths,
                        generated_subtitle=generated,
                    )
                    self._require_type(stage, staged, Path)
                    message = f"Created staged MKV: {staged}"
                elif stage is PipelineStage.VERIFY:
                    verified = self.verification.execute(
                        batch_plan,
                        plan.inventory.source,
                        paths,
                        generated_subtitle=generated,
                    )
                    self._require_type(stage, verified, VerifiedOutput)
                    message = f"Verified staged MKV: {verified.staged_path}"
                elif stage is PipelineStage.PUBLISH:
                    published = self.publishing.execute(
                        batch_plan,
                        plan.inventory.source,
                        paths,
                        verified,
                    )
                    self._require_type(stage, published, PublishedOutput)
                    message = f"Published MKV: {published.final_path}"
                else:
                    archived = self.archiving.execute(
                        batch_plan,
                        plan.inventory.source,
                        paths,
                        published,
                    )
                    self._require_type(stage, archived, ArchivedInputs)
                    message = (
                        f"Archived {len(archived.archived_paths)} input(s): "
                        f"{archived.destination}"
                    )
                duration = self._elapsed_since(started_at)
                stage_result = StageResult(
                    stage,
                    ResultStatus.COMPLETED,
                    message,
                    duration,
                )
            except Exception as exc:
                duration = self._elapsed_since(started_at)
                result = self._failed_result(
                    plan,
                    stage,
                    position,
                    stage_results,
                    exc,
                    published,
                    paths,
                    duration,
                )
                if observer is not None:
                    failed_stage = result.stages[len(stage_results)]
                    observer(
                        StageExecutionEvent(
                            StageEventKind.FINISHED,
                            plan.inventory.source,
                            stage,
                            target_path,
                            failed_stage.message,
                            ResultStatus.FAILED,
                            duration,
                            failed_stage.failure,
                        )
                    )
                return result
            stage_results.append(stage_result)
            if observer is not None:
                observer(
                    StageExecutionEvent(
                        StageEventKind.FINISHED,
                        plan.inventory.source,
                        stage,
                        target_path,
                        message,
                        ResultStatus.COMPLETED,
                        duration,
                    )
                )

        ran_stage = any(
            plan.decision_for(stage).action is StageAction.RUN
            for stage in EXECUTION_STAGES
        )
        status = ResultStatus.COMPLETED if ran_stage else ResultStatus.SKIPPED
        output_path = published.final_path if published is not None else None
        trash_path = archived.destination if archived is not None else None
        message = (
            f"Completed all planned stages for {plan.inventory.source}"
            if ran_stage
            else f"All stages were already complete for {plan.inventory.source}"
        )
        return VideoResult(
            plan.inventory.source,
            status,
            message,
            output_path,
            trash_path,
            tuple(stage_results),
        )

    @staticmethod
    def _require_type(stage: PipelineStage, value, expected_type: type) -> None:
        if not isinstance(value, expected_type):
            raise ExecutionError(
                f"{stage.value} returned no {expected_type.__name__} artifact"
            )

    @staticmethod
    def _blocked_result(plan: VideoPlan, batch_plan: BatchPlan) -> VideoResult:
        blockers = [
            decision.reason
            for decision in plan.decisions
            if decision.action is StageAction.NEEDS_INPUT
        ]
        blockers.extend(f"{issue.path}: {issue.message}" for issue in batch_plan.issues)
        if not blockers:
            blockers.append("Another video has unresolved planning decisions")
        message = "; ".join(dict.fromkeys(blockers))
        stage_results = tuple(
            StageResult(
                decision.stage,
                ResultStatus.NEEDS_INPUT,
                decision.reason
                if decision.action is StageAction.NEEDS_INPUT
                else f"Batch blocked before {decision.stage.value}: {message}",
            )
            for decision in plan.decisions
        )
        return VideoResult(
            plan.inventory.source,
            ResultStatus.NEEDS_INPUT,
            message,
            plan.output_path if plan.uses_verified_output else None,
            stages=stage_results,
        )

    @staticmethod
    def _failed_result(
        plan: VideoPlan,
        stage: PipelineStage,
        position: int,
        completed_stages: list[StageResult],
        error: Exception,
        published: PublishedOutput | None,
        paths: WorkspacePaths,
        duration_seconds: float | None = None,
    ) -> VideoResult:
        error_text = str(error).strip() or repr(error)
        detail = f"{type(error).__name__}: {error_text}"
        failure = FailureDetail(
            type(error).__name__,
            error_text,
            BatchExecutor._stage_target(plan, stage, paths),
            plan.transcription_audio_index
            if stage is PipelineStage.TRANSCRIBE
            else None,
        )
        stages = [
            *completed_stages,
            StageResult(
                stage,
                ResultStatus.FAILED,
                f"{plan.inventory.source}: {detail}",
                duration_seconds,
                failure,
            ),
        ]
        stages.extend(
            StageResult(
                remaining,
                ResultStatus.SKIPPED,
                f"Not run because {stage.value} failed for {plan.inventory.source}",
            )
            for remaining in EXECUTION_STAGES[position + 1 :]
        )
        is_partial = stage is PipelineStage.ARCHIVE and (
            published is not None or plan.uses_verified_output
        )
        status = ResultStatus.PARTIAL if is_partial else ResultStatus.FAILED
        output_path = (
            published.final_path
            if published is not None
            else plan.output_path
            if plan.uses_verified_output
            else None
        )
        return VideoResult(
            plan.inventory.source,
            status,
            f"{stage.value} failed for {plan.inventory.source}: {detail}",
            output_path,
            plan.trash_path if is_partial else None,
            stages=tuple(stages),
        )

    def _elapsed_since(self, started_at: float) -> float:
        return max(0.0, self.clock() - started_at)

    @staticmethod
    def _stage_target(
        plan: VideoPlan,
        stage: PipelineStage,
        paths: WorkspacePaths,
    ) -> Path:
        if stage is PipelineStage.TRANSCRIBE:
            return plan.inventory.source
        if stage in (PipelineStage.MUX, PipelineStage.VERIFY):
            return paths.staged_output_for(plan.inventory.source)
        if stage is PipelineStage.PUBLISH:
            return plan.output_path
        return plan.trash_path

    @classmethod
    def _published_map(
        cls,
        batch_plan: BatchPlan,
        outputs: Sequence[PublishedOutput],
    ) -> dict[str, PublishedOutput]:
        plans = {
            cls._source_key(plan.inventory.source): plan for plan in batch_plan.videos
        }
        result: dict[str, PublishedOutput] = {}
        for output in outputs:
            key = cls._source_key(output.source)
            if key not in plans:
                raise PlanningError(
                    f"Published output proof has no video plan: {output.source}"
                )
            if key in result:
                raise PlanningError(
                    f"Duplicate published output proof for {output.source}"
                )
            if not plans[key].uses_verified_output:
                raise PlanningError(
                    f"Published output proof was not planned for {output.source}"
                )
            result[key] = output
        return result

    @staticmethod
    def _source_key(path: Path) -> str:
        return str(path.resolve()).casefold()
