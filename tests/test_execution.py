import tempfile
import unittest
from pathlib import Path

from subtitles_bridge.batch_planner import BatchPlanner
from subtitles_bridge.execution import EXECUTION_STAGES, BatchExecutor
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
    ResultStatus,
    StreamKind,
    SubtitleArtifact,
    SubtitleOrigin,
    SubtitleValidation,
    VerifiedOutput,
    VideoInventory,
)
from subtitles_bridge.paths import WorkspacePaths


class FakeStage:
    def __init__(self, pipeline, stage):
        self.pipeline = pipeline
        self.stage = stage

    def execute(self, batch_plan, source, paths, *args, **kwargs):
        return self.pipeline.execute(
            self.stage,
            batch_plan,
            source,
            paths,
            *args,
            **kwargs,
        )


class FakePipeline:
    def __init__(self):
        self.calls = []
        self.failures = {}
        self.stages = {stage: FakeStage(self, stage) for stage in EXECUTION_STAGES}

    def executor(self):
        return BatchExecutor(
            self.stages[PipelineStage.TRANSCRIBE],
            self.stages[PipelineStage.MUX],
            self.stages[PipelineStage.VERIFY],
            self.stages[PipelineStage.PUBLISH],
            self.stages[PipelineStage.ARCHIVE],
        )

    def execute(
        self,
        stage,
        batch_plan,
        source,
        paths,
        *args,
        **kwargs,
    ):
        source = source.resolve()
        self.calls.append((source, stage))
        failure = self.failures.get((source, stage))
        if failure is not None:
            raise failure

        plan = batch_plan.plan_for(source)
        if stage is PipelineStage.TRANSCRIBE:
            return SubtitleArtifact(
                SubtitleOrigin.GENERATED,
                ArtifactState.VALID,
                language="eng",
                path=paths.staging_directory / f"{source.stem}.generated.eng.srt",
                validation=SubtitleValidation(True, 1, "utf-8"),
            )
        if stage is PipelineStage.MUX:
            return paths.staged_output_for(source)
        if stage is PipelineStage.VERIFY:
            generated = kwargs.get("generated_subtitle")
            expected = (
                (generated,) if generated is not None else plan.selected_subtitles
            )
            return VerifiedOutput(
                source,
                paths.staged_output_for(source),
                MediaInspection(plan.inventory.streams),
                expected,
                100,
                10,
            )
        if stage is PipelineStage.PUBLISH:
            verified = args[0]
            return PublishedOutput(
                source,
                plan.output_path,
                verified.inspection,
                verified.expected_subtitles,
                verified.size_bytes,
                verified.modified_time_ns,
            )

        published = args[0]
        sidecars = tuple(
            subtitle.path
            for subtitle in published.expected_subtitles
            if subtitle.origin is not SubtitleOrigin.EMBEDDED
        )
        originals = (source, *sidecars)
        return ArchivedInputs(
            source,
            plan.trash_path,
            originals,
            tuple(plan.trash_path / path.name for path in originals),
        )


class BatchExecutorTests(unittest.TestCase):
    def make_workspace(self, names=("lesson.mp4",), *, subtitles=False):
        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        root = Path(temporary_directory.name)
        inventories = []
        for name in names:
            source = root / name
            source.write_bytes(b"video")
            artifacts = ()
            if subtitles:
                sidecar = root / f"{source.stem}.en.srt"
                sidecar.write_text("subtitle", encoding="utf-8")
                artifacts = (
                    SubtitleArtifact(
                        SubtitleOrigin.EXTERNAL,
                        ArtifactState.VALID,
                        language="eng",
                        path=sidecar.resolve(),
                        validation=SubtitleValidation(True, 1, "utf-8"),
                    ),
                )
            inventories.append(
                VideoInventory(
                    source.resolve(),
                    (
                        MediaStream(0, StreamKind.VIDEO, "h264"),
                        MediaStream(1, StreamKind.AUDIO, "aac"),
                    ),
                    artifacts,
                )
            )
        paths = WorkspacePaths.from_directory(root)
        discovery = DiscoveryResult(tuple(inventories))
        return root, paths, tuple(inventories), discovery

    def test_executes_all_run_stages_and_connects_typed_artifacts(self):
        _, paths, (inventory,), discovery = self.make_workspace()
        batch = BatchPlanner().plan(discovery, paths)
        pipeline = FakePipeline()

        result = pipeline.executor().execute(batch, paths)

        self.assertEqual(
            pipeline.calls,
            [(inventory.source, stage) for stage in EXECUTION_STAGES],
        )
        self.assertEqual(result.status, ResultStatus.COMPLETED)
        self.assertEqual(result.exit_code, 0)
        self.assertEqual(result.videos[0].status, ResultStatus.COMPLETED)
        self.assertEqual(
            [stage.status for stage in result.videos[0].stages],
            [ResultStatus.COMPLETED] * 5,
        )
        self.assertEqual(result.videos[0].output_path, batch.videos[0].output_path)
        self.assertEqual(result.videos[0].trash_path, batch.videos[0].trash_path)

    def test_records_planned_skips_without_invoking_their_backend(self):
        _, paths, (inventory,), discovery = self.make_workspace(subtitles=True)
        batch = BatchPlanner().plan(discovery, paths)
        pipeline = FakePipeline()

        result = pipeline.executor().execute(batch, paths)

        self.assertNotIn(
            (inventory.source, PipelineStage.TRANSCRIBE),
            pipeline.calls,
        )
        self.assertEqual(
            result.videos[0].stages[0].status,
            ResultStatus.SKIPPED,
        )
        self.assertEqual(result.status, ResultStatus.COMPLETED)

    def test_contains_a_video_failure_and_continues_the_batch(self):
        _, paths, inventories, discovery = self.make_workspace(
            ("first.mp4", "second.mp4")
        )
        batch = BatchPlanner().plan(discovery, paths)
        pipeline = FakePipeline()
        pipeline.failures[(inventories[0].source, PipelineStage.MUX)] = RuntimeError(
            "injected mux failure"
        )

        result = pipeline.executor().execute(batch, paths)

        first, second = result.videos
        self.assertEqual(first.status, ResultStatus.FAILED)
        self.assertIn("RuntimeError: injected mux failure", first.message)
        self.assertEqual(
            [stage.status for stage in first.stages],
            [
                ResultStatus.COMPLETED,
                ResultStatus.FAILED,
                ResultStatus.SKIPPED,
                ResultStatus.SKIPPED,
                ResultStatus.SKIPPED,
            ],
        )
        self.assertEqual(second.status, ResultStatus.COMPLETED)
        self.assertEqual(result.status, ResultStatus.FAILED)
        self.assertEqual(result.exit_code, 1)

    def test_archive_failure_is_partial_and_keeps_published_path(self):
        _, paths, (inventory,), discovery = self.make_workspace()
        batch = BatchPlanner().plan(discovery, paths)
        pipeline = FakePipeline()
        pipeline.failures[(inventory.source, PipelineStage.ARCHIVE)] = OSError(
            "injected archive failure"
        )

        result = pipeline.executor().execute(batch, paths)

        video = result.videos[0]
        self.assertEqual(video.status, ResultStatus.PARTIAL)
        self.assertEqual(video.output_path, batch.videos[0].output_path)
        self.assertIn(str(inventory.source), video.message)
        self.assertEqual(result.status, ResultStatus.PARTIAL)
        self.assertEqual(result.exit_code, 3)

    def test_blocked_batch_never_invokes_stages(self):
        root, paths, (inventory,), discovery = self.make_workspace()
        issue = DiscoveryIssue(
            DiscoveryIssueKind.UNASSOCIATED_SUBTITLE,
            root / "orphan.srt",
            "No video matches subtitle",
        )
        blocked = BatchPlanner().plan(
            DiscoveryResult(discovery.inventories, (issue,)),
            paths,
        )
        pipeline = FakePipeline()

        result = pipeline.executor().execute(blocked, paths)

        self.assertEqual(pipeline.calls, [])
        self.assertEqual(result.status, ResultStatus.NEEDS_INPUT)
        self.assertEqual(result.exit_code, 2)
        self.assertEqual(result.videos[0].status, ResultStatus.NEEDS_INPUT)
        self.assertTrue(
            all(
                stage.status is ResultStatus.NEEDS_INPUT
                for stage in result.videos[0].stages
            )
        )
        self.assertIn(str(issue.path), result.videos[0].message)

    def test_resumed_output_runs_only_archive_with_supplied_proof(self):
        root, paths, (inventory,), _ = self.make_workspace()
        output = paths.output_for(inventory.source)
        output.parent.mkdir()
        output.write_bytes(b"verified")
        resumed_inventory = VideoInventory(
            inventory.source,
            inventory.streams,
            existing_output=output.resolve(),
        )
        batch = BatchPlanner().plan(
            DiscoveryResult((resumed_inventory,)),
            paths,
            (PlanningChoice(inventory.source, verified_output=output),),
        )
        proof = PublishedOutput(
            inventory.source,
            output,
            MediaInspection(inventory.streams),
            (),
            output.stat().st_size,
            output.stat().st_mtime_ns,
        )
        pipeline = FakePipeline()

        result = pipeline.executor().execute(
            batch,
            paths,
            published_outputs=(proof,),
        )

        self.assertEqual(
            pipeline.calls,
            [(inventory.source, PipelineStage.ARCHIVE)],
        )
        self.assertEqual(result.videos[0].status, ResultStatus.COMPLETED)
        self.assertEqual(
            [stage.status for stage in result.videos[0].stages[:4]],
            [ResultStatus.SKIPPED] * 4,
        )
        self.assertEqual(result.videos[0].output_path, output)
        self.assertEqual(
            result.videos[0].trash_path,
            (root / "trash" / "lesson").resolve(),
        )

    def test_missing_run_artifact_is_a_failed_stage(self):
        _, paths, (inventory,), discovery = self.make_workspace()
        batch = BatchPlanner().plan(discovery, paths)
        pipeline = FakePipeline()

        def missing_artifact(*args, **kwargs):
            pipeline.calls.append((inventory.source, PipelineStage.TRANSCRIBE))
            return None

        pipeline.stages[PipelineStage.TRANSCRIBE].execute = missing_artifact

        result = pipeline.executor().execute(batch, paths)

        video = result.videos[0]
        self.assertEqual(video.status, ResultStatus.FAILED)
        self.assertEqual(video.stages[0].status, ResultStatus.FAILED)
        self.assertIn("returned no SubtitleArtifact", video.message)

    def test_empty_batches_distinguish_failure_from_discovery_attention(self):
        root, paths, _, _ = self.make_workspace(())
        pipeline = FakePipeline()

        empty = pipeline.executor().execute(BatchPlan(()), paths)
        issue = DiscoveryIssue(
            DiscoveryIssueKind.INSPECTION_FAILED,
            root / "broken.mp4",
            "ffprobe failed",
        )
        attention = pipeline.executor().execute(BatchPlan((), (issue,)), paths)

        self.assertEqual(empty.status, ResultStatus.FAILED)
        self.assertEqual(empty.exit_code, 1)
        self.assertEqual(attention.status, ResultStatus.NEEDS_INPUT)
        self.assertEqual(attention.exit_code, 2)
        self.assertEqual(pipeline.calls, [])


if __name__ == "__main__":
    unittest.main()
