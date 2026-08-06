from pathlib import Path
import subprocess
import tempfile
import unittest

from subtitles_bridge.adapters.ffmpeg_audio import FFmpegAudioExtractor
from subtitles_bridge.errors import AudioExtractionError, StagingCollisionError
from subtitles_bridge.models import MediaStream, StreamKind


class FFmpegAudioExtractorTests(unittest.TestCase):
    def make_paths(self):
        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        root = Path(temporary_directory.name)
        source = root / "lesson.mkv"
        source.touch()
        return source, root / "selected.wav"

    def test_extracts_only_selected_global_stream_without_overwrite(self):
        source, destination = self.make_paths()
        calls = []

        def runner(command, **kwargs):
            calls.append((command, kwargs))
            Path(command[-1]).write_bytes(b"pcm")
            return subprocess.CompletedProcess(command, 0, "", "")

        FFmpegAudioExtractor("/usr/bin/ffmpeg", runner).extract(
            source,
            MediaStream(4, StreamKind.AUDIO, "aac"),
            destination,
        )

        self.assertEqual(
            calls[0][0],
            [
                "/usr/bin/ffmpeg",
                "-v",
                "error",
                "-nostdin",
                "-n",
                "-i",
                str(source),
                "-map",
                "0:4",
                "-vn",
                "-ac",
                "1",
                "-ar",
                "16000",
                "-c:a",
                "pcm_s16le",
                str(destination),
            ],
        )
        self.assertEqual(
            calls[0][1],
            {"capture_output": True, "text": True, "check": False},
        )

    def test_rejects_non_audio_and_existing_destination_before_execution(self):
        source, destination = self.make_paths()
        calls = []
        extractor = FFmpegAudioExtractor(
            runner=lambda *args, **kwargs: calls.append(args)
        )

        with self.assertRaisesRegex(AudioExtractionError, "not an audio"):
            extractor.extract(
                source,
                MediaStream(0, StreamKind.VIDEO, "h264"),
                destination,
            )
        destination.touch()
        with self.assertRaisesRegex(StagingCollisionError, "already exists"):
            extractor.extract(
                source,
                MediaStream(1, StreamKind.AUDIO, "aac"),
                destination,
            )

        self.assertEqual(calls, [])

    def test_propagates_process_launch_exit_and_missing_output_failures(self):
        source, destination = self.make_paths()
        audio = MediaStream(1, StreamKind.AUDIO, "aac")

        def missing_executable(*args, **kwargs):
            raise FileNotFoundError("ffmpeg missing")

        cases = (
            (missing_executable, "Cannot execute"),
            (
                lambda command, **kwargs: subprocess.CompletedProcess(
                    command,
                    1,
                    "",
                    "broken audio",
                ),
                "broken audio",
            ),
            (
                lambda command, **kwargs: subprocess.CompletedProcess(
                    command,
                    0,
                    "",
                    "",
                ),
                "did not create",
            ),
        )

        for runner, message in cases:
            with self.subTest(message=message):
                with self.assertRaisesRegex(AudioExtractionError, message):
                    FFmpegAudioExtractor(runner=runner).extract(
                        source,
                        audio,
                        destination,
                    )


if __name__ == "__main__":
    unittest.main()
