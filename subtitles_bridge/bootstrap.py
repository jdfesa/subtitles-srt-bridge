"""Concrete composition root for the default local media workflow."""

from __future__ import annotations

from .adapters.ffmpeg_audio import FFmpegAudioExtractor
from .adapters.ffmpeg_mux import FFmpegMediaMuxer
from .adapters.ffprobe import FFprobeMediaProbe
from .adapters.filesystem_archive import TransactionalInputArchiver
from .adapters.filesystem_publish import AtomicOutputPublisher
from .adapters.whisper import WhisperSpeechRecognizer
from .archiving import ArchivingStage
from .batch_planner import BatchPlanner
from .discovery import WorkspaceDiscovery
from .execution import BatchExecutor
from .muxing import MuxingStage
from .publishing import PublishingStage
from .srt import SrtValidator
from .transcription import StagedSubtitleTranscriber, TranscriptionStage
from .verification import OutputContractVerifier, VerificationStage
from .workspace_application import WorkspaceApplication


def build_default_workspace_application() -> WorkspaceApplication:
    probe = FFprobeMediaProbe()
    validator = SrtValidator()
    transcriber = StagedSubtitleTranscriber(
        FFmpegAudioExtractor(),
        WhisperSpeechRecognizer(),
        validator,
    )
    executor = BatchExecutor(
        TranscriptionStage(transcriber),
        MuxingStage(FFmpegMediaMuxer()),
        VerificationStage(OutputContractVerifier(probe)),
        PublishingStage(AtomicOutputPublisher()),
        ArchivingStage(TransactionalInputArchiver()),
    )
    return WorkspaceApplication(
        WorkspaceDiscovery(probe, validator),
        BatchPlanner(),
        executor,
    )
