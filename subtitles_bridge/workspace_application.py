"""Workspace-level application flow above discovery, planning, and execution."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from .application import (
    BatchExecutionApplication,
    format_fatal_result,
    run_batch_application,
)
from .models import BatchPlan, DiscoveryResult
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
    ) -> BatchPlan: ...


class WorkspaceApplication:
    def __init__(
        self,
        discovery: DiscoveryApplication,
        planner: PlanningApplication,
        executor: BatchExecutionApplication,
    ) -> None:
        self.discovery = discovery
        self.planner = planner
        self.executor = executor

    def run(
        self,
        directory: str | Path,
        *,
        write: Writer = print,
    ) -> int:
        try:
            requested_directory = Path(directory).expanduser()
            paths = WorkspacePaths.from_directory(requested_directory)
            discovery = self.discovery.inspect(paths)
            batch_plan = self.planner.plan(discovery, paths)
        except Exception as exc:
            write(format_fatal_result(exc))
            return 1

        write("Preflight\n" + format_batch_plan(batch_plan))
        return run_batch_application(
            self.executor,
            batch_plan,
            paths,
            write=write,
        )
