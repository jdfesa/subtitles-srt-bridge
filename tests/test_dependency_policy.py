import re
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def declared_requirements(filename):
    return [
        line.strip()
        for line in (PROJECT_ROOT / filename).read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


class DependencyPolicyTests(unittest.TestCase):
    def test_main_pipeline_has_one_pinned_direct_dependency(self):
        self.assertEqual(
            declared_requirements("requirements.txt"),
            ["openai-whisper==20250625"],
        )

    def test_legacy_translation_dependency_is_isolated_and_pinned(self):
        self.assertEqual(
            declared_requirements("requirements-legacy.txt"),
            ["deep-translator==1.11.4"],
        )

    def test_development_dependency_is_isolated_and_pinned(self):
        self.assertEqual(
            declared_requirements("requirements-dev.txt"),
            ["ruff==0.15.22"],
        )
        setup = (PROJECT_ROOT / "setup.sh").read_text(encoding="utf-8")
        self.assertNotIn("requirements-dev.txt", setup)

    def test_quality_gate_and_ci_share_pinned_tool_versions(self):
        quality_gate = (PROJECT_ROOT / "tools/check.py").read_text(encoding="utf-8")
        workflow = (PROJECT_ROOT / ".github/workflows/checks.yml").read_text(
            encoding="utf-8"
        )

        self.assertIn("0.15.22", quality_gate)
        self.assertIn("requirements-dev.txt", workflow)
        for tool_version in ("0.11.0", "3.13.1"):
            with self.subTest(tool_version=tool_version):
                self.assertIn(tool_version, quality_gate)
                self.assertIn(tool_version, workflow)

    def test_main_requirements_do_not_pin_whisper_transitive_dependencies(self):
        content = "\n".join(declared_requirements("requirements.txt")).casefold()

        for dependency in ("numpy", "numba", "llvmlite", "torch"):
            with self.subTest(dependency=dependency):
                self.assertNotIn(dependency, content)

    def test_whisper_repair_command_uses_the_same_direct_pin(self):
        adapter = (PROJECT_ROOT / "subtitles_bridge/adapters/whisper.py").read_text(
            encoding="utf-8"
        )
        direct_pin = declared_requirements("requirements.txt")[0]

        self.assertIn(direct_pin, adapter)
        self.assertNotRegex(adapter, re.compile(r"pip install openai-whisper[\"']"))


if __name__ == "__main__":
    unittest.main()
