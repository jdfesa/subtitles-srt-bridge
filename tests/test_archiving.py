from dataclasses import replace
import os
from pathlib import Path
import tempfile
import unittest

from subtitles_bridge.adapters.filesystem_archive import (
    TransactionalInputArchiver,
)
from subtitles_bridge.adapters.filesystem_publish import AtomicOutputPublisher
from subtitles_bridge.archiving import ArchivingStage
from subtitles_bridge.batch_planner import BatchPlanner
from subtitles_bridge.errors import ArchivingError, ArchivingPartialError
from subtitles_bridge.models import (
    ArchivedInputs,
    ArtifactState,
    BatchPlan,
    DiscoveryIssue,
    DiscoveryIssueKind,
    DiscoveryResult,
    MediaInspection,
    MediaStream,
    PipelineStage,
    PlanningChoice,
    PublishedOutput,
    StageAction,
    StreamKind,
    SubtitleArtifact,
    SubtitleOrigin,
    SubtitleValidation,
    VerifiedOutput,
    VideoInventory,
)
from subtitles_bridge.paths import WorkspacePaths
from subtitles_bridge.publishing import PublishingStage


class RecordingArchiver:
    def __init__(self, *, move=True):
        self.calls = []
        self.move = move

    def archive(self, source, sidecars, destination):
        self.calls.append((source, tuple(sidecars), destination))
        originals = (source, *sidecars)
        archived = tuple(destination / path.name for path in originals)
        if self.move:
            return TransactionalInputArchiver().archive(
                source,
                sidecars,
                destination,
            )
        return ArchivedInputs(source, destination, originals, archived)


class ArchivingStageTests(unittest.TestCase):
    def make_workspace(self, *, with_external=True):
        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        root = Path(temporary_directory.name)
        source = root / "lesson.mp4"
        source.write_bytes(b"source-video")
        streams = (
            MediaStream(0, StreamKind.VIDEO, "h264"),
            MediaStream(1, StreamKind.AUDIO, "aac"),
        )
        subtitles = ()
        if with_external:
            sidecar = root / "lesson.en.srt"
            sidecar.write_text(
                "1\n00:00:00,000 --> 00:00:01,000\nHello\n",
                encoding="utf-8",
            )
            subtitles = (
                SubtitleArtifact(
                    SubtitleOrigin.EXTERNAL,
                    ArtifactState.VALID,
                    language="eng",
                    path=sidecar.resolve(),
                    validation=SubtitleValidation(True, 1, "utf-8"),
                ),
            )
        inventory = VideoInventory(
            source.resolve(),
            streams,
            subtitles,
            duration_seconds=10.0,
        )
        paths = WorkspacePaths.from_directory(root)
        output = paths.output_for(source)
        output.parent.mkdir()
        output.write_bytes(b"published-mkv")
        inspection = MediaInspection(
            (*streams, MediaStream(2, StreamKind.SUBTITLE, "subrip")),
            format_name="matroska",
            duration_seconds=10.0,
        )
        stat = output.stat()
        proof = PublishedOutput(
            source.resolve(),
            output,
            inspection,
            subtitles,
            stat.st_size,
            stat.st_mtime_ns,
        )
        batch = BatchPlanner().plan(DiscoveryResult((inventory,)), paths)
        return root, source.resolve(), inventory, paths, batch, proof

    def test_archives_only_source_and_incorporated_sidecars(self):
        root, source, inventory, paths, batch, proof = self.make_workspace()
        invalid = root / "lesson.bad.srt"
        invalid.write_text("not incorporated", encoding="utf-8")
        unrelated = root / "other.srt"
        unrelated.write_text("unrelated", encoding="utf-8")
        archiver = RecordingArchiver()

        receipt = ArchivingStage(archiver).execute(
            batch,
            source,
            paths,
            proof,
        )

        sidecar = inventory.valid_subtitles[0].path
        self.assertEqual(
            archiver.calls,
            [(source, (sidecar,), paths.trash_directory / "lesson")],
        )
        self.assertEqual(receipt.original_paths, (source, sidecar))
        self.assertTrue(all(path.is_file() for path in receipt.archived_paths))
        self.assertTrue(invalid.is_file())
        self.assertTrue(unrelated.is_file())
        self.assertTrue(proof.final_path.is_file())

    def test_consumes_the_proof_returned_by_atomic_publication(self):
        _, source, _, paths, batch, proof = self.make_workspace()
        proof.final_path.unlink()
        staged = paths.staged_output_for(source)
        staged.parent.mkdir()
        staged.write_bytes(b"published-mkv")
        stat = staged.stat()
        verified = VerifiedOutput(
            source,
            staged,
            proof.inspection,
            proof.expected_subtitles,
            stat.st_size,
            stat.st_mtime_ns,
        )

        published = PublishingStage(AtomicOutputPublisher()).execute(
            batch,
            source,
            paths,
            verified,
        )
        receipt = ArchivingStage(TransactionalInputArchiver()).execute(
            batch,
            source,
            paths,
            published,
        )

        self.assertTrue(published.final_path.is_file())
        self.assertTrue(all(path.is_file() for path in receipt.archived_paths))
        self.assertFalse(staged.exists())

    def test_requires_a_current_matching_published_proof(self):
        _, source, inventory, paths, batch, proof = self.make_workspace()
        archiver = RecordingArchiver()

        with self.assertRaisesRegex(ArchivingError, "published output proof"):
            ArchivingStage(archiver).execute(batch, source, paths, None)

        proof.final_path.write_bytes(b"changed")
        with self.assertRaisesRegex(ArchivingError, "Published output changed"):
            ArchivingStage(archiver).execute(batch, source, paths, proof)

        stat = proof.final_path.stat()
        wrong = replace(
            proof,
            source=inventory.source.with_name("other.mp4"),
            size_bytes=stat.st_size,
            modified_time_ns=stat.st_mtime_ns,
        )
        with self.assertRaisesRegex(ArchivingError, "another source"):
            ArchivingStage(archiver).execute(batch, source, paths, wrong)
        self.assertEqual(archiver.calls, [])

    def test_rejects_a_receipt_when_the_archiver_did_not_move_inputs(self):
        _, source, _, paths, batch, proof = self.make_workspace()
        archiver = RecordingArchiver(move=False)

        with self.assertRaisesRegex(ArchivingError, "left an input in place"):
            ArchivingStage(archiver).execute(batch, source, paths, proof)

        self.assertTrue(source.is_file())
        self.assertTrue(proof.final_path.is_file())

    def test_resumes_generated_sidecar_archival_from_verified_output(self):
        _, source, inventory, paths, _, proof = self.make_workspace(
            with_external=False
        )
        generated_path = paths.staging_directory / "lesson.generated.eng.srt"
        generated_path.parent.mkdir()
        generated_path.write_text(
            "1\n00:00:00,000 --> 00:00:01,000\nHello\n",
            encoding="utf-8",
        )
        generated = SubtitleArtifact(
            SubtitleOrigin.GENERATED,
            ArtifactState.VALID,
            language="eng",
            path=generated_path,
            validation=SubtitleValidation(True, 1, "utf-8"),
        )
        resumed_inventory = replace(
            inventory,
            existing_output=proof.final_path.resolve(),
        )
        resumed = BatchPlanner().plan(
            DiscoveryResult((resumed_inventory,)),
            paths,
            (PlanningChoice(source, verified_output=proof.final_path),),
        )
        stat = proof.final_path.stat()
        resumed_proof = replace(
            proof,
            expected_subtitles=(generated,),
            size_bytes=stat.st_size,
            modified_time_ns=stat.st_mtime_ns,
        )

        receipt = ArchivingStage(TransactionalInputArchiver()).execute(
            resumed,
            source,
            paths,
            resumed_proof,
        )

        self.assertTrue(resumed.videos[0].uses_verified_output)
        for stage in (
            PipelineStage.TRANSCRIBE,
            PipelineStage.MUX,
            PipelineStage.VERIFY,
            PipelineStage.PUBLISH,
        ):
            self.assertIs(
                resumed.videos[0].decision_for(stage).action,
                StageAction.SKIP,
            )
        self.assertEqual(receipt.original_paths, (source, generated_path))
        self.assertTrue(proof.final_path.is_file())

    def test_archive_failure_keeps_output_and_can_retry_only_archive(self):
        _, source, inventory, paths, batch, proof = self.make_workspace()
        calls = 0

        def fail_source_move(original, archived):
            nonlocal calls
            calls += 1
            if original == source:
                raise OSError("injected source move failure")
            os.replace(original, archived)

        with self.assertRaisesRegex(ArchivingPartialError, "remains valid"):
            ArchivingStage(
                TransactionalInputArchiver(fail_source_move)
            ).execute(batch, source, paths, proof)

        self.assertTrue(proof.final_path.is_file())
        self.assertTrue(source.is_file())
        self.assertTrue(inventory.valid_subtitles[0].path.is_file())
        self.assertFalse(paths.trash_directory.joinpath("lesson").exists())

        receipt = ArchivingStage(TransactionalInputArchiver()).execute(
            batch,
            source,
            paths,
            proof,
        )
        self.assertEqual(calls, 3)
        self.assertTrue(proof.final_path.is_file())
        self.assertTrue(all(path.is_file() for path in receipt.archived_paths))

    def test_skip_and_blocked_plans_never_invoke_archiver(self):
        root, source, inventory, paths, batch, proof = self.make_workspace()
        plan = batch.videos[0]
        skip_decisions = tuple(
            replace(decision, action=StageAction.SKIP, reason="Already archived")
            if decision.stage is PipelineStage.ARCHIVE
            else decision
            for decision in plan.decisions
        )
        skipped = BatchPlan((replace(plan, decisions=skip_decisions),))
        archiver = RecordingArchiver()

        self.assertIsNone(
            ArchivingStage(archiver).execute(skipped, source, paths, None)
        )

        issue = DiscoveryIssue(
            DiscoveryIssueKind.UNASSOCIATED_SUBTITLE,
            root / "orphan.srt",
            "No video matches subtitle",
        )
        blocked = BatchPlanner().plan(
            DiscoveryResult((inventory,), (issue,)),
            paths,
        )
        with self.assertRaisesRegex(ArchivingError, "batch is not executable"):
            ArchivingStage(archiver).execute(
                blocked,
                source,
                paths,
                proof,
            )
        self.assertEqual(archiver.calls, [])


if __name__ == "__main__":
    unittest.main()
