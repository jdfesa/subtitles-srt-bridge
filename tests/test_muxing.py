from pathlib import Path
import tempfile
import unittest

from subtitles_bridge.batch_planner import BatchPlanner
from subtitles_bridge.errors import MuxingCollisionError, MuxingError
from subtitles_bridge.models import (
    ArtifactState,
    DiscoveryIssue,
    DiscoveryIssueKind,
    DiscoveryResult,
    MediaStream,
    PlanningChoice,
    StreamKind,
    SubtitleArtifact,
    SubtitleOrigin,
    SubtitleValidation,
    VideoInventory,
)
from subtitles_bridge.muxing import MuxingStage
from subtitles_bridge.paths import WorkspacePaths


class RecordingMuxer:
    def __init__(self, *, content=b"staged-mkv"):
        self.content = content
        self.calls = []

    def mux(self, inventory, subtitles, destination):
        self.calls.append((inventory, tuple(subtitles), destination))
        destination.write_bytes(self.content)


class MuxingStageTests(unittest.TestCase):
    def make_workspace(self):
        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        root = Path(temporary_directory.name)
        source = root / "lesson.mp4"
        source.write_bytes(b"source-media")
        return root, source.resolve(), WorkspacePaths.from_directory(root)

    @staticmethod
    def external(path, *, language="eng", title="English"):
        path.write_text(
            "1\n00:00:00,000 --> 00:00:01,000\nHello\n",
            encoding="utf-8",
        )
        return SubtitleArtifact(
            SubtitleOrigin.EXTERNAL,
            ArtifactState.VALID,
            language=language,
            title=title,
            path=path.resolve(),
            validation=SubtitleValidation(True, 1, "utf-8"),
        )

    @staticmethod
    def inventory(source, *, subtitles=(), extra_streams=()):
        return VideoInventory(
            source,
            (
                MediaStream(0, StreamKind.VIDEO, "h264"),
                MediaStream(1, StreamKind.AUDIO, "aac"),
                *extra_streams,
            ),
            subtitles,
        )

    @staticmethod
    def batch(inventory, paths, *, choices=(), issues=()):
        return BatchPlanner().plan(
            DiscoveryResult((inventory,), tuple(issues)),
            paths,
            choices,
        )

    def test_reuses_every_planned_external_and_embedded_subtitle(self):
        root, source, paths = self.make_workspace()
        external = self.external(root / "lesson.en.srt")
        embedded_stream = MediaStream(2, StreamKind.SUBTITLE, "subrip")
        embedded = SubtitleArtifact(
            SubtitleOrigin.EMBEDDED,
            ArtifactState.VALID,
            stream_index=2,
        )
        inventory = self.inventory(
            source,
            subtitles=(embedded, external),
            extra_streams=(embedded_stream,),
        )
        batch_plan = self.batch(inventory, paths)
        muxer = RecordingMuxer()
        source_content = source.read_bytes()
        sidecar_content = external.path.read_bytes()

        output = MuxingStage(muxer).execute(batch_plan, source, paths)

        self.assertEqual(output, paths.staged_output_for(source))
        self.assertEqual(output.read_bytes(), b"staged-mkv")
        self.assertEqual(muxer.calls[0][1], (embedded, external))
        self.assertEqual(source.read_bytes(), source_content)
        self.assertEqual(external.path.read_bytes(), sidecar_content)

    def test_requires_and_passes_only_the_generated_transcription(self):
        _, source, paths = self.make_workspace()
        inventory = self.inventory(source)
        batch_plan = self.batch(inventory, paths)
        muxer = RecordingMuxer()

        with self.assertRaisesRegex(MuxingError, "requires the generated"):
            MuxingStage(muxer).execute(batch_plan, source, paths)
        self.assertEqual(muxer.calls, [])
        self.assertFalse(paths.staging_directory.exists())

        paths.staging_directory.mkdir()
        wrong_path = paths.staging_directory / "lesson.generated.eng.extra.srt"
        wrong = self.external(wrong_path)
        wrong = SubtitleArtifact(
            SubtitleOrigin.GENERATED,
            ArtifactState.VALID,
            language=wrong.language,
            path=wrong.path,
            validation=wrong.validation,
        )
        with self.assertRaisesRegex(MuxingError, "does not belong"):
            MuxingStage(muxer).execute(
                batch_plan,
                source,
                paths,
                generated_subtitle=wrong,
            )
        wrong.path.unlink()

        generated_path = paths.staging_directory / "lesson.generated.eng.srt"
        generated = self.external(generated_path)
        generated = SubtitleArtifact(
            SubtitleOrigin.GENERATED,
            ArtifactState.VALID,
            language=generated.language,
            title="Whisper transcription (eng)",
            path=generated.path,
            validation=generated.validation,
        )

        output = MuxingStage(muxer).execute(
            batch_plan,
            source,
            paths,
            generated_subtitle=generated,
        )

        self.assertEqual(output, paths.staged_output_for(source))
        self.assertEqual(muxer.calls[0][1], (generated,))

    def test_skip_plan_never_invokes_muxer_or_creates_staging(self):
        root, source, paths = self.make_workspace()
        output = paths.output_for(source)
        output.parent.mkdir()
        output.write_bytes(b"verified-output")
        inventory = VideoInventory(
            source,
            (
                MediaStream(0, StreamKind.VIDEO, "h264"),
                MediaStream(1, StreamKind.AUDIO, "aac"),
            ),
            existing_output=output.resolve(),
        )
        batch_plan = self.batch(
            inventory,
            paths,
            choices=(PlanningChoice(source, verified_output=output),),
        )
        muxer = RecordingMuxer()

        result = MuxingStage(muxer).execute(batch_plan, source, paths)

        self.assertIsNone(result)
        self.assertEqual(muxer.calls, [])
        self.assertFalse(paths.staging_directory.exists())
        self.assertEqual(
            root.joinpath("output", output.name).read_bytes(),
            b"verified-output",
        )

    def test_blocked_batch_and_staging_collisions_fail_before_muxer(self):
        root, source, paths = self.make_workspace()
        external = self.external(root / "lesson.en.srt")
        inventory = self.inventory(source, subtitles=(external,))
        issue = DiscoveryIssue(
            DiscoveryIssueKind.UNASSOCIATED_SUBTITLE,
            root / "orphan.srt",
            "No video matches subtitle",
        )
        blocked = self.batch(inventory, paths, issues=(issue,))
        muxer = RecordingMuxer()

        with self.assertRaisesRegex(MuxingError, "batch is not executable"):
            MuxingStage(muxer).execute(blocked, source, paths)
        self.assertEqual(muxer.calls, [])
        self.assertFalse(paths.staging_directory.exists())

        ready = self.batch(inventory, paths)
        paths.staging_directory.touch()
        with self.assertRaisesRegex(MuxingCollisionError, "safe directory"):
            MuxingStage(muxer).execute(ready, source, paths)
        self.assertEqual(muxer.calls, [])

        paths.staging_directory.unlink()
        paths.staging_directory.mkdir()
        existing_output = paths.staged_output_for(source)
        existing_output.write_bytes(b"existing-staged-output")
        with self.assertRaisesRegex(MuxingCollisionError, "already exists"):
            MuxingStage(muxer).execute(ready, source, paths)
        self.assertEqual(existing_output.read_bytes(), b"existing-staged-output")
        self.assertEqual(muxer.calls, [])

    def test_rejects_unplanned_generated_subtitle_and_empty_muxer_output(self):
        root, source, paths = self.make_workspace()
        external = self.external(root / "lesson.en.srt")
        inventory = self.inventory(source, subtitles=(external,))
        batch_plan = self.batch(inventory, paths)
        generated = SubtitleArtifact(
            SubtitleOrigin.GENERATED,
            ArtifactState.VALID,
            language="spa",
            path=external.path,
            validation=external.validation,
        )
        muxer = RecordingMuxer(content=b"")

        with self.assertRaisesRegex(MuxingError, "not planned"):
            MuxingStage(muxer).execute(
                batch_plan,
                source,
                paths,
                generated_subtitle=generated,
            )
        self.assertEqual(muxer.calls, [])

        with self.assertRaisesRegex(MuxingError, "usable staged MKV"):
            MuxingStage(muxer).execute(batch_plan, source, paths)
        self.assertFalse(paths.staged_output_for(source).exists())


if __name__ == "__main__":
    unittest.main()
