"""Concrete composition root for the default local media workflow."""

from __future__ import annotations

from .adapters.ffmpeg_audio import FFmpegAudioExtractor
from .adapters.ffmpeg_mux import FFmpegMediaMuxer
from .adapters.ffprobe import FFprobeMediaProbe
from .adapters.filesystem_archive import TransactionalInputArchiver
from .adapters.filesystem_publish import AtomicOutputPublisher
from .adapters.whisper import WhisperConfig, WhisperSpeechRecognizer
from .archiving import ArchivingStage
from .batch_planner import BatchPlanner
from .diagnostics import DoctorApplication, RuntimeDoctor
from .discovery import WorkspaceDiscovery
from .execution import BatchExecutor
from .muxing import MuxingStage
from .publishing import PublishingStage
from .resuming import ExistingOutputResumer
from .srt import SrtValidator
from .transcription import StagedSubtitleTranscriber, TranscriptionStage
from .verification import OutputContractVerifier, VerificationStage
from .workspace_application import WorkspaceApplication


def build_default_workspace_application(
    whisper_config: WhisperConfig | None = None,
) -> WorkspaceApplication:
    probe = FFprobeMediaProbe()
    validator = SrtValidator()
    transcriber = StagedSubtitleTranscriber(
        FFmpegAudioExtractor(),
        WhisperSpeechRecognizer(whisper_config),
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
        ExistingOutputResumer(OutputContractVerifier(probe), validator),
    )


def build_default_doctor_application(
    whisper_config: WhisperConfig | None = None,
) -> DoctorApplication:
    config = whisper_config or WhisperConfig()
    recognizer = WhisperSpeechRecognizer(config)
    return DoctorApplication(
        RuntimeDoctor(
            recognizer.verify_local_model,
            model_name=config.model,
        )
    )
