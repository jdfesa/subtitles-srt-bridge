import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from subtitles_bridge.bootstrap import build_default_workspace_application
from subtitles_bridge.cli import main
from subtitles_bridge.workspace_application import WorkspaceApplication


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class RecordingApplication:
    def __init__(self, exit_code=0):
        self.exit_code = exit_code
        self.calls = []

    def run(self, directory, *, write=print):
        self.calls.append((directory, write))
        write(f"ran {directory}")
        return self.exit_code


class CliTests(unittest.TestCase):
    def test_passes_positional_or_default_directory_to_application(self):
        application = RecordingApplication(exit_code=3)
        written = []

        explicit = main(
            ["/media/input"],
            application_factory=lambda: application,
            write=written.append,
        )
        default = main(
            [],
            application_factory=lambda: application,
            write=written.append,
        )

        self.assertEqual((explicit, default), (3, 3))
        self.assertEqual(
            [call[0] for call in application.calls],
            ["/media/input", "."],
        )
        self.assertEqual(written, ["ran /media/input", "ran ."])

    def test_reports_application_construction_failure(self):
        def fail():
            raise RuntimeError("cannot compose application")

        written = []

        exit_code = main([], application_factory=fail, write=written.append)

        self.assertEqual(exit_code, 1)
        self.assertIn("RuntimeError: cannot compose application", written[0])

    def test_default_composition_is_lazy_and_uses_application_boundary(self):
        application = build_default_workspace_application()

        self.assertIsInstance(application, WorkspaceApplication)
        recognizer = application.executor.transcription.transcriber.recognizer
        self.assertIsNone(recognizer._model)

    def test_direct_and_module_launchers_share_the_cli(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            caller = Path(temp_dir)
            missing = caller / "missing"
            direct = subprocess.run(
                [
                    sys.executable,
                    str(PROJECT_ROOT / "subtitles_bridge_cli.py"),
                    str(missing),
                ],
                cwd=caller,
                text=True,
                capture_output=True,
                env=os.environ.copy(),
                timeout=10,
                check=False,
            )
            module = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "subtitles_bridge",
                    str(missing),
                ],
                cwd=PROJECT_ROOT,
                text=True,
                capture_output=True,
                env=os.environ.copy(),
                timeout=10,
                check=False,
            )

        for completed in (direct, module):
            self.assertEqual(completed.returncode, 1)
            self.assertIn("Batch result: failed", completed.stdout)
            self.assertIn(str(missing), completed.stdout)
            self.assertNotIn("ModuleNotFoundError", completed.stderr)


if __name__ == "__main__":
    unittest.main()
