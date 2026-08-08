import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def write_executable(path, content):
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)


@unittest.skipIf(os.name == "nt", "Bash wrapper tests require macOS or Linux")
class SetupShellTests(unittest.TestCase):
    def test_setup_uses_script_root_and_runs_portable_doctor(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "project"
            root.mkdir()
            shutil.copy2(PROJECT_ROOT / "setup.sh", root / "setup.sh")
            (root / "requirements.txt").write_text("example\n", encoding="utf-8")
            (root / "subtitles_bridge_cli.py").write_text("# launcher\n")
            caller = Path(temp_dir) / "caller"
            caller.mkdir()
            fake_bin = Path(temp_dir) / "bin"
            fake_bin.mkdir()
            trace = Path(temp_dir) / "python-arguments.txt"
            fake_python = fake_bin / "python3"
            write_executable(
                fake_python,
                """#!/bin/bash
if [ "$1" = "-c" ]; then
    echo "3.12.2"
    exit 0
fi
if [ "$1" = "-m" ] && [ "$2" = "venv" ]; then
    destination="$3"
    mkdir -p "$destination/bin"
    cat > "$destination/bin/python3" <<'INNER'
#!/bin/bash
printf '%s ' "$@" >> "$SETUP_TRACE"
printf '\n' >> "$SETUP_TRACE"
[ "$1" = "-c" ] && echo "3.12.2"
exit 0
INNER
    chmod +x "$destination/bin/python3"
    exit 0
fi
exit 1
""",
            )
            for tool in ("ffmpeg", "ffprobe"):
                write_executable(
                    fake_bin / tool,
                    f"#!/bin/sh\necho '{tool} version test'\nexit 0\n",
                )
            environment = {
                **os.environ,
                "PATH": f"{fake_bin}:/usr/bin:/bin",
                "SETUP_TRACE": str(trace),
            }

            completed = subprocess.run(
                ["bash", str(root / "setup.sh")],
                cwd=caller,
                text=True,
                capture_output=True,
                env=environment,
                timeout=10,
                check=False,
            )
            venv_python_exists = (root / ".venv" / "bin" / "python3").is_file()
            caller_venv_exists = (caller / ".venv").exists()
            python_calls = trace.read_text(encoding="utf-8")

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertTrue(venv_python_exists)
        self.assertFalse(caller_venv_exists)
        self.assertIn("-m pip install --upgrade pip", python_calls)
        self.assertIn(
            f"-m pip install -r {root / 'requirements.txt'}",
            python_calls,
        )
        self.assertIn(f"{root / 'subtitles_bridge_cli.py'} --doctor", python_calls)
        self.assertIn("not downloaded automatically", completed.stdout)
        self.assertIn("whisper.load_model('small')", completed.stdout)

    def test_missing_media_tool_fails_before_creating_venv(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "project"
            root.mkdir()
            shutil.copy2(PROJECT_ROOT / "setup.sh", root / "setup.sh")
            fake_bin = Path(temp_dir) / "bin"
            fake_bin.mkdir()
            write_executable(
                fake_bin / "python3",
                '#!/bin/sh\n[ "$1" = "-c" ] && echo 3.12.2 && exit 0\nexit 1\n',
            )
            write_executable(
                fake_bin / "ffprobe",
                "#!/bin/sh\necho 'ffprobe version test'\nexit 0\n",
            )
            environment = {
                **os.environ,
                "PATH": f"{fake_bin}:/usr/bin:/bin",
            }

            completed = subprocess.run(
                ["bash", str(root / "setup.sh")],
                text=True,
                capture_output=True,
                env=environment,
                timeout=10,
                check=False,
            )

        self.assertEqual(completed.returncode, 1)
        self.assertIn("ffmpeg was not found", completed.stdout)
        self.assertIn("platform's package manager", completed.stdout)
        self.assertFalse((root / ".venv").exists())

    def test_setup_does_not_assume_or_invoke_homebrew(self):
        content = (PROJECT_ROOT / "setup.sh").read_text(encoding="utf-8")

        self.assertNotIn("brew", content)
        self.assertNotIn("llvm", content.casefold())

    def test_setup_enforces_the_documented_python_range(self):
        content = (PROJECT_ROOT / "setup.sh").read_text(encoding="utf-8")

        self.assertEqual(content.count("(3, 10) <= sys.version_info < (3, 14)"), 2)
        self.assertIn("Python 3.10 through 3.13 is required", content)
        self.assertNotIn("requirements-legacy.txt", content)


if __name__ == "__main__":
    unittest.main()
