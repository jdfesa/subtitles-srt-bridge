"""CLI-facing reporting boundary without argument or process ownership."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Protocol

from .models import BatchPlan, BatchResult, PublishedOutput
from .paths import WorkspacePaths
from .summary import format_batch_result


Writer = Callable[[str], None]


class BatchExecutionApplication(Protocol):
    def execute(
        self,
        batch_plan: BatchPlan,
        paths: WorkspacePaths,
        *,
        published_outputs: Sequence[PublishedOutput] = (),
    ) -> BatchResult: ...


def format_fatal_result(error: Exception) -> str:
    message = str(error).strip() or repr(error)
    return "\n".join(
        (
            "Batch result: failed",
            "Exit code: 1",
            f"Fatal: {type(error).__name__}: {message}",
        )
    )


def run_batch_application(
    executor: BatchExecutionApplication,
    batch_plan: BatchPlan,
    paths: WorkspacePaths,
    *,
    published_outputs: Sequence[PublishedOutput] = (),
    write: Writer = print,
) -> int:
    try:
        result = executor.execute(
            batch_plan,
            paths,
            published_outputs=published_outputs,
        )
    except Exception as exc:
        write(format_fatal_result(exc))
        return 1

    write(format_batch_result(result))
    return result.exit_code
