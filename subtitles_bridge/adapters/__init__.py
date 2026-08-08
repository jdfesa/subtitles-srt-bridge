"""Concrete adapters for external tools."""

from .ffmpeg_audio import FFmpegAudioExtractor
from .ffmpeg_mux import FFmpegMediaMuxer, build_ffmpeg_mux_command
from .ffprobe import FFprobeMediaProbe
from .filesystem_archive import TransactionalInputArchiver
from .filesystem_publish import AtomicOutputPublisher
from .whisper import WhisperConfig, WhisperSpeechRecognizer

__all__ = [
    "AtomicOutputPublisher",
    "FFmpegAudioExtractor",
    "FFmpegMediaMuxer",
    "FFprobeMediaProbe",
    "WhisperConfig",
    "WhisperSpeechRecognizer",
    "TransactionalInputArchiver",
    "build_ffmpeg_mux_command",
]
