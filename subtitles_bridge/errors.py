"""Project-specific errors that callers can present without a traceback."""


class SubtitleBridgeError(Exception):
    """Base class for expected workflow errors."""


class InputPathError(SubtitleBridgeError):
    """The selected input directory is missing or invalid."""


class SourceVideoError(SubtitleBridgeError):
    """A candidate video cannot be managed by the selected workspace."""


class MediaInspectionError(SubtitleBridgeError):
    """FFprobe could not produce a usable media inventory."""


class PlanningError(SubtitleBridgeError):
    """The supplied planning inputs are inconsistent or duplicated."""


class TranscriptionError(SubtitleBridgeError):
    """The planned subtitle transcription could not be completed safely."""


class TranscriptionDependencyError(TranscriptionError):
    """A local Whisper or FFmpeg dependency is missing or unusable."""


class AudioExtractionError(TranscriptionError):
    """The selected audio stream could not be extracted to staging."""


class StagingCollisionError(TranscriptionError):
    """A staging path is already occupied and cannot be overwritten."""


class GeneratedSubtitleError(TranscriptionError):
    """Whisper output did not produce a valid reusable SRT."""


class MuxingError(SubtitleBridgeError):
    """The planned MKV remux could not be completed safely."""


class MuxingCollisionError(MuxingError):
    """A staged MKV path is occupied and cannot be overwritten."""
