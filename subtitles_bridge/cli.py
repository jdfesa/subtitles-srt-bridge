"""Minimal command-line boundary for the composed workspace application."""

from __future__ import annotations

import argparse
from collections.abc import Callable, Sequence

from .application import format_fatal_result
from .bootstrap import build_default_workspace_application
from .workspace_application import WorkspaceApplication, Writer


ApplicationFactory = Callable[[], WorkspaceApplication]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="subtitles-bridge",
        description=(
            "Package selectable subtitle tracks into verified MKV outputs "
            "without transcoding source streams."
        ),
    )
    parser.add_argument(
        "directory",
        nargs="?",
        default=".",
        help="workspace containing non-recursive MP4/MKV inputs (default: cwd)",
    )
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    application_factory: ApplicationFactory = build_default_workspace_application,
    write: Writer = print,
) -> int:
    arguments = build_parser().parse_args(argv)
    try:
        application = application_factory()
    except Exception as exc:
        write(format_fatal_result(exc))
        return 1
    return application.run(arguments.directory, write=write)
