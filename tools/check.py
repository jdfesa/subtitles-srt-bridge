#!/usr/bin/env python3
"""Run the complete local quality gate without modifying repository files."""

from __future__ import annotations

import shutil
import subprocess
import sys
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXPECTED_RUFF_VERSION = "0.15.22"
EXPECTED_SHFMT_VERSION = "v3.13.1"
EXPECTED_SHELLCHECK_VERSION = "0.11.0"
SHELL_SCRIPTS = ("menu.sh", "setup.sh")


def _require_python_tool() -> bool:
    try:
        installed = version("ruff")
    except PackageNotFoundError:
        print(
            "Missing Ruff. Install development tools with: "
            f'"{sys.executable}" -m pip install -r '
            f'"{PROJECT_ROOT / "requirements-dev.txt"}"',
            file=sys.stderr,
        )
        return False
    if installed != EXPECTED_RUFF_VERSION:
        print(
            f"Unsupported Ruff {installed}; expected {EXPECTED_RUFF_VERSION}. "
            "Reinstall requirements-dev.txt.",
            file=sys.stderr,
        )
        return False
    return True


def _require_external_tool(
    name: str,
    *,
    version_args: tuple[str, ...],
    expected_text: str,
) -> str | None:
    executable = shutil.which(name)
    if executable is None:
        print(
            f"Missing {name}. Install the documented version before running checks.",
            file=sys.stderr,
        )
        return None
    completed = subprocess.run(
        [executable, *version_args],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    output = f"{completed.stdout}\n{completed.stderr}".strip()
    if completed.returncode != 0 or expected_text not in output:
        print(
            f"Unsupported {name} output; expected {expected_text!r}, got "
            f"{output or 'no version output'!r}.",
            file=sys.stderr,
        )
        return None
    return executable


def _run(command: list[str]) -> int:
    print("+", " ".join(command), flush=True)
    return subprocess.run(command, cwd=PROJECT_ROOT, check=False).returncode


def main() -> int:
    if not _require_python_tool():
        return 1
    shfmt = _require_external_tool(
        "shfmt",
        version_args=("--version",),
        expected_text=EXPECTED_SHFMT_VERSION,
    )
    shellcheck = _require_external_tool(
        "shellcheck",
        version_args=("--version",),
        expected_text=f"version: {EXPECTED_SHELLCHECK_VERSION}",
    )
    if shfmt is None or shellcheck is None:
        return 1

    commands = (
        [sys.executable, "-m", "ruff", "check", "."],
        [sys.executable, "-m", "ruff", "format", "--check", "."],
        [shfmt, "-d", "-i", "4", "-ci", *SHELL_SCRIPTS],
        [shellcheck, *SHELL_SCRIPTS],
        [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-q"],
    )
    for command in commands:
        exit_code = _run(command)
        if exit_code != 0:
            return exit_code
    print("All checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
