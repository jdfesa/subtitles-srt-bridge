import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class SetupShellTests(unittest.TestCase):
    def test_setup_uses_script_root_for_venv_and_requirements(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "project"
            root.mkdir()
            shutil.copy2(PROJECT_ROOT / "setup.sh", root / "setup.sh")
            (root / "requirements.txt").write_text("example\n", encoding="utf-8")
            caller = Path(temp_dir) / "caller"
            caller.mkdir()
            fake_bin = Path(temp_dir) / "bin"
            fake_bin.mkdir()
            trace = Path(temp_dir) / "pip-arguments.txt"
            fake_python = fake_bin / "python3"
            fake_python.write_text(
                """#!/bin/bash
destination="$3"
mkdir -p "$destination/bin"
cat > "$destination/bin/python3" <<'INNER'
#!/bin/bash
printf '%s ' "$@" >> "$SETUP_TRACE"
printf '\n' >> "$SETUP_TRACE"
exit 0
INNER
chmod +x "$destination/bin/python3"
""",
                encoding="utf-8",
            )
            fake_python.chmod(0o755)
            fake_uname = fake_bin / "uname"
            fake_uname.write_text("#!/bin/sh\necho Linux\n", encoding="utf-8")
            fake_uname.chmod(0o755)
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
            venv_python_exists = (
                root / ".venv" / "bin" / "python3"
            ).is_file()
            caller_venv_exists = (caller / ".venv").exists()
            pip_calls = trace.read_text(encoding="utf-8")

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertTrue(venv_python_exists)
        self.assertFalse(caller_venv_exists)
        self.assertIn("-m pip install --upgrade pip", pip_calls)
        self.assertIn(
            f"-m pip install -r {root / 'requirements.txt'}",
            pip_calls,
        )


if __name__ == "__main__":
    unittest.main()
