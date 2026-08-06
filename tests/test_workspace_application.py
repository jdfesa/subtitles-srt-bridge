from pathlib import Path
import tempfile
import unittest

from subtitles_bridge.models import (
    BatchPlan,
    BatchResult,
    DiscoveryResult,
    PipelineStage,
    PlanDecision,
    ResultStatus,
    StageAction,
    StageResult,
    VideoInventory,
    VideoPlan,
    VideoResult,
)
from subtitles_bridge.workspace_application import WorkspaceApplication


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

    def plan(self, discovery, paths):
        self.calls.append((discovery, paths))
        return self.plan_result


class FakeExecutor:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def execute(self, batch_plan, paths, *, published_outputs=()):
        self.calls.append((batch_plan, paths, tuple(published_outputs)))
        return self.result


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
