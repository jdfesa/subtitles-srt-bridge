import tempfile
import unittest
from pathlib import Path

from subtitles_bridge.batch_planner import BatchPlanner
from subtitles_bridge.errors import (
    AudioExtractionError,
    GeneratedSubtitleError,
    StagingCollisionError,
    TranscriptionError,
)
from subtitles_bridge.integrity import subtitle_sha256
from subtitles_bridge.models import (
    ArtifactState,
    DiscoveryIssue,
    DiscoveryIssueKind,
    DiscoveryResult,
    MediaStream,
    SpeechSegment,
    SpeechTranscript,
    StreamKind,
    SubtitleArtifact,
    SubtitleOrigin,
    SubtitleValidation,
    VideoInventory,
)
from subtitles_bridge.paths import WorkspacePaths
from subtitles_bridge.srt import SrtValidator
from subtitles_bridge.transcription import (
    StagedSubtitleTranscriber,
    TranscriptionStage,
    render_srt,
)


class FakeExtractor:
    def __init__(self, error=None):
        self.error = error
        self.calls = []

    def extract(self, source, audio_stream, destination):
        self.calls.append((source, audio_stream, destination))
        destination.write_bytes(b"pcm")
        if self.error is not None:
            raise self.error


class FakeRecognizer:
    def __init__(self, transcript=None, error=None):
        self.transcript = transcript
        self.error = error
        self.calls = []

    def transcribe(self, audio):
        self.calls.append(audio)
        if self.error is not None:
            raise self.error
        return self.transcript


class StagedSubtitleTranscriberTests(unittest.TestCase):
    def make_workspace(self):
        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        root = Path(temporary_directory.name)
        source = root / "lesson.mkv"
        source.write_bytes(b"source-media")
        paths = WorkspacePaths.from_directory(root)
        destination = paths.generated_subtitle_target(source)
        temporary_audio = paths.staging_directory / ".selected.wav"
        return root, source.resolve(), paths, destination, temporary_audio

    @staticmethod
    def transcript(language="eng"):
        return SpeechTranscript(
            language,
            (
                SpeechSegment(0, 1.25, "Hello"),
                SpeechSegment(2, 3.5, "Second\nline"),
            ),
        )

    def make_transcriber(self, extractor, recognizer, temporary_audio):
        return StagedSubtitleTranscriber(
            extractor,
            recognizer,
            SrtValidator(),
            temporary_audio_factory=lambda target: temporary_audio,
        )

    def test_renders_numbered_multiline_srt_with_rounded_timestamps(self):
        content = render_srt(self.transcript())

        self.assertEqual(
            content,
            (
                "1\n00:00:00,000 --> 00:00:01,250\nHello\n\n"
                "2\n00:00:02,000 --> 00:00:03,500\nSecond\nline\n"
            ),
        )

    def test_generates_valid_language_named_srt_and_cleans_temporary_audio(self):
        _, source, _, destination, temporary_audio = self.make_workspace()
        extractor = FakeExtractor()
        recognizer = FakeRecognizer(self.transcript("en"))
        transcriber = self.make_transcriber(extractor, recognizer, temporary_audio)
        original_source = source.read_bytes()
        audio_stream = MediaStream(3, StreamKind.AUDIO, "aac")

        artifact = transcriber.transcribe(source, audio_stream, destination)

        self.assertEqual(artifact.path.name, "lesson.generated.eng.srt")
        self.assertEqual(artifact.language, "eng")
        self.assertTrue(artifact.validation.is_valid)
        self.assertEqual(artifact.content_sha256, subtitle_sha256(artifact.path))
        self.assertEqual(extractor.calls[0][1].index, 3)
        self.assertEqual(recognizer.calls, [temporary_audio])
        self.assertFalse(temporary_audio.exists())
        self.assertFalse(destination.exists())
        self.assertEqual(source.read_bytes(), original_source)

    def test_reuses_unique_valid_candidate_without_external_tools(self):
        _, source, paths, destination, temporary_audio = self.make_workspace()
        paths.staging_directory.mkdir()
        existing = paths.staging_directory / "lesson.generated.spa.srt"
        existing.write_text(
            "1\n00:00:00,000 --> 00:00:01,000\nHola\n",
            encoding="utf-8",
        )
        extractor = FakeExtractor(error=AssertionError("must not extract"))
        recognizer = FakeRecognizer(error=AssertionError("must not recognize"))
        transcriber = self.make_transcriber(extractor, recognizer, temporary_audio)

        artifact = transcriber.transcribe(
            source,
            MediaStream(1, StreamKind.AUDIO, "aac"),
            destination,
        )

        self.assertEqual(artifact.path, existing.resolve())
        self.assertEqual(artifact.language, "spa")
        self.assertEqual(artifact.content_sha256, subtitle_sha256(existing))
        self.assertEqual(extractor.calls, [])
        self.assertEqual(recognizer.calls, [])

    def test_refuses_invalid_or_multiple_existing_candidates_without_overwrite(self):
        _, source, paths, destination, temporary_audio = self.make_workspace()
        paths.staging_directory.mkdir()
        first = paths.staging_directory / "lesson.generated.eng.srt"
        first.write_text("invalid", encoding="utf-8")
        transcriber = self.make_transcriber(
            FakeExtractor(),
            FakeRecognizer(self.transcript()),
            temporary_audio,
        )

        with self.assertRaisesRegex(StagingCollisionError, "invalid"):
            transcriber.transcribe(
                source,
                MediaStream(1, StreamKind.AUDIO, "aac"),
                destination,
            )
        self.assertEqual(first.read_text(encoding="utf-8"), "invalid")

        first.write_text(
            "1\n00:00:00,000 --> 00:00:01,000\nHello\n",
            encoding="utf-8",
        )
        second = paths.staging_directory / "lesson.generated.spa.srt"
        second.write_text(
            "1\n00:00:00,000 --> 00:00:01,000\nHola\n",
            encoding="utf-8",
        )
        with self.assertRaisesRegex(StagingCollisionError, "Multiple"):
            transcriber.transcribe(
                source,
                MediaStream(1, StreamKind.AUDIO, "aac"),
                destination,
            )

    def test_cleans_partial_audio_when_extraction_or_recognition_fails(self):
        failure_factories = (
            (
                lambda: FakeExtractor(AudioExtractionError("extract failed")),
                lambda: FakeRecognizer(self.transcript()),
                "extract failed",
            ),
            (
                lambda: FakeExtractor(),
                lambda: FakeRecognizer(error=TranscriptionError("decode failed")),
                "decode failed",
            ),
        )

        for extractor_factory, recognizer_factory, message in failure_factories:
            with self.subTest(message=message):
                _, source, _, destination, temporary_audio = self.make_workspace()
                original_source = source.read_bytes()
                transcriber = self.make_transcriber(
                    extractor_factory(),
                    recognizer_factory(),
                    temporary_audio,
                )
                with self.assertRaisesRegex(TranscriptionError, message):
                    transcriber.transcribe(
                        source,
                        MediaStream(1, StreamKind.AUDIO, "aac"),
                        destination,
                    )
                self.assertFalse(temporary_audio.exists())
                self.assertEqual(list(destination.parent.glob("*.srt")), [])
                self.assertEqual(source.read_bytes(), original_source)

    def test_removes_new_empty_srt_when_whisper_returns_no_segments(self):
        _, source, _, destination, temporary_audio = self.make_workspace()
        transcriber = self.make_transcriber(
            FakeExtractor(),
            FakeRecognizer(SpeechTranscript("eng", ())),
            temporary_audio,
        )

        with self.assertRaisesRegex(GeneratedSubtitleError, "invalid"):
            transcriber.transcribe(
                source,
                MediaStream(1, StreamKind.AUDIO, "aac"),
                destination,
            )

        self.assertFalse(temporary_audio.exists())
        self.assertEqual(list(destination.parent.glob("*.srt")), [])


class RecordingTranscriber:
    def __init__(self):
        self.calls = []

    def transcribe(self, source, audio_stream, destination):
        self.calls.append((source, audio_stream, destination))
        final_path = destination.with_name(f"{destination.stem}.eng.srt")
        final_path.parent.mkdir(parents=True, exist_ok=True)
        final_path.write_text(
            "1\n00:00:00,000 --> 00:00:01,000\nHello\n",
            encoding="utf-8",
        )
        return SubtitleArtifact(
            SubtitleOrigin.GENERATED,
            ArtifactState.VALID,
            language="eng",
            path=final_path,
            validation=SubtitleValidation(True, 1, "utf-8"),
        )


class TranscriptionStageTests(unittest.TestCase):
    def make_workspace(self):
        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        root = Path(temporary_directory.name)
        source = root / "lesson.mkv"
        source.touch()
        return root, source.resolve(), WorkspacePaths.from_directory(root)

    @staticmethod
    def inventory(source, audios, subtitles=()):
        return VideoInventory(
            source,
            (MediaStream(0, StreamKind.VIDEO, "h264"), *audios),
            subtitles,
        )

    def test_skip_plan_never_invokes_transcriber_when_valid_subtitle_exists(self):
        root, source, paths = self.make_workspace()
        existing = SubtitleArtifact(
            SubtitleOrigin.EXTERNAL,
            ArtifactState.VALID,
            path=root / "lesson.en.srt",
        )
        inventory = self.inventory(
            source,
            (MediaStream(1, StreamKind.AUDIO, "aac"),),
            (existing,),
        )
        batch_plan = BatchPlanner().plan(DiscoveryResult((inventory,)), paths)
        transcriber = RecordingTranscriber()

        result = TranscriptionStage(transcriber).execute(batch_plan, source, paths)

        self.assertIsNone(result)
        self.assertEqual(transcriber.calls, [])
        self.assertFalse(paths.staging_directory.exists())

        root, ready_source, ready_paths = self.make_workspace()
        ready_subtitle = SubtitleArtifact(
            SubtitleOrigin.EXTERNAL,
            ArtifactState.VALID,
            path=root / "lesson.en.srt",
        )
        ready_inventory = self.inventory(
            ready_source,
            (MediaStream(1, StreamKind.AUDIO, "aac"),),
            (ready_subtitle,),
        )
        issue = DiscoveryIssue(
            DiscoveryIssueKind.UNASSOCIATED_SUBTITLE,
            root / "orphan.srt",
            "No video matches subtitle",
        )
        blocked_batch = BatchPlanner().plan(
            DiscoveryResult((ready_inventory,), (issue,)),
            ready_paths,
        )
        global_transcriber = RecordingTranscriber()
        with self.assertRaisesRegex(TranscriptionError, "batch is not executable"):
            TranscriptionStage(global_transcriber).execute(
                blocked_batch,
                ready_source,
                ready_paths,
            )
        self.assertEqual(global_transcriber.calls, [])

    def test_run_plan_passes_only_the_planner_selected_audio_to_staging(self):
        _, source, paths = self.make_workspace()
        inventory = self.inventory(
            source,
            (
                MediaStream(1, StreamKind.AUDIO, "aac"),
                MediaStream(4, StreamKind.AUDIO, "aac", is_default=True),
            ),
        )
        batch_plan = BatchPlanner().plan(DiscoveryResult((inventory,)), paths)
        transcriber = RecordingTranscriber()

        artifact = TranscriptionStage(transcriber).execute(batch_plan, source, paths)

        self.assertEqual(transcriber.calls[0][1].index, 4)
        self.assertEqual(
            transcriber.calls[0][2],
            paths.staging_directory / "lesson.generated.srt",
        )
        self.assertEqual(artifact.path.name, "lesson.generated.eng.srt")

        _, blocked_source, blocked_paths = self.make_workspace()
        blocked_paths.staging_directory.touch()
        blocked_inventory = self.inventory(
            blocked_source,
            (MediaStream(1, StreamKind.AUDIO, "aac"),),
        )
        blocked_batch_plan = BatchPlanner().plan(
            DiscoveryResult((blocked_inventory,)),
            blocked_paths,
        )
        blocked_transcriber = RecordingTranscriber()
        with self.assertRaisesRegex(StagingCollisionError, "safe directory"):
            TranscriptionStage(blocked_transcriber).execute(
                blocked_batch_plan,
                blocked_source,
                blocked_paths,
            )
        self.assertEqual(blocked_transcriber.calls, [])

    def test_needs_input_plan_propagates_failure_without_invoking_transcriber(self):
        _, source, paths = self.make_workspace()
        inventory = self.inventory(
            source,
            (
                MediaStream(1, StreamKind.AUDIO, "aac"),
                MediaStream(2, StreamKind.AUDIO, "aac"),
            ),
        )
        batch_plan = BatchPlanner().plan(DiscoveryResult((inventory,)), paths)
        transcriber = RecordingTranscriber()

        with self.assertRaisesRegex(TranscriptionError, "batch is not executable"):
            TranscriptionStage(transcriber).execute(batch_plan, source, paths)

        self.assertEqual(transcriber.calls, [])
        self.assertFalse(paths.staging_directory.exists())


if __name__ == "__main__":
    unittest.main()
