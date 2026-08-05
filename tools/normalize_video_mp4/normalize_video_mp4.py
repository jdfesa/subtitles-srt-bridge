#!/usr/bin/env python3
"""Normalize videos to MP4 and add selectable subtitle tracks."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import unicodedata


VIDEO_EXTENSIONS = {
    ".3gp",
    ".avi",
    ".flv",
    ".m4v",
    ".mkv",
    ".mov",
    ".mp4",
    ".mpeg",
    ".mpg",
    ".webm",
    ".wmv",
}

SUBTITLE_EXTENSIONS = {
    ".ass",
    ".srt",
    ".ssa",
    ".vtt",
}

LANGUAGE_TOKENS = {
    "ar": ("ara", "Arabic"),
    "arabic": ("ara", "Arabic"),
    "castellano": ("spa", "Spanish"),
    "de": ("deu", "German"),
    "deu": ("deu", "German"),
    "en": ("eng", "English"),
    "eng": ("eng", "English"),
    "english": ("eng", "English"),
    "es": ("spa", "Spanish"),
    "espanol": ("spa", "Spanish"),
    "esp": ("spa", "Spanish"),
    "ingles": ("eng", "English"),
    "fr": ("fra", "French"),
    "fra": ("fra", "French"),
    "fre": ("fra", "French"),
    "french": ("fra", "French"),
    "ger": ("deu", "German"),
    "german": ("deu", "German"),
    "ita": ("ita", "Italian"),
    "italian": ("ita", "Italian"),
    "it": ("ita", "Italian"),
    "japanese": ("jpn", "Japanese"),
    "jp": ("jpn", "Japanese"),
    "jpn": ("jpn", "Japanese"),
    "pt": ("por", "Portuguese"),
    "por": ("por", "Portuguese"),
    "portuguese": ("por", "Portuguese"),
    "spa": ("spa", "Spanish"),
    "spanish": ("spa", "Spanish"),
}


class ScriptError(Exception):
    """Expected error that should be shown without a traceback."""


@dataclass(frozen=True)
class SubtitleTrack:
    path: Path
    language: str
    title: str
    charenc: str | None


@dataclass(frozen=True)
class CodecPlan:
    args: list[str]
    label: str


def ascii_fold(value: str) -> str:
    folded = unicodedata.normalize("NFKD", value)
    return folded.encode("ascii", "ignore").decode("ascii").lower()


def tokenise_name(path: Path) -> list[str]:
    return [token for token in re.split(r"[^a-z0-9]+", ascii_fold(path.stem)) if token]


def require_tool(name: str) -> str:
    tool_path = shutil.which(name)
    if tool_path is None:
        raise ScriptError(
            f"Missing required tool: {name}. Install ffmpeg first, for example: "
            "brew install ffmpeg"
        )
    return tool_path


def resolve_existing_path(raw_path: str, label: str) -> Path:
    path = Path(raw_path).expanduser().resolve()
    if not path.exists():
        raise ScriptError(f"{label} does not exist: {path}")
    return path


def is_sample_file(path: Path) -> bool:
    return "sample" in tokenise_name(path)


def is_normalized_output_file(path: Path) -> bool:
    return path.suffix.lower() == ".mp4" and "normalized" in tokenise_name(path)


def resolve_video_source(raw_source: str) -> tuple[Path, str | None]:
    source = resolve_existing_path(raw_source, "Source")
    if source.is_file():
        return source, None

    if not source.is_dir():
        raise ScriptError(f"Source is not a file or folder: {source}")

    candidates = sorted(
        path
        for path in source.iterdir()
        if path.is_file() and path.suffix.lower() in VIDEO_EXTENSIONS
    )
    if not candidates:
        raise ScriptError(f"No video files found inside folder: {source}")

    non_sample_candidates = [path for path in candidates if not is_sample_file(path)]
    if non_sample_candidates:
        candidates = non_sample_candidates

    non_normalized_candidates = [
        path for path in candidates if not is_normalized_output_file(path)
    ]
    if non_normalized_candidates:
        candidates = non_normalized_candidates

    non_mp4_candidates = [path for path in candidates if path.suffix.lower() != ".mp4"]
    if non_mp4_candidates:
        candidates = non_mp4_candidates

    selected = max(candidates, key=lambda path: path.stat().st_size)
    note = f"Source is a folder; selected largest video: {selected}"
    return selected.resolve(), note


def discover_subtitle_paths(video_path: Path, raw_subtitles: list[str]) -> list[Path]:
    if raw_subtitles:
        subtitles = [
            resolve_existing_path(raw_subtitle, "Subtitle")
            for raw_subtitle in raw_subtitles
        ]
    else:
        subtitles = sorted(
            path.resolve()
            for path in video_path.parent.iterdir()
            if path.is_file() and path.suffix.lower() in SUBTITLE_EXTENSIONS
        )

    unique_subtitles: list[Path] = []
    seen: set[Path] = set()
    for subtitle in subtitles:
        if subtitle in seen:
            continue
        seen.add(subtitle)
        unique_subtitles.append(subtitle)

    return unique_subtitles


def detect_subtitle_charenc(path: Path) -> str | None:
    if path.suffix.lower() == ".vtt":
        return None

    data = path.read_bytes()
    if data.startswith((b"\xef\xbb\xbf", b"\xff\xfe", b"\xfe\xff")):
        return None

    try:
        data.decode("utf-8")
        return None
    except UnicodeDecodeError:
        pass

    try:
        data.decode("cp1252")
        return "CP1252"
    except UnicodeDecodeError:
        return "ISO-8859-1"


def guess_subtitle_language(path: Path) -> tuple[str, str]:
    for token in tokenise_name(path):
        if token in LANGUAGE_TOKENS:
            return LANGUAGE_TOKENS[token]
    return "und", path.stem


def normalize_language_code(raw_language: str) -> str:
    folded = ascii_fold(raw_language.strip())
    if folded in LANGUAGE_TOKENS:
        return LANGUAGE_TOKENS[folded][0]
    if re.fullmatch(r"[a-z]{3}", folded):
        return folded
    raise ScriptError(
        f"Language must be a known 2-letter or 3-letter code, got: {raw_language}"
    )


def pick_override(values: list[str] | None, index: int, default: str) -> str:
    if not values:
        return default
    if index < len(values):
        return values[index]
    if len(values) == 1:
        return values[0]
    return default


def build_subtitle_tracks(
    paths: list[Path],
    languages: list[str] | None,
    titles: list[str] | None,
) -> list[SubtitleTrack]:
    tracks: list[SubtitleTrack] = []

    for index, path in enumerate(paths):
        guessed_language, guessed_title = guess_subtitle_language(path)
        raw_language = pick_override(languages, index, guessed_language)
        language = normalize_language_code(raw_language)
        title = pick_override(titles, index, guessed_title)
        tracks.append(
            SubtitleTrack(
                path=path,
                language=language,
                title=title,
                charenc=detect_subtitle_charenc(path),
            )
        )

    return tracks


def default_output_path(video_path: Path) -> Path:
    if video_path.suffix.lower() == ".mp4":
        return video_path.with_name(f"{video_path.stem}.normalized.mp4")
    return video_path.with_suffix(".mp4")


def resolve_output_path(raw_output: str | None, video_path: Path) -> Path:
    if raw_output is None:
        if is_normalized_output_file(video_path):
            raise ScriptError(
                "Input already looks like a normalized output. "
                "Pass the original video or choose an explicit --output path."
            )
        output = default_output_path(video_path)
    else:
        output = Path(raw_output).expanduser()
        if not output.is_absolute():
            output = Path.cwd() / output
        output = output.resolve()

    if output.suffix.lower() != ".mp4":
        raise ScriptError(f"Output must end in .mp4: {output}")
    if not output.parent.exists():
        raise ScriptError(f"Output folder does not exist: {output.parent}")
    if output.resolve() == video_path.resolve():
        raise ScriptError("Output path cannot be the same file as the input video")
    return output


def probe_media(ffprobe: str, path: Path) -> dict:
    command = [
        ffprobe,
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_streams",
        str(path),
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise ScriptError(result.stderr.strip() or f"ffprobe failed for {path}")
    return json.loads(result.stdout)


def first_video_stream(probe: dict) -> dict:
    for stream in probe.get("streams", []):
        if stream.get("codec_type") == "video":
            return stream
    raise ScriptError("Input has no video stream")


def audio_streams(probe: dict) -> list[dict]:
    return [
        stream
        for stream in probe.get("streams", [])
        if stream.get("codec_type") == "audio"
    ]


def subtitle_streams(probe: dict) -> list[dict]:
    return [
        stream
        for stream in probe.get("streams", [])
        if stream.get("codec_type") == "subtitle"
    ]


def stream_language(stream: dict) -> str:
    raw_language = str(stream.get("tags", {}).get("language") or "und")
    folded = ascii_fold(raw_language.strip())
    if folded in LANGUAGE_TOKENS:
        return LANGUAGE_TOKENS[folded][0]
    return folded


def parse_default_audio(value: str | None, streams: list[dict]) -> int | None:
    if value is None:
        return None

    folded = ascii_fold(value.strip())
    if folded in {"none", "off", "no", "0"}:
        return -1
    if folded == "first":
        if not streams:
            raise ScriptError("--default-audio first requires at least one audio track")
        return 0

    try:
        number = int(folded)
    except ValueError:
        language = normalize_language_code(folded)
        for index, stream in enumerate(streams):
            if stream_language(stream) == language:
                return index
        raise ScriptError(f"No audio track found for language: {value}")

    if number < 1 or number > len(streams):
        raise ScriptError(
            f"--default-audio {number} is out of range; "
            f"there are {len(streams)} audio tracks"
        )
    return number - 1


def build_video_codec_plan(
    args: argparse.Namespace,
    probe: dict,
    video_path: Path,
) -> CodecPlan:
    stream = first_video_stream(probe)
    codec_name = stream.get("codec_name", "unknown")
    pixel_format = stream.get("pix_fmt")
    is_mp4_input = video_path.suffix.lower() == ".mp4"

    should_copy = args.video_codec == "copy" or (
        args.video_codec == "auto"
        and (
            is_mp4_input
            or (codec_name == "h264" and pixel_format in {None, "yuv420p", "yuvj420p"})
        )
    )
    if should_copy:
        return CodecPlan(["-c:v", "copy"], f"copy ({codec_name})")

    return CodecPlan(
        [
            "-c:v",
            "libx264",
            "-preset",
            args.preset,
            "-crf",
            str(args.crf),
            "-pix_fmt",
            "yuv420p",
        ],
        f"libx264 from {codec_name}",
    )


def default_audio_bitrate(streams: list[dict]) -> str:
    max_channels = 2
    for stream in streams:
        try:
            max_channels = max(max_channels, int(stream.get("channels") or 2))
        except (TypeError, ValueError):
            continue
    return "384k" if max_channels >= 6 else "192k"


def build_audio_codec_plan(
    args: argparse.Namespace,
    probe: dict,
    video_path: Path,
) -> CodecPlan | None:
    streams = audio_streams(probe)
    if not streams:
        return None

    codec_names = [stream.get("codec_name", "unknown") for stream in streams]
    is_mp4_input = video_path.suffix.lower() == ".mp4"
    should_copy = args.audio_codec == "copy" or (
        args.audio_codec == "auto"
        and (is_mp4_input or all(codec_name == "aac" for codec_name in codec_names))
    )
    if should_copy:
        return CodecPlan(["-c:a", "copy"], f"copy ({', '.join(codec_names)})")

    bitrate = args.audio_bitrate or default_audio_bitrate(streams)
    return CodecPlan(["-c:a", "aac", "-b:a", bitrate], f"aac {bitrate}")


def parse_default_subtitle(value: str, subtitle_count: int) -> int | None:
    folded = ascii_fold(value.strip())
    if folded in {"none", "off", "no", "0"}:
        return None
    if folded == "first":
        if subtitle_count == 0:
            return None
        return 0

    try:
        number = int(folded)
    except ValueError as exc:
        raise ScriptError(
            "--default-subtitle must be 'none', 'first', or a 1-based subtitle number"
        ) from exc

    if number < 1 or number > subtitle_count:
        raise ScriptError(
            f"--default-subtitle {number} is out of range; "
            f"there are {subtitle_count} subtitle tracks"
        )
    return number - 1


def build_ffmpeg_command(
    ffmpeg: str,
    video_path: Path,
    output_path: Path,
    subtitles: list[SubtitleTrack],
    video_plan: CodecPlan,
    audio_plan: CodecPlan | None,
    embedded_subtitles: list[dict],
    default_audio: int | None,
    default_subtitle: int | None,
    overwrite: bool,
) -> list[str]:
    command = [ffmpeg, "-hide_banner", "-y" if overwrite else "-n", "-i", str(video_path)]

    for subtitle in subtitles:
        if subtitle.charenc is not None:
            command.extend(["-sub_charenc", subtitle.charenc])
        command.extend(["-i", str(subtitle.path)])

    command.extend(["-map", "0:v:0", "-map", "0:a?"])
    if embedded_subtitles:
        command.extend(["-map", "0:s?"])
    for subtitle_index in range(len(subtitles)):
        command.extend(["-map", f"{subtitle_index + 1}:0"])

    command.extend(video_plan.args)
    if audio_plan is not None:
        command.extend(audio_plan.args)
    total_subtitle_count = len(embedded_subtitles) + len(subtitles)
    if total_subtitle_count:
        command.extend(["-c:s", "mov_text"])

    command.extend(["-map_metadata", "0", "-map_chapters", "0"])

    if default_audio is not None:
        command.extend(["-disposition:a", "0"])
        if default_audio >= 0:
            command.extend([f"-disposition:a:{default_audio}", "default"])

    if total_subtitle_count:
        command.extend(["-disposition:s", "0"])

    embedded_count = len(embedded_subtitles)
    for subtitle_index, subtitle in enumerate(subtitles):
        output_subtitle_index = embedded_count + subtitle_index
        command.extend(
            [
                f"-metadata:s:s:{output_subtitle_index}",
                f"language={subtitle.language}",
                f"-metadata:s:s:{output_subtitle_index}",
                f"title={subtitle.title}",
                f"-metadata:s:s:{output_subtitle_index}",
                f"handler_name={subtitle.title}",
            ]
        )
        disposition = "default" if subtitle_index == default_subtitle else "0"
        command.extend([f"-disposition:s:{output_subtitle_index}", disposition])

    command.extend(["-movflags", "+faststart", str(output_path)])
    return command


def print_plan(
    video_path: Path,
    output_path: Path,
    subtitles: list[SubtitleTrack],
    video_plan: CodecPlan,
    audio_plan: CodecPlan | None,
    embedded_subtitles: list[dict],
    default_audio: int | None,
    default_subtitle: int | None,
    note: str | None,
) -> None:
    if note:
        print(note)
    print(f"Input video: {video_path}")
    print(f"Output MP4:  {output_path}")
    print(f"Video:      {video_plan.label}")
    audio_label = audio_plan.label if audio_plan else "no audio streams"
    if default_audio is not None:
        audio_label += (
            ", no default" if default_audio < 0 else f", track {default_audio + 1} default"
        )
    print(f"Audio:      {audio_label}")

    if embedded_subtitles:
        print(f"Embedded subtitles preserved: {len(embedded_subtitles)} (disabled by default)")

    if subtitles:
        print("Subtitles:")
        for index, subtitle in enumerate(subtitles, start=1):
            default_note = " default" if default_subtitle == index - 1 else ""
            encoding_note = subtitle.charenc or "UTF-8"
            print(
                f"  {index}. {subtitle.path.name} "
                f"[{subtitle.language}, {subtitle.title}, {encoding_note}{default_note}]"
            )
    else:
        print("Subtitles:  none")
    print()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Convert or remux a video into an MP4 file and add external subtitles "
            "as selectable tracks for players such as VLC."
        )
    )
    parser.add_argument(
        "source",
        help="Video file, or a folder containing the video. Folders use the largest non-sample video.",
    )
    parser.add_argument(
        "subtitles",
        nargs="*",
        help="Subtitle files. If omitted, subtitle files next to the video are included.",
    )
    parser.add_argument(
        "-o",
        "--output",
        help="Output .mp4 path. Defaults to the video name with .mp4.",
    )
    parser.add_argument(
        "-l",
        "--language",
        action="append",
        help=(
            "Subtitle language code such as spa, eng, es, or en. Repeat for "
            "multiple subtitles. Guessed from filenames when omitted."
        ),
    )
    parser.add_argument(
        "--title",
        action="append",
        help="Subtitle title shown by players. Repeat for multiple subtitles.",
    )
    parser.add_argument(
        "--default-subtitle",
        default="none",
        help="Subtitle enabled by default: none, first, or a 1-based subtitle number. Defaults to none.",
    )
    parser.add_argument(
        "--default-audio",
        help=(
            "Audio enabled by default: a language such as eng/en, first, none, "
            "or a 1-based audio track number. When omitted, existing dispositions are kept."
        ),
    )
    parser.add_argument(
        "--preserve-embedded-subtitles",
        action="store_true",
        help=(
            "Keep embedded subtitle tracks, converting them to mov_text for MP4. "
            "All embedded subtitles are disabled by default."
        ),
    )
    parser.add_argument(
        "--video-codec",
        choices=("auto", "copy", "h264"),
        default="auto",
        help="auto copies compatible H.264 and otherwise encodes H.264. Defaults to auto.",
    )
    parser.add_argument(
        "--audio-codec",
        choices=("auto", "copy", "aac"),
        default="auto",
        help="auto copies AAC and otherwise encodes AAC. Defaults to auto.",
    )
    parser.add_argument(
        "--crf",
        type=int,
        default=20,
        help="H.264 quality when encoding video. Lower is larger/better. Defaults to 20.",
    )
    parser.add_argument(
        "--preset",
        default="medium",
        help="x264 encoding preset when encoding video. Defaults to medium.",
    )
    parser.add_argument(
        "--audio-bitrate",
        help="AAC bitrate when encoding audio, for example 192k or 384k.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace the output file if it already exists.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the ffmpeg command without creating the output file.",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    try:
        ffmpeg = require_tool("ffmpeg")
        ffprobe = require_tool("ffprobe")
        video_path, note = resolve_video_source(args.source)
        subtitle_paths = discover_subtitle_paths(video_path, args.subtitles)
        subtitles = build_subtitle_tracks(subtitle_paths, args.language, args.title)
        output_path = resolve_output_path(args.output, video_path)
        default_subtitle = parse_default_subtitle(
            args.default_subtitle,
            len(subtitles),
        )

        if output_path.exists() and not args.overwrite:
            raise ScriptError(
                f"Output already exists: {output_path}\n"
                "Use --overwrite or choose another path with --output."
            )

        probe = probe_media(ffprobe, video_path)
        embedded_subtitles = (
            subtitle_streams(probe) if args.preserve_embedded_subtitles else []
        )
        default_audio = parse_default_audio(args.default_audio, audio_streams(probe))
        video_plan = build_video_codec_plan(args, probe, video_path)
        audio_plan = build_audio_codec_plan(args, probe, video_path)
        command = build_ffmpeg_command(
            ffmpeg=ffmpeg,
            video_path=video_path,
            output_path=output_path,
            subtitles=subtitles,
            video_plan=video_plan,
            audio_plan=audio_plan,
            embedded_subtitles=embedded_subtitles,
            default_audio=default_audio,
            default_subtitle=default_subtitle,
            overwrite=args.overwrite,
        )

        print_plan(
            video_path=video_path,
            output_path=output_path,
            subtitles=subtitles,
            video_plan=video_plan,
            audio_plan=audio_plan,
            embedded_subtitles=embedded_subtitles,
            default_audio=default_audio,
            default_subtitle=default_subtitle,
            note=note,
        )
        print("Command:")
        print(shlex.join(command))

        if args.dry_run:
            return 0

        print()
        sys.stdout.flush()
        result = subprocess.run(command, check=False)
        if result.returncode != 0:
            return result.returncode

        print()
        print(f"Done: {output_path}")
        return 0
    except ScriptError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
