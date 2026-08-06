from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import process_videos


VALID_SRT = "1\n00:00:00,000 --> 00:00:01,000\nHello\n"


class NormalizePathTests(unittest.TestCase):
    def test_unescapes_terminal_drag_and_drop_path(self):
        with patch("process_videos.os.path.exists", return_value=False):
            result = process_videos.normalize_path("/tmp/My\\ Folder/video.mp4")

        self.assertEqual(result, "/tmp/My Folder/video.mp4")

    def test_preserves_an_existing_path_verbatim(self):
        raw_path = "/tmp/a\\literal\\path"

        with patch("process_videos.os.path.exists", return_value=True):
            result = process_videos.normalize_path(raw_path)

        self.assertEqual(result, raw_path)


class WhisperResolutionTests(unittest.TestCase):
    def test_prefers_whisper_available_on_path(self):
        with patch("process_videos.shutil.which", return_value="/opt/bin/whisper"):
            result = process_videos.check_whisper_installed()

        self.assertEqual(result, "/opt/bin/whisper")

    @unittest.expectedFailure
    def test_resolves_whisper_next_to_the_active_python(self):
        """P0.1 reproduction: setup's .venv/bin/whisper is currently ignored."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            active_python = root / ".venv" / "bin" / "python3"
            active_whisper = active_python.with_name("whisper")
            active_whisper.parent.mkdir(parents=True)
            active_python.touch()
            active_whisper.touch()

            with (
                patch("process_videos.shutil.which", return_value=None),
                patch.object(process_videos.sys, "executable", str(active_python)),
                patch.object(process_videos.Path, "home", return_value=root / "home"),
                redirect_stdout(StringIO()),
            ):
                result = process_videos.check_whisper_installed()

        self.assertEqual(result, str(active_whisper))


class WhisperCommandTests(unittest.TestCase):
    def test_builds_legacy_command_and_renames_whisper_output(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            video = root / "lesson.mp4"
            video.touch()

            def fake_run(command, check):
                self.assertTrue(check)
                video.with_suffix(".srt").write_text(VALID_SRT, encoding="utf-8")
                return subprocess.CompletedProcess(command, 0)

            with (
                patch("process_videos.subprocess.run", side_effect=fake_run) as run,
                redirect_stdout(StringIO()),
            ):
                result = process_videos.generate_english_subtitle(
                    video,
                    "/opt/bin/whisper",
                )

            self.assertEqual(result, video.with_suffix(".en.srt"))
            self.assertFalse(video.with_suffix(".srt").exists())
            self.assertTrue(video.with_suffix(".en.srt").exists())
            self.assertEqual(
                run.call_args.args[0],
                [
                    "/opt/bin/whisper",
                    str(video),
                    "--task",
                    "transcribe",
                    "--language",
                    "en",
                    "--model",
                    "small",
                    "--fp16",
                    "False",
                    "--output_format",
                    "srt",
                    "--output_dir",
                    str(root),
                ],
            )

    def test_returns_none_when_whisper_process_fails(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            video = Path(temp_dir) / "lesson.mp4"
            video.touch()

            with (
                patch(
                    "process_videos.subprocess.run",
                    side_effect=subprocess.CalledProcessError(2, ["whisper"]),
                ),
                redirect_stdout(StringIO()),
            ):
                result = process_videos.generate_english_subtitle(video, "whisper")

        self.assertIsNone(result)

    @unittest.expectedFailure
    def test_whisper_writes_to_staging_instead_of_the_source_directory(self):
        """P0.1 reproduction: Whisper currently writes beside user media."""
        with tempfile.TemporaryDirectory() as temp_dir:
            video = Path(temp_dir) / "lesson.mp4"
            video.touch()

            with (
                patch(
                    "process_videos.subprocess.run",
                    return_value=subprocess.CompletedProcess(["whisper"], 0),
                ) as run,
                redirect_stdout(StringIO()),
            ):
                process_videos.generate_english_subtitle(video, "whisper")

            command = run.call_args.args[0]
            output_directory = Path(command[command.index("--output_dir") + 1])

        self.assertNotEqual(output_directory, video.parent)


class LegacyDirectoryProcessingTests(unittest.TestCase):
    def test_skips_video_when_both_legacy_sidecars_exist(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "lesson.mp4").touch()
            (root / "lesson.srt").write_text(VALID_SRT, encoding="utf-8")
            sub_en = root / "sub_en"
            sub_en.mkdir()
            (sub_en / "lesson.en.srt").write_text(VALID_SRT, encoding="utf-8")

            with (
                patch("process_videos.check_whisper_installed", return_value="whisper"),
                patch("process_videos.generate_english_subtitle") as generate,
                patch("process_videos.translate_to_spanish") as translate,
                redirect_stdout(StringIO()),
            ):
                result = process_videos.process_directory(str(root))

        generate.assert_not_called()
        translate.assert_not_called()
        self.assertEqual(result, 0)

    @unittest.expectedFailure
    def test_does_not_treat_empty_sidecars_as_completed_work(self):
        """P0.1 reproduction: existence is currently the only completion check."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "lesson.mp4").touch()
            (root / "lesson.srt").touch()
            sub_en = root / "sub_en"
            sub_en.mkdir()
            (sub_en / "lesson.en.srt").touch()

            with (
                patch("process_videos.check_whisper_installed", return_value="whisper"),
                patch("process_videos.generate_english_subtitle") as generate,
                patch("process_videos.translate_to_spanish") as translate,
                redirect_stdout(StringIO()),
            ):
                process_videos.process_directory(str(root))

        self.assertTrue(generate.called or translate.called)

    def test_reports_failure_with_nonzero_status_for_missing_directory(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            missing = Path(temp_dir) / "missing"
            with redirect_stdout(StringIO()):
                result = process_videos.process_directory(str(missing))

        self.assertIsInstance(result, int)
        self.assertNotEqual(result, 0)

    def test_reports_failure_without_loading_whisper_for_empty_directory(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with (
                patch("process_videos.check_whisper_installed") as check,
                redirect_stdout(StringIO()),
            ):
                result = process_videos.process_directory(temp_dir)

        self.assertNotEqual(result, 0)
        check.assert_not_called()

    def test_reports_failure_when_a_video_cannot_generate_a_subtitle(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "lesson.mp4").touch()
            with (
                patch(
                    "process_videos.check_whisper_installed",
                    return_value="whisper",
                ),
                patch(
                    "process_videos.generate_english_subtitle",
                    return_value=None,
                ),
                redirect_stdout(StringIO()),
            ):
                result = process_videos.process_directory(str(root))

        self.assertNotEqual(result, 0)

    def test_reports_failure_when_a_video_cannot_be_translated(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "lesson.mp4").touch()
            english = root / "lesson.en.srt"
            english.write_text(VALID_SRT, encoding="utf-8")
            with (
                patch(
                    "process_videos.check_whisper_installed",
                    return_value="whisper",
                ),
                patch(
                    "process_videos.translate_to_spanish",
                    return_value=False,
                ) as translate,
                redirect_stdout(StringIO()),
            ):
                result = process_videos.process_directory(str(root))

        self.assertNotEqual(result, 0)
        translate.assert_called_once()

    @unittest.expectedFailure
    def test_discovers_mkv_inputs(self):
        """P0.1 reproduction: the legacy scanner only considers MP4 files."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            video = root / "lesson.mkv"
            video.touch()

            with (
                patch("process_videos.check_whisper_installed", return_value="whisper"),
                patch(
                    "process_videos.generate_english_subtitle",
                    return_value=None,
                ) as generate,
                redirect_stdout(StringIO()),
            ):
                process_videos.process_directory(str(root))

        generate.assert_called_once_with(video, "whisper")


if __name__ == "__main__":
    unittest.main()
