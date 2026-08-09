"""Minimal command-line boundary for the composed workspace application."""

from __future__ import annotations

import argparse
from collections.abc import Callable, Sequence

from .adapters.whisper import WhisperConfig
from .application import format_fatal_result
from .bootstrap import (
    build_default_doctor_application,
    build_default_workspace_application,
)
from .diagnostics import DoctorApplication, format_diagnostic_fatal
from .observability import JsonLinesReporter, OutputFormat
from .workspace_application import AudioSelection, WorkspaceApplication, Writer

ApplicationFactory = Callable[[WhisperConfig], WorkspaceApplication]
DoctorFactory = Callable[[WhisperConfig], DoctorApplication]


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
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=(
            "Reuse every valid subtitle or generate one only when none exist, then\n"
            "package selectable, non-default subtitle tracks into a verified MKV.\n"
            "All source streams are preserved without audio/video transcoding."
        ),
        epilog="""Safe workflow:
  1. Inspect without changes:
       subtitles-bridge /path/to/videos --preflight
  2. Process an unambiguous plan:
       subtitles-bridge /path/to/videos
  3. Resume only a verified output whose archive step is pending:
       subtitles-bridge /path/to/videos --resume
  4. Check runtime requirements without selecting a workspace:
       subtitles-bridge --doctor

Exit codes:
  0  completed or safely skipped
  1  failed or empty workspace
  2  user decision required; no video stages executed
  3  output published, but input archival remains pending

Safety:
  Preflight is read-only. Processing never overwrites output/ or trash/,
  verifies the MKV before publication, and treats trash/ as reversible
  quarantine.
""",
    )
    parser.add_argument(
        "directory",
        nargs="?",
        default=".",
        help=(
            "folder containing non-recursive MP4/MKV inputs and associated SRT "
            "files (default: current directory)"
        ),
    )
    parser.add_argument(
        "--doctor",
        action="store_true",
        help="check Python, FFmpeg, FFprobe, and Whisper without a workspace",
    )
    parser.add_argument(
        "--preflight",
        action="store_true",
        help="inspect associations, collisions, and the plan without changes",
    )
    parser.add_argument(
        "--audio",
        action="append",
        default=[],
        type=_audio_selection,
        metavar="SOURCE=STREAM_INDEX",
        help=(
            "resolve which audio to transcribe when a subtitle-free source has "
            "multiple candidates (repeatable)"
        ),
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
        help="re-verify a published output and retry only pending archival",
    )
    parser.add_argument(
        "--output-format",
        choices=tuple(item.value for item in OutputFormat),
        default=OutputFormat.TEXT.value,
        help="use human-readable text or automation-safe JSON Lines (default: text)",
    )
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    application_factory: ApplicationFactory = build_default_workspace_application,
    doctor_factory: DoctorFactory = build_default_doctor_application,
    write: Writer = print,
) -> int:
    arguments = build_parser().parse_args(argv)
    output_format = OutputFormat(arguments.output_format)
    reporter = JsonLinesReporter(write) if output_format is OutputFormat.JSONL else None
    try:
        config = WhisperConfig(
            model=arguments.whisper_model,
            device=arguments.whisper_device,
        )
        if arguments.doctor:
            invalid_options = (
                arguments.directory != "."
                or arguments.preflight
                or bool(arguments.audio)
                or arguments.resume
            )
            if invalid_options:
                raise ValueError(
                    "--doctor does not accept a workspace or processing options"
                )
            doctor = doctor_factory(config)
        else:
            application = application_factory(config)
    except Exception as exc:
        if reporter is None:
            write(
                format_diagnostic_fatal(exc)
                if arguments.doctor
                else format_fatal_result(exc)
            )
        else:
            reporter.fatal("doctor" if arguments.doctor else "batch", exc)
        return 1
    if arguments.doctor:
        return doctor.run(write=write, output_format=output_format)
    return application.run(
        arguments.directory,
        preflight_only=arguments.preflight,
        audio_selections=arguments.audio,
        resume=arguments.resume,
        write=write,
        output_format=output_format,
    )
