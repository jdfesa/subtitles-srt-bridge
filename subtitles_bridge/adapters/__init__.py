"""Concrete adapters for external tools."""

from .ffmpeg_audio import FFmpegAudioExtractor
from .ffprobe import FFprobeMediaProbe
from .whisper import WhisperConfig, WhisperSpeechRecognizer

__all__ = [
    "FFmpegAudioExtractor",
    "FFprobeMediaProbe",
    "WhisperConfig",
    "WhisperSpeechRecognizer",
]
