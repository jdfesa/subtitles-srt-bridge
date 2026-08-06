"""Minimal command-line boundary for the composed workspace application."""

from __future__ import annotations

import argparse
from collections.abc import Callable, Sequence

from .application import format_fatal_result
from .adapters.whisper import WhisperConfig
from .bootstrap import build_default_workspace_application
from .workspace_application import AudioSelection, WorkspaceApplication, Writer


ApplicationFactory = Callable[[WhisperConfig], WorkspaceApplication]


def _non_empty(value: str) -> str:
    if not value.strip():
        raise argparse.ArgumentTypeError("value cannot be empty")
    return value


def _audio_selection(value: str) -> AudioSelection:
    try:
        source, raw_index = value.rsplit("=", 1)
        stream_index = int(raw_index)
        return AudioSelection(source, stream_index)
    except (ValueError, TypeError) as exc:
        raise argparse.ArgumentTypeError(
            "audio selection must use SOURCE=STREAM_INDEX with a non-negative index"
        ) from exc


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
    parser.add_argument(
        "--preflight",
        action="store_true",
        help="inspect and print the plan without executing any stage",
    )
    parser.add_argument(
        "--audio",
        action="append",
        default=[],
        type=_audio_selection,
        metavar="SOURCE=STREAM_INDEX",
        help="select the audio stream to transcribe for one source (repeatable)",
    )
    parser.add_argument(
        "--whisper-model",
        default="small",
        type=_non_empty,
        metavar="MODEL_OR_PATH",
        help="local/cache Whisper model name or checkpoint path (default: small)",
    )
    parser.add_argument(
        "--whisper-device",
        type=_non_empty,
        metavar="DEVICE",
        help="device passed to Whisper, such as cpu, cuda, or mps",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="re-verify existing outputs and run only pending safe stages",
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
        application = application_factory(
            WhisperConfig(
                model=arguments.whisper_model,
                device=arguments.whisper_device,
            )
        )
    except Exception as exc:
        write(format_fatal_result(exc))
        return 1
    return application.run(
        arguments.directory,
        preflight_only=arguments.preflight,
        audio_selections=arguments.audio,
        resume=arguments.resume,
        write=write,
    )
