import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


@unittest.skipIf(os.name == "nt", "Bash wrapper tests require macOS or Linux")
class MenuShellTests(unittest.TestCase):
    def _run_menu(self, interaction, fake_python_source, *, trace=None):
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        root = Path(temp_dir.name)
        shutil.copy2(PROJECT_ROOT / "menu.sh", root / "menu.sh")
        caller = root / "caller"
        caller.mkdir()
        fake_python = root / ".venv" / "bin" / "python3"
        fake_python.parent.mkdir(parents=True)
        fake_python.write_text(fake_python_source, encoding="utf-8")
        fake_python.chmod(0o755)
        environment = {**os.environ, "TERM": "xterm"}
        if trace is not None:
            environment["TRACE_FILE"] = str(trace)
        if callable(interaction):
            interaction = interaction(root)
        return subprocess.run(
            ["bash", str(root / "menu.sh")],
            cwd=caller,
            input=interaction,
            text=True,
            capture_output=True,
            env=environment,
            timeout=10,
            check=False,
        ), root

    def test_menu_does_not_announce_success_for_failed_process(self):
        with tempfile.TemporaryDirectory() as trace_dir:
            trace = Path(trace_dir) / "arguments.txt"

            def interaction(root):
                media = root / "media folder"
                media.mkdir()
                escaped_media = str(media).replace(" ", "\\ ")
                return f"3\n{escaped_media}\n\n8\n"

            completed, root = self._run_menu(
                interaction,
                '#!/bin/sh\nprintf \'%s\\n\' "$@" > "$TRACE_FILE"\nexit 1\n',
                trace=trace,
            )
            media = root / "media folder"
            traced_arguments = trace.read_text(encoding="utf-8").splitlines()

        output = completed.stdout + completed.stderr
        self.assertEqual(completed.returncode, 0)
        self.assertIn("Procesamiento falló (código 1)", output)
        self.assertNotIn("Procesamiento finalizado correctamente", output)
        self.assertEqual(
            traced_arguments,
            [str(root / "subtitles_bridge_cli.py"), str(media)],
        )

    def test_menu_exposes_preflight_resume_and_doctor_with_exact_arguments(self):
        with tempfile.TemporaryDirectory() as trace_dir:
            trace = Path(trace_dir) / "arguments.txt"

            def interaction(root):
                media = root / "media folder"
                media.mkdir()
                return f"2\n{media}\n\n4\n{media}\n\n5\n\n8\n"

            completed, root = self._run_menu(
                interaction,
                ('#!/bin/sh\nprintf \'%s\\n\' --- "$@" >> "$TRACE_FILE"\nexit 0\n'),
                trace=trace,
            )
            media = root / "media folder"
            traced = trace.read_text(encoding="utf-8").splitlines()

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(
            traced,
            [
                "---",
                str(root / "subtitles_bridge_cli.py"),
                str(media),
                "--preflight",
                "---",
                str(root / "subtitles_bridge_cli.py"),
                str(media),
                "--resume",
                "---",
                str(root / "subtitles_bridge_cli.py"),
                "--doctor",
            ],
        )
        output = completed.stdout + completed.stderr
        self.assertIn("Inspección completada", output)
        self.assertIn("Reanudación completada", output)
        self.assertIn("Diagnóstico finalizado", output)

    def test_menu_explains_pending_and_partial_exit_codes(self):
        completed, _root = self._run_menu(
            "2\n.\n\n4\n.\n\n8\n",
            (
                "#!/bin/sh\n"
                'case " $* " in\n'
                "  *' --preflight '*) exit 2 ;;\n"
                "  *' --resume '*) exit 3 ;;\n"
                "esac\n"
                "exit 0\n"
            ),
        )

        output = completed.stdout + completed.stderr
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("necesita una decisión (código 2)", output)
        self.assertIn("Resultado parcial (código 3)", output)
        self.assertIn("el MKV publicado se conserva", output)

    def test_menu_help_states_the_subtitle_goal_and_safety_boundary(self):
        completed, _root = self._run_menu(
            "6\n\n8\n",
            "#!/bin/sh\nexit 0\n",
        )

        output = completed.stdout + completed.stderr
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("OBJETIVO", output)
        self.assertIn("pistas seleccionables", output)
        self.assertIn("No comprime ni recodifica audio o video", output)
        self.assertIn("cuarentena reversible", output)


if __name__ == "__main__":
    unittest.main()
