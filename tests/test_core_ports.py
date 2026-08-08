import unittest
from pathlib import Path

from subtitles_bridge.models import (
    ArchivedInputs,
    ArtifactState,
    MediaInspection,
    MediaStream,
    SpeechSegment,
    SpeechTranscript,
    StreamKind,
    SubtitleArtifact,
    SubtitleOrigin,
    SubtitleValidation,
    VerifiedOutput,
    VideoInventory,
)
from subtitles_bridge.ports import (
    AudioExtractor,
    InputArchiver,
    MediaMuxer,
    MediaProbe,
    OutputPublisher,
    OutputVerifier,
    SpeechRecognizer,
    SubtitleTranscriber,
    SubtitleValidator,
)


class FakeAdapters:
    class Probe:
        def inspect(self, source):
            return MediaInspection((MediaStream(0, StreamKind.VIDEO, "h264"),))

    class Transcriber:
        def transcribe(self, source, audio_stream, destination):
            return SubtitleArtifact(
                origin=SubtitleOrigin.GENERATED,
                state=ArtifactState.VALID,
                path=destination,
            )

    class Validator:
        def validate(self, path):
            return SubtitleValidation(True, 1, "utf-8")

    class Extractor:
        def extract(self, source, audio_stream, destination):
            return None

    class Recognizer:
        def transcribe(self, audio):
            return SpeechTranscript(
                "eng",
                (SpeechSegment(0, 1, "Hello"),),
            )

    class Muxer:
        def mux(self, inventory, subtitles, destination):
            return None

    class Verifier:
        def verify(self, inventory, output, expected_subtitles):
            return VerifiedOutput(
                inventory.source,
                output,
                MediaInspection(inventory.streams),
                tuple(expected_subtitles),
                1,
                0,
            )

    class Publisher:
        def publish(self, staged_output, final_output):
            return None

    class Archiver:
        def archive(self, source, sidecars, destination):
            originals = (source, *sidecars)
            return ArchivedInputs(
                source,
                destination,
                originals,
                tuple(destination / path.name for path in originals),
            )


class PortBoundaryTests(unittest.TestCase):
    def test_fake_adapters_satisfy_runtime_protocols(self):
        self.assertIsInstance(FakeAdapters.Probe(), MediaProbe)
        self.assertIsInstance(FakeAdapters.Validator(), SubtitleValidator)
        self.assertIsInstance(FakeAdapters.Extractor(), AudioExtractor)
        self.assertIsInstance(FakeAdapters.Recognizer(), SpeechRecognizer)
        self.assertIsInstance(FakeAdapters.Transcriber(), SubtitleTranscriber)
        self.assertIsInstance(FakeAdapters.Muxer(), MediaMuxer)
        self.assertIsInstance(FakeAdapters.Verifier(), OutputVerifier)
        self.assertIsInstance(FakeAdapters.Publisher(), OutputPublisher)
        self.assertIsInstance(FakeAdapters.Archiver(), InputArchiver)

    def test_protocols_allow_orchestration_without_external_tools(self):
        probe = FakeAdapters.Probe()
        transcriber = FakeAdapters.Transcriber()
        source = Path("lesson.mkv")
        inspection = probe.inspect(source)
        inventory = VideoInventory(source, inspection.streams)
        subtitle = transcriber.transcribe(
            source,
            MediaStream(1, StreamKind.AUDIO, "aac", language="eng"),
            Path("staging/lesson.en.srt"),
        )

        self.assertEqual(inventory.video_streams, inspection.streams)
        self.assertEqual(subtitle.origin, SubtitleOrigin.GENERATED)


if __name__ == "__main__":
    unittest.main()
