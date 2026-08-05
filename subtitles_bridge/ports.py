"""Typed boundaries for tools and filesystem side effects."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Protocol, runtime_checkable

from .models import MediaStream, SubtitleArtifact, VideoInventory


@runtime_checkable
class MediaProbe(Protocol):
    def inspect(self, source: Path) -> tuple[MediaStream, ...]: ...


@runtime_checkable
class SubtitleTranscriber(Protocol):
    def transcribe(
        self,
        source: Path,
        audio_stream: MediaStream,
        destination: Path,
    ) -> SubtitleArtifact: ...


@runtime_checkable
class MediaMuxer(Protocol):
    def mux(
        self,
        inventory: VideoInventory,
        subtitles: Sequence[SubtitleArtifact],
        destination: Path,
    ) -> None: ...


@runtime_checkable
class OutputVerifier(Protocol):
    def verify(
        self,
        inventory: VideoInventory,
        output: Path,
        expected_subtitles: Sequence[SubtitleArtifact],
    ) -> None: ...


@runtime_checkable
class OutputPublisher(Protocol):
    def publish(self, staged_output: Path, final_output: Path) -> None: ...


@runtime_checkable
class InputArchiver(Protocol):
    def archive(
        self,
        source: Path,
        sidecars: Sequence[Path],
        destination: Path,
    ) -> None: ...
