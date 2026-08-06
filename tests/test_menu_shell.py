import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class MenuShellTests(unittest.TestCase):
    def test_menu_does_not_announce_success_for_failed_process(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            shutil.copy2(PROJECT_ROOT / "menu.sh", root / "menu.sh")
            fake_python = root / ".venv" / "bin" / "python3"
            fake_python.parent.mkdir(parents=True)
            fake_python.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
            fake_python.chmod(0o755)
            interaction = "2\n.\n\n5\n"
            environment = {**os.environ, "TERM": "xterm"}

            completed = subprocess.run(
                ["bash", "menu.sh"],
                cwd=root,
                input=interaction,
                text=True,
                capture_output=True,
                env=environment,
                timeout=10,
                check=False,
            )

        output = completed.stdout + completed.stderr
        self.assertEqual(completed.returncode, 0)
        self.assertIn("Proceso no completado (código 1)", output)
        self.assertNotIn("Proceso finalizado correctamente", output)


if __name__ == "__main__":
    unittest.main()
