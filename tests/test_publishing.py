from dataclasses import replace
from pathlib import Path
import tempfile
import unittest

from subtitles_bridge.batch_planner import BatchPlanner
from subtitles_bridge.errors import PublicationCollisionError, PublicationError
from subtitles_bridge.models import (
    ArtifactState,
    DiscoveryIssue,
    DiscoveryIssueKind,
    DiscoveryResult,
    MediaInspection,
    MediaStream,
    PlanningChoice,
    StreamKind,
    SubtitleArtifact,
    SubtitleOrigin,
    SubtitleValidation,
    VerifiedOutput,
    VideoInventory,
)
from subtitles_bridge.paths import WorkspacePaths
from subtitles_bridge.publishing import PublishingStage


class RecordingPublisher:
    def __init__(self):
        self.calls = []

    def publish(self, staged_output, final_output):
        self.calls.append((staged_output, final_output))
        final_output.parent.mkdir(parents=True, exist_ok=True)
        staged_output.replace(final_output)


class PublishingStageTests(unittest.TestCase):
    def make_workspace(self):
        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        root = Path(temporary_directory.name)
        source = root / "lesson.mp4"
        source.write_bytes(b"source")
        sidecar = root / "lesson.en.srt"
        sidecar.write_text(
            "1\n00:00:00,000 --> 00:00:01,000\nHello\n",
            encoding="utf-8",
        )
        subtitle = SubtitleArtifact(
            SubtitleOrigin.EXTERNAL,
            ArtifactState.VALID,
            language="eng",
            title="English",
            path=sidecar.resolve(),
            validation=SubtitleValidation(True, 1, "utf-8"),
        )
        inventory = VideoInventory(
            source.resolve(),
            (
                MediaStream(0, StreamKind.VIDEO, "h264"),
                MediaStream(1, StreamKind.AUDIO, "aac"),
            ),
            (subtitle,),
            duration_seconds=10.0,
        )
        paths = WorkspacePaths.from_directory(root)
        staged = paths.staged_output_for(source)
        staged.parent.mkdir()
        staged.write_bytes(b"verified-mkv")
        inspection = MediaInspection(
            (
                *inventory.streams,
                MediaStream(2, StreamKind.SUBTITLE, "subrip"),
            ),
            format_name="matroska",
            duration_seconds=10.0,
        )
        stat = staged.stat()
        proof = VerifiedOutput(
            source.resolve(),
            staged,
            inspection,
            (subtitle,),
            stat.st_size,
            stat.st_mtime_ns,
        )
        batch = BatchPlanner().plan(DiscoveryResult((inventory,)), paths)
        return root, source.resolve(), inventory, paths, batch, proof

    def test_publishes_only_the_current_verified_snapshot(self):
        _, source, _, paths, batch, proof = self.make_workspace()
        publisher = RecordingPublisher()

        final = PublishingStage(publisher).execute(
            batch,
            source,
            paths,
            proof,
        )

        self.assertEqual(final, paths.output_for(source))
        self.assertEqual(final.read_bytes(), b"verified-mkv")
        self.assertFalse(proof.staged_path.exists())
        self.assertEqual(
            publisher.calls,
            [(proof.staged_path, paths.output_for(source))],
        )

    def test_rejects_changed_or_incomplete_verification_proofs(self):
        _, source, inventory, paths, batch, proof = self.make_workspace()
        publisher = RecordingPublisher()
        proof.staged_path.write_bytes(b"changed-after-verification")

        with self.assertRaisesRegex(PublicationError, "changed after verification"):
            PublishingStage(publisher).execute(batch, source, paths, proof)
        self.assertEqual(publisher.calls, [])
        self.assertFalse(paths.output_for(source).exists())

        stat = proof.staged_path.stat()
        wrong_subtitles = replace(
            proof,
            expected_subtitles=(),
            size_bytes=stat.st_size,
            modified_time_ns=stat.st_mtime_ns,
        )
        with self.assertRaisesRegex(PublicationError, "planned subtitles"):
            PublishingStage(publisher).execute(
                batch,
                source,
                paths,
                wrong_subtitles,
            )

        other_source = replace(proof, source=inventory.source.with_name("other.mp4"))
        with self.assertRaisesRegex(PublicationError, "another source"):
            PublishingStage(publisher).execute(
                batch,
                source,
                paths,
                other_source,
            )

    def test_requires_proof_and_rejects_final_output_collisions(self):
        _, source, _, paths, batch, proof = self.make_workspace()
        publisher = RecordingPublisher()

        with self.assertRaisesRegex(PublicationError, "requires a verification"):
            PublishingStage(publisher).execute(batch, source, paths, None)

        final = paths.output_for(source)
        final.parent.mkdir()
        final.write_bytes(b"existing")
        with self.assertRaisesRegex(PublicationCollisionError, "already exists"):
            PublishingStage(publisher).execute(batch, source, paths, proof)
        self.assertEqual(final.read_bytes(), b"existing")
        self.assertEqual(publisher.calls, [])

    def test_skip_and_blocked_plans_never_invoke_publisher(self):
        root, source, inventory, paths, _, proof = self.make_workspace()
        final = paths.output_for(source)
        final.parent.mkdir()
        final.write_bytes(b"verified")
        resumed_inventory = replace(inventory, existing_output=final.resolve())
        resumed = BatchPlanner().plan(
            DiscoveryResult((resumed_inventory,)),
            paths,
            (PlanningChoice(source, verified_output=final),),
        )
        publisher = RecordingPublisher()

        self.assertIsNone(
            PublishingStage(publisher).execute(
                resumed,
                source,
                paths,
                None,
            )
        )
        self.assertEqual(publisher.calls, [])

        issue = DiscoveryIssue(
            DiscoveryIssueKind.UNASSOCIATED_SUBTITLE,
            root / "orphan.srt",
            "No video matches subtitle",
        )
        blocked = BatchPlanner().plan(
            DiscoveryResult((inventory,), (issue,)),
            paths,
        )
        with self.assertRaisesRegex(PublicationError, "batch is not executable"):
            PublishingStage(publisher).execute(
                blocked,
                source,
                paths,
                proof,
            )
        self.assertEqual(publisher.calls, [])


if __name__ == "__main__":
    unittest.main()
