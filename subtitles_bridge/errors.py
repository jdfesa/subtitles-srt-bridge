"""Project-specific errors that callers can present without a traceback."""


class SubtitleBridgeError(Exception):
    """Base class for expected workflow errors."""


class InputPathError(SubtitleBridgeError):
    """The selected input directory is missing or invalid."""


class SourceVideoError(SubtitleBridgeError):
    """A candidate video cannot be managed by the selected workspace."""


class MediaInspectionError(SubtitleBridgeError):
    """FFprobe could not produce a usable media inventory."""
