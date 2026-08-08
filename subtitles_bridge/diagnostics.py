"""Portable, read-only runtime diagnostics for the command-line application."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
import platform
import shutil
import subprocess
import sys


CommandLocator = Callable[[str], str | None]
CommandRunner = Callable[..., subprocess.CompletedProcess[str]]
ModelChecker = Callable[[], Path]
Writer = Callable[[str], None]


class DiagnosticStatus(str, Enum):
    OK = "ok"
    WARNING = "warning"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class DiagnosticCheck:
    name: str
    status: DiagnosticStatus
    message: str

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("Diagnostic checks require a name")
        if not self.message.strip():
            raise ValueError("Diagnostic checks require a message")


@dataclass(frozen=True, slots=True)
class DiagnosticReport:
    checks: tuple[DiagnosticCheck, ...]

    @property
    def status(self) -> str:
        if any(check.status is DiagnosticStatus.ERROR for check in self.checks):
            return "failed"
        if any(check.status is DiagnosticStatus.WARNING for check in self.checks):
            return "warnings"
        return "ready"

    @property
    def exit_code(self) -> int:
        return 1 if self.status == "failed" else 0


def format_diagnostic_report(report: DiagnosticReport) -> str:
    lines = ["Runtime doctor"]
    lines.extend(
        f"[{check.status.value}] {check.name}: {check.message}"
        for check in report.checks
    )
    lines.extend(
        (
            f"Doctor result: {report.status}",
            f"Exit code: {report.exit_code}",
        )
    )
    return "\n".join(lines)


def format_diagnostic_fatal(error: Exception) -> str:
    message = str(error).strip() or repr(error)
    return "\n".join(
        (
            "Runtime doctor",
            f"[error] doctor: {type(error).__name__}: {message}",
            "Doctor result: failed",
            "Exit code: 1",
        )
    )


class RuntimeDoctor:
    def __init__(
        self,
        model_checker: ModelChecker,
        *,
        model_name: str,
        command_locator: CommandLocator = shutil.which,
        runner: CommandRunner = subprocess.run,
        python_executable: str = sys.executable,
        python_version: tuple[int, int, int] | None = None,
        python_version_text: str | None = None,
        minimum_python: tuple[int, int] = (3, 10),
        maximum_python_exclusive: tuple[int, int] = (3, 14),
        command_timeout_seconds: float = 10.0,
    ) -> None:
        if not model_name.strip():
            raise ValueError("Diagnostic Whisper model cannot be empty")
        if command_timeout_seconds <= 0:
            raise ValueError("Diagnostic command timeout must be positive")
        if maximum_python_exclusive <= minimum_python:
            raise ValueError("Diagnostic Python range must be increasing")
        self.model_checker = model_checker
        self.model_name = model_name
        self.command_locator = command_locator
        self.runner = runner
        self.python_executable = python_executable
        current = sys.version_info
        self.python_version = python_version or (
            current.major,
            current.minor,
            current.micro,
        )
        self.python_version_text = python_version_text or platform.python_version()
        self.minimum_python = minimum_python
        self.maximum_python_exclusive = maximum_python_exclusive
        self.command_timeout_seconds = command_timeout_seconds

    def inspect(self) -> DiagnosticReport:
        checks = [self._python_check()]
        checks.extend(self._command_check(name) for name in ("ffmpeg", "ffprobe"))
        checks.append(self._model_check())
        return DiagnosticReport(tuple(checks))

    def _python_check(self) -> DiagnosticCheck:
        minimum = ".".join(str(item) for item in self.minimum_python)
        maximum = ".".join(
            str(item)
            for item in (
                self.maximum_python_exclusive[0],
                self.maximum_python_exclusive[1] - 1,
            )
        )
        if not (
            self.minimum_python
            <= self.python_version[:2]
            < self.maximum_python_exclusive
        ):
            return DiagnosticCheck(
                "python",
                DiagnosticStatus.ERROR,
                (
                    f"Python {self.python_version_text} at {self.python_executable}; "
                    f"Python {minimum} through {maximum} is required"
                ),
            )
        return DiagnosticCheck(
            "python",
            DiagnosticStatus.OK,
            (
                f"Python {self.python_version_text} at {self.python_executable} "
                f"(supported {minimum} through {maximum})"
            ),
        )

    def _command_check(self, name: str) -> DiagnosticCheck:
        executable = self.command_locator(name)
        if executable is None:
            return DiagnosticCheck(
                name,
                DiagnosticStatus.ERROR,
                (
                    f"Not found on PATH. Install the FFmpeg package for your "
                    f"platform and ensure {name} is executable"
                ),
            )
        command = [executable, "-version"]
        try:
            result = self.runner(
                command,
                capture_output=True,
                text=True,
                check=False,
                timeout=self.command_timeout_seconds,
            )
        except Exception as exc:
            return DiagnosticCheck(
                name,
                DiagnosticStatus.ERROR,
                f"Cannot execute {executable}: {type(exc).__name__}: {exc}",
            )
        if result.returncode != 0:
            detail = result.stderr.strip() or result.stdout.strip() or "no details"
            return DiagnosticCheck(
                name,
                DiagnosticStatus.ERROR,
                f"{executable} -version failed with code {result.returncode}: {detail}",
            )
        version_line = (result.stdout.strip() or result.stderr.strip()).splitlines()
        detail = version_line[0] if version_line else "version command succeeded"
        return DiagnosticCheck(
            name,
            DiagnosticStatus.OK,
            f"{executable}: {detail}",
        )

    def _model_check(self) -> DiagnosticCheck:
        try:
            checkpoint = self.model_checker()
        except Exception as exc:
            message = str(exc).strip() or repr(exc)
            return DiagnosticCheck(
                "whisper-model",
                DiagnosticStatus.WARNING,
                (
                    f"Fallback model {self.model_name!r} is unavailable: "
                    f"{type(exc).__name__}: {message}"
                ),
            )
        return DiagnosticCheck(
            "whisper-model",
            DiagnosticStatus.OK,
            f"Fallback model {self.model_name!r} is available at {checkpoint}",
        )


class DoctorApplication:
    def __init__(self, doctor: RuntimeDoctor) -> None:
        self.doctor = doctor

    def run(self, *, write: Writer = print) -> int:
        try:
            report = self.doctor.inspect()
        except Exception as exc:
            write(format_diagnostic_fatal(exc))
            return 1
        write(format_diagnostic_report(report))
        return report.exit_code
