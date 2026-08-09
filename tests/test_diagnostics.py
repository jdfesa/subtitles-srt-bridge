import json
import subprocess
import unittest
from pathlib import Path

from subtitles_bridge.diagnostics import (
    DiagnosticStatus,
    DoctorApplication,
    RuntimeDoctor,
)
from subtitles_bridge.observability import OutputFormat


class RuntimeDoctorTests(unittest.TestCase):
    @staticmethod
    def locator(name):
        return f"/tools/{name}"

    @staticmethod
    def successful_runner(command, **options):
        name = Path(command[0]).name
        return subprocess.CompletedProcess(
            command,
            0,
            f"{name} version 7.0\n",
            "",
        )

    def make_doctor(self, model_checker=lambda: Path("/cache/small.pt"), **kwargs):
        return RuntimeDoctor(
            model_checker,
            model_name="small",
            command_locator=self.locator,
            runner=self.successful_runner,
            python_executable="/env/bin/python",
            python_version=(3, 12, 2),
            python_version_text="3.12.2",
            **kwargs,
        )

    def test_reports_ready_when_required_tools_and_model_are_available(self):
        runner_calls = []

        def runner(command, **options):
            runner_calls.append((command, options))
            return self.successful_runner(command, **options)

        doctor = self.make_doctor()
        doctor.runner = runner

        report = doctor.inspect()

        self.assertEqual(report.status, "ready")
        self.assertEqual(report.exit_code, 0)
        self.assertTrue(
            all(check.status is DiagnosticStatus.OK for check in report.checks)
        )
        self.assertEqual(
            [call[0] for call in runner_calls],
            [["/tools/ffmpeg", "-version"], ["/tools/ffprobe", "-version"]],
        )
        self.assertEqual(
            runner_calls[0][1],
            {
                "capture_output": True,
                "text": True,
                "check": False,
                "timeout": 10.0,
            },
        )

    def test_missing_model_is_a_successful_warning(self):
        def missing_model():
            raise RuntimeError("preload explicitly")

        report = self.make_doctor(missing_model).inspect()

        self.assertEqual(report.status, "warnings")
        self.assertEqual(report.exit_code, 0)
        model = report.checks[-1]
        self.assertEqual(model.status, DiagnosticStatus.WARNING)
        self.assertIn("preload explicitly", model.message)

    def test_missing_or_failing_required_tool_returns_failure(self):
        def locator(name):
            return None if name == "ffprobe" else f"/tools/{name}"

        def runner(command, **options):
            return subprocess.CompletedProcess(command, 2, "", "broken binary")

        doctor = self.make_doctor()
        doctor.command_locator = locator
        doctor.runner = runner

        report = doctor.inspect()

        self.assertEqual(report.status, "failed")
        self.assertEqual(report.exit_code, 1)
        self.assertIn("code 2", report.checks[1].message)
        self.assertIn("Not found on PATH", report.checks[2].message)

    def test_old_python_and_runner_exception_are_actionable_errors(self):
        def runner(command, **options):
            raise OSError("cannot execute")

        doctor = RuntimeDoctor(
            lambda: Path("/cache/small.pt"),
            model_name="small",
            command_locator=self.locator,
            runner=runner,
            python_executable="/old/python",
            python_version=(3, 9, 18),
            python_version_text="3.9.18",
        )

        report = doctor.inspect()

        self.assertEqual(report.exit_code, 1)
        self.assertIn("3.10 through 3.13", report.checks[0].message)
        self.assertIn("OSError: cannot execute", report.checks[1].message)

    def test_python_newer_than_supported_range_is_an_actionable_error(self):
        doctor = RuntimeDoctor(
            lambda: Path("/cache/small.pt"),
            model_name="small",
            command_locator=self.locator,
            runner=self.successful_runner,
            python_executable="/new/python",
            python_version=(3, 14, 0),
            python_version_text="3.14.0",
        )

        report = doctor.inspect()

        self.assertEqual(report.exit_code, 1)
        self.assertEqual(report.checks[0].status, DiagnosticStatus.ERROR)
        self.assertIn("3.10 through 3.13", report.checks[0].message)

    def test_latest_supported_python_minor_is_ready(self):
        doctor = self.make_doctor()
        doctor.python_version = (3, 13, 9)
        doctor.python_version_text = "3.13.9"

        report = doctor.inspect()

        self.assertEqual(report.checks[0].status, DiagnosticStatus.OK)
        self.assertIn("supported 3.10 through 3.13", report.checks[0].message)

    def test_application_formats_deterministic_report(self):
        written = []

        exit_code = DoctorApplication(self.make_doctor()).run(write=written.append)

        self.assertEqual(exit_code, 0)
        self.assertEqual(len(written), 1)
        self.assertTrue(written[0].startswith("Runtime doctor\n[ok] python:"))
        self.assertTrue(written[0].endswith("Doctor result: ready\nExit code: 0"))

    def test_application_can_emit_one_jsonl_doctor_result(self):
        written = []

        exit_code = DoctorApplication(self.make_doctor()).run(
            write=written.append,
            output_format=OutputFormat.JSONL,
        )

        record = json.loads(written[0])
        self.assertEqual(exit_code, 0)
        self.assertEqual(len(written), 1)
        self.assertEqual(record["event"], "doctor-result")
        self.assertEqual(record["schema_version"], 1)
        self.assertEqual(record["checks"][0]["name"], "python")


if __name__ == "__main__":
    unittest.main()
