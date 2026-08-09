import tempfile
import unittest
from pathlib import Path

from subtitles_bridge.application import run_batch_application
from subtitles_bridge.models import (
    BatchPlan,
    BatchResult,
    PipelineStage,
    ResultStatus,
    StageResult,
    VideoResult,
)
from subtitles_bridge.paths import WorkspacePaths


class ResultExecutor:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def execute(self, batch_plan, paths, *, published_outputs=(), observer=None):
        self.calls.append((batch_plan, paths, tuple(published_outputs), observer))
        return self.result


class FailingExecutor:
    def execute(self, batch_plan, paths, *, published_outputs=(), observer=None):
        raise RuntimeError("fatal executor failure")


class BatchApplicationTests(unittest.TestCase):
    def test_prints_detailed_summary_and_returns_batch_exit_code(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            paths = WorkspacePaths.from_directory(root)
            source = (root / "lesson.mp4").resolve()
            source.write_bytes(b"video")
            output = paths.output_for(source)
            result = BatchResult(
                (
                    VideoResult(
                        source,
                        ResultStatus.PARTIAL,
                        f"archive failed for {source}: OSError: disk busy",
                        output,
                        stages=(
                            StageResult(
                                PipelineStage.ARCHIVE,
                                ResultStatus.FAILED,
                                f"{source}: OSError: disk busy",
                            ),
                        ),
                    ),
                )
            )
            executor = ResultExecutor(result)
            written = []

            exit_code = run_batch_application(
                executor,
                BatchPlan(()),
                paths,
                write=written.append,
            )

        self.assertEqual(exit_code, 3)
        self.assertEqual(len(executor.calls), 1)
        summary = written[0]
        self.assertIn("Batch result: partial", summary)
        self.assertIn("Exit code: 3", summary)
        self.assertIn("partial=1", summary)
        self.assertIn(f"Output: {output}", summary)
        self.assertIn("[failed] archive", summary)
        self.assertIn("OSError: disk busy", summary)

    def test_fatal_application_error_is_reported_as_failure(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = WorkspacePaths.from_directory(Path(temp_dir))
            written = []

            exit_code = run_batch_application(
                FailingExecutor(),
                BatchPlan(()),
                paths,
                write=written.append,
            )

        self.assertEqual(exit_code, 1)
        self.assertEqual(
            written,
            [
                "Batch result: failed\n"
                "Exit code: 1\n"
                "Fatal: RuntimeError: fatal executor failure"
            ],
        )


if __name__ == "__main__":
    unittest.main()
