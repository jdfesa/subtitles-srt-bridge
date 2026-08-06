"""CLI-facing reporting boundary without argument or process ownership."""

from __future__ import annotations

from collections.abc import Callable, Sequence

from .execution import BatchExecutor
from .models import BatchPlan, PublishedOutput
from .paths import WorkspacePaths
from .summary import format_batch_result


Writer = Callable[[str], None]


def run_batch_application(
    executor: BatchExecutor,
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
        message = str(exc).strip() or repr(exc)
        write(
            "\n".join(
                (
                    "Batch result: failed",
                    "Exit code: 1",
                    f"Fatal: {type(exc).__name__}: {message}",
                )
            )
        )
        return 1

    write(format_batch_result(result))
    return result.exit_code
