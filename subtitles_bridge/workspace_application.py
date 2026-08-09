"""Workspace-level application flow above discovery, planning, and execution."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from .application import (
    BatchExecutionApplication,
    format_fatal_result,
    run_batch_application,
)
from .errors import PlanningError
from .models import BatchPlan, DiscoveryResult, PlanningChoice, PublishedOutput
from .observability import JsonLinesReporter, OutputFormat
from .paths import WorkspacePaths
from .summary import format_batch_plan

Writer = Callable[[str], None]


class DiscoveryApplication(Protocol):
    def inspect(self, paths: WorkspacePaths) -> DiscoveryResult: ...


class PlanningApplication(Protocol):
    def plan(
        self,
        discovery: DiscoveryResult,
        paths: WorkspacePaths,
        choices: Sequence[PlanningChoice] = (),
    ) -> BatchPlan: ...


class ResumeApplication(Protocol):
    def verify(
        self,
        discovery: DiscoveryResult,
        paths: WorkspacePaths,
    ) -> tuple[PublishedOutput, ...]: ...


@dataclass(frozen=True, slots=True)
class AudioSelection:
    source: str
    stream_index: int

    def __post_init__(self) -> None:
        if not self.source.strip():
            raise ValueError("Audio selection requires a source video")
        if self.stream_index < 0:
            raise ValueError("Selected audio stream cannot be negative")


class WorkspaceApplication:
    def __init__(
        self,
        discovery: DiscoveryApplication,
        planner: PlanningApplication,
        executor: BatchExecutionApplication,
        resumer: ResumeApplication | None = None,
    ) -> None:
        self.discovery = discovery
        self.planner = planner
        self.executor = executor
        self.resumer = resumer

    def run(
        self,
        directory: str | Path,
        *,
        preflight_only: bool = False,
        audio_selections: Sequence[AudioSelection] = (),
        resume: bool = False,
        write: Writer = print,
        output_format: OutputFormat = OutputFormat.TEXT,
    ) -> int:
        reporter = (
            JsonLinesReporter(write) if output_format is OutputFormat.JSONL else None
        )
        try:
            requested_directory = Path(directory).expanduser()
            paths = WorkspacePaths.from_directory(requested_directory)
            discovery = self.discovery.inspect(paths)
            choices = self._audio_choices(paths, audio_selections)
            published_outputs: tuple[PublishedOutput, ...] = ()
            if resume:
                if self.resumer is None:
                    raise PlanningError("Resume support is not configured")
                published_outputs = self.resumer.verify(discovery, paths)
                choices = self._merge_resume_choices(choices, published_outputs)
            batch_plan = self.planner.plan(discovery, paths, choices)
        except Exception as exc:
            if reporter is None:
                write(format_fatal_result(exc))
            else:
                reporter.fatal("batch", exc)
            return 1

        if reporter is None:
            write("Preflight\n" + format_batch_plan(batch_plan))
        else:
            reporter.preflight(batch_plan)
        if preflight_only:
            exit_code = self._preflight_exit_code(batch_plan)
            status = (
                "ready"
                if exit_code == 0
                else "needs-input"
                if exit_code == 2
                else "failed"
            )
            if reporter is None:
                write(f"Preflight result: {status}\nExit code: {exit_code}")
            else:
                reporter.preflight_result(status, exit_code)
            return exit_code
        return run_batch_application(
            self.executor,
            batch_plan,
            paths,
            published_outputs=published_outputs,
            write=write,
            output_format=output_format,
            reporter=reporter,
        )

    @staticmethod
    def _audio_choices(
        paths: WorkspacePaths,
        selections: Sequence[AudioSelection],
    ) -> tuple[PlanningChoice, ...]:
        choices = []
        seen_sources: set[str] = set()
        for selection in selections:
            candidate = Path(selection.source).expanduser()
            if not candidate.is_absolute():
                candidate = paths.root / candidate
            source = paths.source_video(candidate)
            key = str(source.resolve())
            if key in seen_sources:
                raise PlanningError(f"Duplicate audio selection for {source}")
            seen_sources.add(key)
            choices.append(PlanningChoice(source, selection.stream_index))
        return tuple(choices)

    @staticmethod
    def _merge_resume_choices(
        choices: Sequence[PlanningChoice],
        outputs: Sequence[PublishedOutput],
    ) -> tuple[PlanningChoice, ...]:
        by_source = {str(choice.source.resolve()): choice for choice in choices}
        if len(by_source) != len(choices):
            raise PlanningError("Duplicate audio selection for a source video")
        for output in outputs:
            key = str(output.source.resolve())
            choice = by_source.get(key)
            by_source[key] = PlanningChoice(
                output.source,
                choice.audio_stream_index if choice is not None else None,
                output.final_path,
            )
        return tuple(by_source.values())

    @staticmethod
    def _preflight_exit_code(batch_plan: BatchPlan) -> int:
        if batch_plan.has_needs_input:
            return 2
        if not batch_plan.videos:
            return 1
        return 0
