"""Structured progress and result reporting for automation consumers."""

from __future__ import annotations

import json
import math
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from .models import (
    BatchPlan,
    BatchResult,
    FailureDetail,
    PipelineStage,
    ResultStatus,
    StageAction,
    SubtitleOrigin,
)

Writer = Callable[[str], None]
SCHEMA_VERSION = 1
EXPENSIVE_STAGES = frozenset(
    (
        PipelineStage.TRANSCRIBE,
        PipelineStage.MUX,
        PipelineStage.VERIFY,
    )
)


class OutputFormat(str, Enum):
    TEXT = "text"
    JSONL = "jsonl"


class StageEventKind(str, Enum):
    STARTED = "stage-started"
    FINISHED = "stage-finished"


@dataclass(frozen=True, slots=True)
class StageExecutionEvent:
    kind: StageEventKind
    source: Path
    stage: PipelineStage
    target_path: Path
    message: str
    status: ResultStatus | None = None
    duration_seconds: float | None = None
    failure: FailureDetail | None = None

    def __post_init__(self) -> None:
        if not self.message.strip():
            raise ValueError("Stage events require a message")
        if self.kind is StageEventKind.STARTED:
            if self.status is not None or self.duration_seconds is not None:
                raise ValueError("A started stage cannot have a result or duration")
            if self.failure is not None:
                raise ValueError("A started stage cannot have failure details")
            return
        if self.status not in (ResultStatus.COMPLETED, ResultStatus.FAILED):
            raise ValueError("A finished stage requires completed or failed status")
        if self.duration_seconds is None or not math.isfinite(self.duration_seconds):
            raise ValueError("A finished stage requires a finite duration")
        if self.duration_seconds < 0:
            raise ValueError("A stage duration cannot be negative")
        if self.failure is not None and self.status is not ResultStatus.FAILED:
            raise ValueError("Only a failed event can carry failure details")


class JsonLinesReporter:
    """Emit schema-versioned JSON records and maintain an honest live ETA."""

    def __init__(self, write: Writer = print) -> None:
        self.write = write
        self.sequence = 0
        self._plans = {}
        self._pending: set[tuple[str, PipelineStage]] = set()
        self._samples: dict[PipelineStage, tuple[float, float]] = {}

    def preflight(self, plan: BatchPlan) -> None:
        self._plans = {
            self._source_key(video.inventory.source): video for video in plan.videos
        }
        self._pending = {
            (self._source_key(video.inventory.source), decision.stage)
            for video in plan.videos
            for decision in video.decisions
            if decision.action is StageAction.RUN and decision.stage in EXPENSIVE_STAGES
        }
        self._samples = {}
        self._emit(
            "preflight",
            batch=_batch_plan_payload(plan),
            eta_seconds=self._eta_seconds(),
            remaining_expensive_stages=len(self._pending),
        )

    def preflight_result(self, status: str, exit_code: int) -> None:
        self._emit(
            "preflight-result",
            status=status,
            exit_code=exit_code,
            eta_seconds=self._eta_seconds(),
            remaining_expensive_stages=len(self._pending),
        )

    def stage_event(self, event: StageExecutionEvent) -> None:
        if event.kind is StageEventKind.FINISHED:
            self._finish_stage(event)
        payload = {
            "source": str(event.source),
            "stage": event.stage.value,
            "status": ("running" if event.status is None else event.status.value),
            "message": event.message,
            "target_path": str(event.target_path),
            "duration_seconds": _rounded(event.duration_seconds),
            "eta_seconds": self._eta_seconds(),
            "remaining_expensive_stages": len(self._pending),
        }
        if event.failure is not None:
            payload["failure"] = _failure_payload(event.failure)
        self._emit(event.kind.value, **payload)

    def batch_result(self, result: BatchResult) -> None:
        self._emit(
            "batch-result",
            result=_batch_result_payload(result),
            eta_seconds=self._eta_seconds(),
            remaining_expensive_stages=len(self._pending),
        )

    def doctor_result(self, report) -> None:
        self._emit(
            "doctor-result",
            status=report.status,
            exit_code=report.exit_code,
            checks=[
                {
                    "name": check.name,
                    "status": check.status.value,
                    "message": check.message,
                }
                for check in report.checks
            ],
        )

    def fatal(self, scope: str, error: Exception) -> None:
        message = str(error).strip() or repr(error)
        self._emit(
            "fatal",
            scope=scope,
            status="failed",
            exit_code=1,
            error={"type": type(error).__name__, "message": message},
        )

    def _finish_stage(self, event: StageExecutionEvent) -> None:
        source_key = self._source_key(event.source)
        self._pending.discard((source_key, event.stage))
        plan = self._plans.get(source_key)
        if (
            event.status is ResultStatus.COMPLETED
            and event.stage in EXPENSIVE_STAGES
            and plan is not None
            and plan.inventory.duration_seconds is not None
            and plan.inventory.duration_seconds > 0
        ):
            elapsed, media = self._samples.get(event.stage, (0.0, 0.0))
            self._samples[event.stage] = (
                elapsed + event.duration_seconds,
                media + plan.inventory.duration_seconds,
            )
        if event.status is ResultStatus.FAILED:
            self._pending = {item for item in self._pending if item[0] != source_key}

    def _eta_seconds(self) -> float | None:
        if not self._pending:
            return 0.0
        estimate = 0.0
        for source_key, stage in self._pending:
            plan = self._plans.get(source_key)
            sample = self._samples.get(stage)
            if (
                plan is None
                or plan.inventory.duration_seconds is None
                or plan.inventory.duration_seconds <= 0
                or sample is None
                or sample[1] <= 0
            ):
                return None
            estimate += plan.inventory.duration_seconds * (sample[0] / sample[1])
        return _rounded(estimate)

    def _emit(self, event: str, **payload) -> None:
        self.sequence += 1
        record = {
            "schema_version": SCHEMA_VERSION,
            "sequence": self.sequence,
            "event": event,
            **payload,
        }
        self.write(
            json.dumps(
                record,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
        )

    @staticmethod
    def _source_key(source: Path) -> str:
        return str(source.resolve()).casefold()


def _batch_plan_payload(plan: BatchPlan) -> dict:
    status = (
        "needs-input"
        if not plan.is_executable
        else "empty"
        if not plan.videos
        else "ready"
    )
    return {
        "status": status,
        "video_count": len(plan.videos),
        "issues": [
            {
                "kind": issue.kind.value,
                "path": str(issue.path),
                "message": issue.message,
                "candidate_videos": [str(path) for path in issue.candidate_videos],
            }
            for issue in plan.issues
        ],
        "videos": [
            {
                "source": str(video.inventory.source),
                "duration_seconds": video.inventory.duration_seconds,
                "status": "ready" if video.is_executable else "needs-input",
                "output_path": str(video.output_path),
                "trash_path": str(video.trash_path),
                "transcription_audio_index": video.transcription_audio_index,
                "audio_streams": [
                    {
                        "index": stream.index,
                        "language": stream.language,
                        "title": stream.title,
                        "default": stream.is_default,
                    }
                    for stream in video.inventory.audio_streams
                ],
                "subtitles": [
                    {
                        "origin": subtitle.origin.value,
                        "state": subtitle.state.value,
                        "language": subtitle.language,
                        "title": subtitle.title,
                        "path": (
                            None
                            if subtitle.origin is SubtitleOrigin.EMBEDDED
                            else str(subtitle.path)
                        ),
                        "stream_index": subtitle.stream_index,
                        "message": subtitle.message,
                    }
                    for subtitle in video.inventory.subtitles
                ],
                "decisions": [
                    {
                        "stage": decision.stage.value,
                        "action": decision.action.value,
                        "reason": decision.reason,
                    }
                    for decision in video.decisions
                ],
            }
            for video in plan.videos
        ],
    }


def _batch_result_payload(result: BatchResult) -> dict:
    statuses = (
        ResultStatus.COMPLETED,
        ResultStatus.SKIPPED,
        ResultStatus.NEEDS_INPUT,
        ResultStatus.PARTIAL,
        ResultStatus.FAILED,
    )
    return {
        "status": result.status.value,
        "exit_code": result.exit_code,
        "message": result.message or None,
        "counts": {status.value: result.count(status) for status in statuses},
        "issues": [
            {
                "kind": issue.kind.value,
                "path": str(issue.path),
                "message": issue.message,
            }
            for issue in result.issues
        ],
        "videos": [_video_result_payload(video) for video in result.videos],
    }


def _video_result_payload(video) -> dict:
    payload = {
        "source": str(video.source),
        "status": video.status.value,
        "message": video.message,
        "output_path": None if video.output_path is None else str(video.output_path),
        "trash_path": None if video.trash_path is None else str(video.trash_path),
        "stages": [
            {
                "stage": stage.stage.value,
                "status": stage.status.value,
                "message": stage.message,
                "duration_seconds": _rounded(stage.duration_seconds),
                "failure": (
                    None if stage.failure is None else _failure_payload(stage.failure)
                ),
            }
            for stage in video.stages
        ],
    }
    if video.status is ResultStatus.PARTIAL:
        payload["recovery"] = {
            "action": "resume",
            "option": "--resume",
            "pending_stage": PipelineStage.ARCHIVE.value,
            "published_output": str(video.output_path),
            "trash_path": None if video.trash_path is None else str(video.trash_path),
        }
    return payload


def _failure_payload(failure: FailureDetail) -> dict:
    return {
        "type": failure.error_type,
        "message": failure.message,
        "target_path": (
            None if failure.target_path is None else str(failure.target_path)
        ),
        "stream_index": failure.stream_index,
    }


def _rounded(value: float | None) -> float | None:
    return None if value is None else round(value, 3)
