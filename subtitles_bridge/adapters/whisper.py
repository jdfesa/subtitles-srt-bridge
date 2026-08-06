"""Lazy, local-only adapter for the openai-whisper Python API."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from hashlib import sha256
import importlib
import os
from pathlib import Path
import re
import sys
from typing import Any
from urllib.parse import urlparse
import wave

from ..errors import TranscriptionDependencyError, TranscriptionError
from ..languages import normalize_trusted_language
from ..models import SpeechSegment, SpeechTranscript


ModuleLoader = Callable[[str], Any]
AudioLoader = Callable[[Path], Any]


@dataclass(frozen=True, slots=True)
class WhisperConfig:
    model: str = "small"
    device: str | None = None
    language: str | None = None
    cache_directory: Path | None = None

    def __post_init__(self) -> None:
        if not self.model.strip():
            raise ValueError("Whisper model cannot be empty")
        if self.device is not None and not self.device.strip():
            raise ValueError("Whisper device cannot be empty")
        if self.language is not None and not self.language.strip():
            raise ValueError("Whisper language cannot be empty")


class WhisperSpeechRecognizer:
    def __init__(
        self,
        config: WhisperConfig | None = None,
        *,
        module_loader: ModuleLoader = importlib.import_module,
        python_executable: str = sys.executable,
        audio_loader: AudioLoader | None = None,
    ) -> None:
        self.config = config or WhisperConfig()
        self.module_loader = module_loader
        self.python_executable = python_executable
        self.audio_loader = audio_loader
        self._model: Any | None = None

    def transcribe(self, audio: Path) -> SpeechTranscript:
        try:
            samples = self._load_audio(audio)
            model = self._model_instance()
            transcribe_options: dict[str, Any] = {"task": "transcribe"}
            if self.config.language is not None:
                transcribe_options["language"] = self.config.language
            result = model.transcribe(samples, **transcribe_options)
        except TranscriptionDependencyError:
            raise
        except Exception as exc:
            raise TranscriptionError(f"Whisper transcription failed: {exc}") from exc

        return self._parse_result(result)

    def verify_local_model(self) -> Path:
        """Resolve and checksum the configured checkpoint without loading it."""
        return self._resolve_checkpoint(self._load_whisper_module())

    def _load_audio(self, audio: Path) -> Any:
        if self.audio_loader is not None:
            return self.audio_loader(audio)
        try:
            numpy = self.module_loader("numpy")
        except ImportError as exc:
            command = f'"{self.python_executable}" -m pip install numpy'
            raise TranscriptionDependencyError(
                "NumPy is not installed in the active Python environment. "
                f"Install it with: {command}"
            ) from exc

        try:
            with wave.open(str(audio), "rb") as source:
                if (
                    source.getnchannels() != 1
                    or source.getsampwidth() != 2
                    or source.getframerate() != 16_000
                    or source.getcomptype() != "NONE"
                ):
                    raise TranscriptionError(
                        "Temporary audio must be uncompressed 16 kHz mono PCM16"
                    )
                frames = source.readframes(source.getnframes())
        except (OSError, wave.Error) as exc:
            raise TranscriptionError(f"Cannot read temporary PCM audio: {exc}") from exc

        return numpy.frombuffer(frames, dtype="<i2").astype(numpy.float32) / 32768.0

    def _model_instance(self) -> Any:
        if self._model is not None:
            return self._model
        whisper_module = self._load_whisper_module()
        checkpoint = self._resolve_checkpoint(whisper_module)
        load_options: dict[str, Any] = {}
        if self.config.device is not None:
            load_options["device"] = self.config.device
        self._model = whisper_module.load_model(str(checkpoint), **load_options)
        if self._model is None:
            raise TranscriptionDependencyError("Whisper returned no loaded model")
        return self._model

    def _load_whisper_module(self) -> Any:
        try:
            return self.module_loader("whisper")
        except ImportError as exc:
            command = (
                f'"{self.python_executable}" -m pip install openai-whisper'
            )
            raise TranscriptionDependencyError(
                "Whisper is not installed in the active Python environment "
                f"({self.python_executable}). Install it with: {command}"
            ) from exc

    def _resolve_checkpoint(self, whisper_module: Any) -> Path:
        local_model = Path(self.config.model).expanduser()
        if local_model.is_file():
            return local_model.resolve()

        model_urls = getattr(whisper_module, "_MODELS", None)
        if not isinstance(model_urls, dict) or self.config.model not in model_urls:
            raise TranscriptionDependencyError(
                f"Whisper model is not a local file or known model: {self.config.model}"
            )

        url = str(model_urls[self.config.model])
        checkpoint = self._cache_directory() / Path(urlparse(url).path).name
        if not checkpoint.is_file():
            raise TranscriptionDependencyError(self._missing_model_message(checkpoint))

        expected_checksum = url.rstrip("/").split("/")[-2].casefold()
        if re.fullmatch(r"[0-9a-f]{64}", expected_checksum) is None:
            raise TranscriptionDependencyError(
                "Whisper model metadata does not contain a trusted checksum"
            )
        if self._sha256(checkpoint) != expected_checksum:
            raise TranscriptionDependencyError(
                "Cached Whisper model failed checksum validation and will not be "
                f"downloaded automatically: {checkpoint}"
            )
        return checkpoint.resolve()

    def _cache_directory(self) -> Path:
        if self.config.cache_directory is not None:
            return self.config.cache_directory.expanduser()
        default_cache = Path.home() / ".cache"
        cache_root = Path(os.getenv("XDG_CACHE_HOME", str(default_cache)))
        return cache_root / "whisper"

    def _missing_model_message(self, checkpoint: Path) -> str:
        bootstrap = (
            "import whisper; "
            f"whisper.load_model({self.config.model!r})"
        )
        command = f'"{self.python_executable}" -c "{bootstrap}"'
        return (
            f"Whisper model is not available locally at {checkpoint}. "
            "Preload it explicitly when network access is acceptable with: "
            f"{command}"
        )

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = sha256()
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def _parse_result(self, raw_result: Any) -> SpeechTranscript:
        if not isinstance(raw_result, dict):
            raise TranscriptionError("Whisper returned an invalid result")
        raw_segments = raw_result.get("segments")
        if not isinstance(raw_segments, list):
            raise TranscriptionError("Whisper result does not contain segments")

        segments: list[SpeechSegment] = []
        try:
            for raw_segment in raw_segments:
                if not isinstance(raw_segment, dict):
                    raise ValueError("segment must be an object")
                if not isinstance(raw_segment.get("text"), str):
                    raise ValueError("segment text must be a string")
                segments.append(
                    SpeechSegment(
                        start_seconds=float(raw_segment["start"]),
                        end_seconds=float(raw_segment["end"]),
                        text=raw_segment["text"],
                    )
                )
        except (KeyError, TypeError, ValueError) as exc:
            raise TranscriptionError(
                f"Whisper returned an invalid segment: {exc}"
            ) from exc

        detected_language = raw_result.get("language") or self.config.language
        return SpeechTranscript(
            normalize_trusted_language(
                str(detected_language) if detected_language is not None else None
            ),
            tuple(segments),
        )
