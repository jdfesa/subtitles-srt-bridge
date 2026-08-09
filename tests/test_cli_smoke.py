import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CLI = PROJECT_ROOT / "subtitles_bridge_cli.py"


class CliSmokeTests(unittest.TestCase):
    def test_help_runs_without_runtime_dependencies(self):
        completed = subprocess.run(
            [sys.executable, str(CLI), "--help"],
            cwd=PROJECT_ROOT,
            text=True,
            capture_output=True,
            timeout=10,
            check=False,
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("usage: subtitles-bridge", completed.stdout)
        self.assertIn("--preflight", completed.stdout)

    def test_empty_preflight_is_read_only_and_needs_no_media_backend(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            completed = subprocess.run(
                [sys.executable, str(CLI), str(workspace), "--preflight"],
                cwd=PROJECT_ROOT,
                text=True,
                capture_output=True,
                timeout=10,
                check=False,
            )
            managed_paths = [
                workspace / name for name in ("output", "staging", "trash")
            ]

        self.assertEqual(completed.returncode, 1, completed.stderr)
        self.assertIn("Batch: 0 video(s)", completed.stdout)
        self.assertIn("Status: empty", completed.stdout)
        self.assertIn("Preflight result: failed", completed.stdout)
        self.assertTrue(all(not path.exists() for path in managed_paths))

    def test_empty_preflight_jsonl_has_no_mixed_stdout(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            completed = subprocess.run(
                [
                    sys.executable,
                    str(CLI),
                    str(workspace),
                    "--preflight",
                    "--output-format",
                    "jsonl",
                ],
                cwd=PROJECT_ROOT,
                text=True,
                capture_output=True,
                timeout=10,
                check=False,
            )
            managed_paths = [
                workspace / name for name in ("output", "staging", "trash")
            ]

        records = [json.loads(line) for line in completed.stdout.splitlines()]
        self.assertEqual(completed.returncode, 1, completed.stderr)
        self.assertEqual(
            [record["event"] for record in records],
            [
                "preflight",
                "preflight-result",
            ],
        )
        self.assertEqual(records[-1]["exit_code"], 1)
        self.assertTrue(all(not path.exists() for path in managed_paths))
