"""Concrete adapters for external tools."""

from .ffmpeg_audio import FFmpegAudioExtractor
from .ffmpeg_mux import FFmpegMediaMuxer, build_ffmpeg_mux_command
from .ffprobe import FFprobeMediaProbe
from .whisper import WhisperConfig, WhisperSpeechRecognizer

__all__ = [
    "FFmpegAudioExtractor",
    "FFmpegMediaMuxer",
    "FFprobeMediaProbe",
    "WhisperConfig",
    "WhisperSpeechRecognizer",
    "build_ffmpeg_mux_command",
]
