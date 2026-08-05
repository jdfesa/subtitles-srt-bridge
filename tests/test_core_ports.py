from pathlib import Path
import unittest

from subtitles_bridge.models import (
    ArtifactState,
    MediaStream,
    StreamKind,
    SubtitleArtifact,
    SubtitleOrigin,
    VideoInventory,
)
from subtitles_bridge.ports import (
    InputArchiver,
    MediaMuxer,
    MediaProbe,
    OutputPublisher,
    OutputVerifier,
    SubtitleTranscriber,
)


class FakeAdapters:
    class Probe:
        def inspect(self, source):
            return (MediaStream(0, StreamKind.VIDEO, "h264"),)

    class Transcriber:
        def transcribe(self, source, audio_stream, destination):
            return SubtitleArtifact(
                origin=SubtitleOrigin.GENERATED,
                state=ArtifactState.VALID,
                path=destination,
            )

    class Muxer:
        def mux(self, inventory, subtitles, destination):
            return None

    class Verifier:
        def verify(self, inventory, output, expected_subtitles):
            return None

    class Publisher:
        def publish(self, staged_output, final_output):
            return None

    class Archiver:
        def archive(self, source, sidecars, destination):
            return None


class PortBoundaryTests(unittest.TestCase):
    def test_fake_adapters_satisfy_runtime_protocols(self):
        self.assertIsInstance(FakeAdapters.Probe(), MediaProbe)
        self.assertIsInstance(FakeAdapters.Transcriber(), SubtitleTranscriber)
        self.assertIsInstance(FakeAdapters.Muxer(), MediaMuxer)
        self.assertIsInstance(FakeAdapters.Verifier(), OutputVerifier)
        self.assertIsInstance(FakeAdapters.Publisher(), OutputPublisher)
        self.assertIsInstance(FakeAdapters.Archiver(), InputArchiver)

    def test_protocols_allow_orchestration_without_external_tools(self):
        probe = FakeAdapters.Probe()
        transcriber = FakeAdapters.Transcriber()
        source = Path("lesson.mkv")
        streams = probe.inspect(source)
        inventory = VideoInventory(source, streams)
        subtitle = transcriber.transcribe(
            source,
            MediaStream(1, StreamKind.AUDIO, "aac", language="eng"),
            Path("staging/lesson.en.srt"),
        )

        self.assertEqual(inventory.video_streams, streams)
        self.assertEqual(subtitle.origin, SubtitleOrigin.GENERATED)


if __name__ == "__main__":
    unittest.main()
