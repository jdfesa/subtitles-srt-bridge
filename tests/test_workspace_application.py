from pathlib import Path
import tempfile
import unittest

from subtitles_bridge.models import (
    BatchPlan,
    BatchResult,
    DiscoveryResult,
    MediaInspection,
    MediaStream,
    PipelineStage,
    PlanDecision,
    PlanningChoice,
    PublishedOutput,
    ResultStatus,
    StageAction,
    StageResult,
    StreamKind,
    VideoInventory,
    VideoPlan,
    VideoResult,
)
from subtitles_bridge.workspace_application import AudioSelection, WorkspaceApplication


EXECUTION_STAGES = (
    PipelineStage.TRANSCRIBE,
    PipelineStage.MUX,
    PipelineStage.VERIFY,
    PipelineStage.PUBLISH,
    PipelineStage.ARCHIVE,
)


class FakeDiscovery:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def inspect(self, paths):
        self.calls.append(paths)
        return self.result


class FakePlanner:
    def __init__(self, plan):
        self.plan_result = plan
        self.calls = []

    def plan(self, discovery, paths, choices=()):
        self.calls.append((discovery, paths, tuple(choices)))
        return self.plan_result


class FakeExecutor:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def execute(self, batch_plan, paths, *, published_outputs=()):
        self.calls.append((batch_plan, paths, tuple(published_outputs)))
        return self.result


class FakeResumer:
    def __init__(self, outputs):
        self.outputs = tuple(outputs)
        self.calls = []

    def verify(self, discovery, paths):
        self.calls.append((discovery, paths))
        return self.outputs


class WorkspaceApplicationTests(unittest.TestCase):
    def test_runs_preflight_before_execution_with_injected_dependencies(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "lesson.mp4"
            source.write_bytes(b"video")
            inventory = VideoInventory(source.resolve())
            discovery_result = DiscoveryResult((inventory,))
            decisions = tuple(
                PlanDecision(stage, StageAction.SKIP, "Already complete")
                for stage in EXECUTION_STAGES
            )
            plan = BatchPlan(
                (
                    VideoPlan(
                        inventory,
                        root / "output" / "lesson.subtitled.mkv",
                        root / "trash" / "lesson",
                        decisions,
                    ),
                )
            )
            stages = tuple(
                StageResult(stage, ResultStatus.SKIPPED, "Already complete")
                for stage in EXECUTION_STAGES
            )
            result = BatchResult(
                (
                    VideoResult(
                        inventory.source,
                        ResultStatus.SKIPPED,
                        "Already complete",
                        stages=stages,
                    ),
                )
            )
            discovery = FakeDiscovery(discovery_result)
            planner = FakePlanner(plan)
            executor = FakeExecutor(result)
            application = WorkspaceApplication(discovery, planner, executor)
            written = []

            exit_code = application.run(root, write=written.append)

        self.assertEqual(exit_code, 0)
        self.assertEqual(len(discovery.calls), 1)
        self.assertEqual(planner.calls[0][0], discovery_result)
        self.assertIs(executor.calls[0][0], plan)
        self.assertEqual(len(written), 2)
        self.assertTrue(written[0].startswith("Preflight\nBatch: 1 video(s)"))
        self.assertIn("[skip] archive: Already complete", written[0])
        self.assertTrue(written[1].startswith("Batch result: skipped"))

    def test_preflight_only_reports_ready_without_calling_executor(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "lesson.mp4"
            source.write_bytes(b"video")
            inventory = VideoInventory(source.resolve())
            decisions = tuple(
                PlanDecision(stage, StageAction.SKIP, "Already complete")
                for stage in EXECUTION_STAGES
            )
            plan = BatchPlan(
                (
                    VideoPlan(
                        inventory,
                        root / "output" / "lesson.subtitled.mkv",
                        root / "trash" / "lesson",
                        decisions,
                    ),
                )
            )
            executor = FakeExecutor(BatchResult(()))
            application = WorkspaceApplication(
                FakeDiscovery(DiscoveryResult((inventory,))),
                FakePlanner(plan),
                executor,
            )
            written = []

            exit_code = application.run(
                root,
                preflight_only=True,
                write=written.append,
            )

        self.assertEqual(exit_code, 0)
        self.assertEqual(executor.calls, [])
        self.assertEqual(written[-1], "Preflight result: ready\nExit code: 0")

    def test_preflight_only_reports_needs_input_and_empty_failure(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "lesson.mp4"
            source.write_bytes(b"video")
            inventory = VideoInventory(source.resolve())
            blocked = tuple(
                PlanDecision(stage, StageAction.NEEDS_INPUT, "Choose audio")
                for stage in EXECUTION_STAGES
            )
            blocked_plan = BatchPlan(
                (
                    VideoPlan(
                        inventory,
                        root / "output" / "lesson.subtitled.mkv",
                        root / "trash" / "lesson",
                        blocked,
                    ),
                )
            )
            blocked_application = WorkspaceApplication(
                FakeDiscovery(DiscoveryResult((inventory,))),
                FakePlanner(blocked_plan),
                FakeExecutor(BatchResult(())),
            )
            empty_application = WorkspaceApplication(
                FakeDiscovery(DiscoveryResult(())),
                FakePlanner(BatchPlan(())),
                FakeExecutor(BatchResult(())),
            )
            empty_written = []

            blocked_code = blocked_application.run(
                root, preflight_only=True, write=lambda _: None
            )
            empty_code = empty_application.run(
                root, preflight_only=True, write=empty_written.append
            )

        self.assertEqual(blocked_code, 2)
        self.assertEqual(empty_code, 1)
        self.assertIn("Status: empty", empty_written[0])
        self.assertEqual(empty_written[-1], "Preflight result: failed\nExit code: 1")

    def test_resolves_audio_selection_relative_to_workspace(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "lesson.mkv"
            source.write_bytes(b"video")
            inventory = VideoInventory(source.resolve())
            planner = FakePlanner(BatchPlan(()))
            application = WorkspaceApplication(
                FakeDiscovery(DiscoveryResult((inventory,))),
                planner,
                FakeExecutor(BatchResult(())),
            )

            application.run(
                root,
                audio_selections=(AudioSelection("lesson.mkv", 4),),
                preflight_only=True,
                write=lambda _: None,
            )

        self.assertEqual(
            planner.calls[0][2],
            (PlanningChoice(source.resolve(), 4),),
        )

    def test_duplicate_audio_selection_fails_before_planning(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "lesson.mkv"
            source.write_bytes(b"video")
            planner = FakePlanner(BatchPlan(()))
            application = WorkspaceApplication(
                FakeDiscovery(DiscoveryResult((VideoInventory(source.resolve()),))),
                planner,
                FakeExecutor(BatchResult(())),
            )
            written = []

            exit_code = application.run(
                root,
                audio_selections=(
                    AudioSelection("lesson.mkv", 1),
                    AudioSelection(str(source), 2),
                ),
                write=written.append,
            )

        self.assertEqual(exit_code, 1)
        self.assertEqual(planner.calls, [])
        self.assertIn("Duplicate audio selection", written[0])

    def test_resume_proof_is_planned_and_passed_to_executor(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "lesson.mp4"
            output = root / "output" / "lesson.subtitled.mkv"
            source.write_bytes(b"video")
            inventory = VideoInventory(source.resolve(), existing_output=output)
            inspection = MediaInspection(
                (MediaStream(0, StreamKind.VIDEO, "h264"),),
                "matroska",
            )
            proof = PublishedOutput(
                source.resolve(), output, inspection, (), 10, 20
            )
            decisions = tuple(
                PlanDecision(stage, StageAction.SKIP, "Verified")
                for stage in EXECUTION_STAGES
            )
            plan = BatchPlan(
                (
                    VideoPlan(
                        inventory,
                        output,
                        root / "trash" / "lesson",
                        decisions,
                        uses_verified_output=True,
                    ),
                )
            )
            result = BatchResult(
                (VideoResult(source.resolve(), ResultStatus.SKIPPED, "Verified"),)
            )
            planner = FakePlanner(plan)
            executor = FakeExecutor(result)
            resumer = FakeResumer((proof,))
            application = WorkspaceApplication(
                FakeDiscovery(DiscoveryResult((inventory,))),
                planner,
                executor,
                resumer,
            )

            exit_code = application.run(root, resume=True, write=lambda _: None)

        self.assertEqual(exit_code, 0)
        self.assertEqual(planner.calls[0][2][0].verified_output, output)
        self.assertEqual(executor.calls[0][2], (proof,))

    def test_invalid_workspace_is_fatal_before_discovery(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            missing = Path(temp_dir) / "missing"
            discovery = FakeDiscovery(DiscoveryResult(()))
            application = WorkspaceApplication(
                discovery,
                FakePlanner(BatchPlan(())),
                FakeExecutor(BatchResult(())),
            )
            written = []

            exit_code = application.run(missing, write=written.append)

        self.assertEqual(exit_code, 1)
        self.assertEqual(discovery.calls, [])
        self.assertEqual(len(written), 1)
        self.assertIn("Batch result: failed", written[0])
        self.assertIn("InputPathError", written[0])
        self.assertIn(str(missing), written[0])


if __name__ == "__main__":
    unittest.main()
