import json
import unittest
from pathlib import Path

from subtitles_bridge.models import (
    BatchPlan,
    BatchResult,
    FailureDetail,
    PipelineStage,
    PlanDecision,
    ResultStatus,
    StageAction,
    StageResult,
    VideoInventory,
    VideoPlan,
    VideoResult,
)
from subtitles_bridge.observability import (
    JsonLinesReporter,
    StageEventKind,
    StageExecutionEvent,
)


class JsonLinesReporterTests(unittest.TestCase):
    def make_plan(self):
        videos = []
        for name, duration in (("first.mp4", 100.0), ("second.mp4", 50.0)):
            source = Path("/media") / name
            inventory = VideoInventory(source, duration_seconds=duration)
            decisions = (
                PlanDecision(
                    PipelineStage.TRANSCRIBE,
                    StageAction.SKIP,
                    "Subtitles already exist",
                ),
                PlanDecision(PipelineStage.MUX, StageAction.RUN, "Build output"),
                PlanDecision(PipelineStage.VERIFY, StageAction.RUN, "Verify output"),
                PlanDecision(PipelineStage.PUBLISH, StageAction.RUN, "Publish output"),
                PlanDecision(PipelineStage.ARCHIVE, StageAction.RUN, "Archive inputs"),
            )
            videos.append(
                VideoPlan(
                    inventory,
                    Path("/media/output") / f"{source.stem}.subtitled.mkv",
                    Path("/media/trash") / source.stem,
                    decisions,
                )
            )
        return BatchPlan(tuple(videos))

    def event(self, source, stage, duration):
        return StageExecutionEvent(
            StageEventKind.FINISHED,
            source,
            stage,
            Path("/media/staging") / f"{source.stem}.subtitled.mkv",
            f"Finished {stage.value}",
            ResultStatus.COMPLETED,
            duration,
        )

    def test_emits_independent_versioned_records_and_learns_eta(self):
        written = []
        reporter = JsonLinesReporter(written.append)
        plan = self.make_plan()
        first, second = (video.inventory.source for video in plan.videos)

        reporter.preflight(plan)
        reporter.stage_event(self.event(first, PipelineStage.MUX, 10.0))
        reporter.stage_event(self.event(first, PipelineStage.VERIFY, 20.0))

        records = [json.loads(line) for line in written]
        self.assertEqual([record["sequence"] for record in records], [1, 2, 3])
        self.assertTrue(all(record["schema_version"] == 1 for record in records))
        self.assertEqual(records[0]["event"], "preflight")
        self.assertEqual(records[0]["remaining_expensive_stages"], 4)
        self.assertIsNone(records[0]["eta_seconds"])
        self.assertIsNone(records[1]["eta_seconds"])
        self.assertEqual(records[2]["remaining_expensive_stages"], 2)
        self.assertEqual(records[2]["eta_seconds"], 15.0)
        self.assertEqual(records[2]["source"], str(first))
        self.assertNotEqual(first, second)

    def test_partial_result_is_self_contained_and_auditable(self):
        source = Path("/media/lesson.mp4")
        output = Path("/media/output/lesson.subtitled.mkv")
        trash = Path("/media/trash/lesson")
        failure = FailureDetail("OSError", "disk busy", trash)
        result = BatchResult(
            (
                VideoResult(
                    source,
                    ResultStatus.PARTIAL,
                    "archive failed",
                    output,
                    trash,
                    (
                        StageResult(
                            PipelineStage.ARCHIVE,
                            ResultStatus.FAILED,
                            "archive failed",
                            1.25,
                            failure,
                        ),
                    ),
                ),
            )
        )
        written = []

        JsonLinesReporter(written.append).batch_result(result)

        record = json.loads(written[0])
        video = record["result"]["videos"][0]
        self.assertEqual(record["event"], "batch-result")
        self.assertEqual(record["result"]["exit_code"], 3)
        self.assertEqual(video["recovery"]["pending_stage"], "archive")
        self.assertEqual(video["recovery"]["option"], "--resume")
        self.assertEqual(video["recovery"]["published_output"], str(output))
        self.assertEqual(video["recovery"]["trash_path"], str(trash))
        self.assertEqual(video["stages"][0]["failure"]["type"], "OSError")

    def test_fatal_record_contains_no_free_text_prefix(self):
        written = []

        JsonLinesReporter(written.append).fatal("batch", RuntimeError("broken"))

        record = json.loads(written[0])
        self.assertEqual(record["event"], "fatal")
        self.assertEqual(record["error"], {"message": "broken", "type": "RuntimeError"})


if __name__ == "__main__":
    unittest.main()
