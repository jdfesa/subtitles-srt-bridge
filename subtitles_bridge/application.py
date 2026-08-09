"""CLI-facing reporting boundary without argument or process ownership."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Protocol

from .models import BatchPlan, BatchResult, PublishedOutput
from .observability import JsonLinesReporter, OutputFormat, StageExecutionEvent
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
        observer: Callable[[StageExecutionEvent], None] | None = None,
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
    output_format: OutputFormat = OutputFormat.TEXT,
    reporter: JsonLinesReporter | None = None,
) -> int:
    if output_format is OutputFormat.JSONL and reporter is None:
        reporter = JsonLinesReporter(write)
    try:
        result = executor.execute(
            batch_plan,
            paths,
            published_outputs=published_outputs,
            observer=None if reporter is None else reporter.stage_event,
        )
    except Exception as exc:
        if reporter is None:
            write(format_fatal_result(exc))
        else:
            reporter.fatal("batch", exc)
        return 1

    if reporter is None:
        write(format_batch_result(result))
    else:
        reporter.batch_result(result)
    return result.exit_code
