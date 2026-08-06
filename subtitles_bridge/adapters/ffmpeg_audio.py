"""FFmpeg adapter for extracting exactly one selected audio stream."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
import subprocess

from ..errors import AudioExtractionError, StagingCollisionError
from ..models import MediaStream, StreamKind


Runner = Callable[..., subprocess.CompletedProcess[str]]


class FFmpegAudioExtractor:
    def __init__(
        self,
        executable: str = "ffmpeg",
        runner: Runner = subprocess.run,
    ) -> None:
        self.executable = executable
        self.runner = runner

    def extract(
        self,
        source: Path,
        audio_stream: MediaStream,
        destination: Path,
    ) -> None:
        if audio_stream.kind is not StreamKind.AUDIO:
            raise AudioExtractionError(
                f"Stream #{audio_stream.index} is not an audio stream"
            )
        if destination.exists():
            raise StagingCollisionError(
                f"Temporary audio destination already exists: {destination}"
            )

        command = [
            self.executable,
            "-v",
            "error",
            "-nostdin",
            "-n",
            "-i",
            str(source),
            "-map",
            f"0:{audio_stream.index}",
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-c:a",
            "pcm_s16le",
            str(destination),
        ]
        try:
            result = self.runner(
                command,
                capture_output=True,
                text=True,
                check=False,
            )
        except OSError as exc:
            raise AudioExtractionError(
                f"Cannot execute FFmpeg '{self.executable}': {exc}"
            ) from exc

        if result.returncode != 0:
            message = result.stderr.strip() or (
                f"FFmpeg could not extract audio stream #{audio_stream.index}"
            )
            raise AudioExtractionError(message)
        if not destination.is_file() or destination.stat().st_size == 0:
            raise AudioExtractionError(
                f"FFmpeg did not create a usable temporary audio file: {destination}"
            )
