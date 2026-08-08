import argparse
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import local_translate_srt


class PrefixTranslator:
    def translate(self, text):
        return f"ES<{text}>"


class TranslateSrtTests(unittest.TestCase):
    def setUp(self):
        self.original_translator = local_translate_srt.TranslatorImpl
        local_translate_srt.TranslatorImpl = PrefixTranslator()

    def tearDown(self):
        local_translate_srt.TranslatorImpl = self.original_translator

    def test_translates_block_when_file_has_no_trailing_newline(self):
        content = "1\n00:00:00,000 --> 00:00:01,000\nHello"

        with patch("local_translate_srt.time.sleep"):
            result = local_translate_srt.translate_srt(content, sleep_duration=0)

        self.assertEqual(
            result,
            "1\n00:00:00,000 --> 00:00:01,000\nES<Hello>\n\n",
        )

    @unittest.expectedFailure
    def test_preserves_multiline_text_inside_a_matched_block(self):
        """P0.1 reproduction: the regex does not enable dot-all matching."""
        content = "1\n00:00:00,000 --> 00:00:01,000\nFirst line\n<i>Second line</i>"

        with patch("local_translate_srt.time.sleep"):
            result = local_translate_srt.translate_srt(content, sleep_duration=0)

        self.assertIn("ES<First line>\nES<<i>Second line</i>>", result)

    @unittest.expectedFailure
    def test_translates_final_block_with_single_trailing_newline(self):
        """P0.1 reproduction: a common final block is silently left untranslated."""
        content = "1\n00:00:00,000 --> 00:00:01,000\nHello\n"

        with patch("local_translate_srt.time.sleep"):
            result = local_translate_srt.translate_srt(content, sleep_duration=0)

        self.assertIn("ES<Hello>", result)

    @unittest.expectedFailure
    def test_translates_all_blocks_without_duplicating_separators(self):
        """P0.1 reproduction: matched blocks currently add extra blank lines."""
        content = (
            "1\n00:00:00,000 --> 00:00:01,000\nHello\n\n"
            "2\n00:00:02,000 --> 00:00:03,000\nWorld\n"
        )

        with patch("local_translate_srt.time.sleep"):
            result = local_translate_srt.translate_srt(content, sleep_duration=0)

        self.assertIn("ES<Hello>", result)
        self.assertIn("ES<World>", result)
        self.assertNotIn("\n\n\n", result)

    @unittest.expectedFailure
    def test_accepts_crlf_content(self):
        content = "1\r\n00:00:00,000 --> 00:00:01,000\r\nHello\r\n"

        with patch("local_translate_srt.time.sleep"):
            result = local_translate_srt.translate_srt(content, sleep_duration=0)

        self.assertIn("ES<Hello>", result)


class TranslatorMainFailureTests(unittest.TestCase):
    def run_failed_translation(self):
        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        root = Path(temporary_directory.name)
        input_directory = root / "input"
        output_directory = root / "output"
        input_directory.mkdir()
        (input_directory / "lesson.srt").write_text(
            "1\n00:00:00,000 --> 00:00:01,000\nHello",
            encoding="utf-8",
        )
        args = argparse.Namespace(
            input_dir=str(input_directory),
            output_dir=str(output_directory),
            src="en",
            tgt="es",
            backend="google",
            sleep=0.25,
            libre_url=None,
            libre_api_key=None,
            deepl_api_key=None,
            overwrite=False,
        )
        stdout = StringIO()
        stderr = StringIO()

        with (
            patch("local_translate_srt.parse_args", return_value=args),
            patch("local_translate_srt.load_translator"),
            patch(
                "local_translate_srt.translate_srt",
                side_effect=RuntimeError("backend unavailable"),
            ),
            redirect_stdout(stdout),
            redirect_stderr(stderr),
        ):
            status = local_translate_srt.main()

        return status, stdout.getvalue(), stderr.getvalue(), output_directory

    @unittest.expectedFailure
    def test_returns_nonzero_when_any_translation_fails(self):
        """P0.1 reproduction: a failed batch currently returns status zero."""
        status, _, _, _ = self.run_failed_translation()

        self.assertNotEqual(status, 0)

    @unittest.expectedFailure
    def test_interpolates_exception_and_output_directory(self):
        """P0.1 reproduction: two legacy messages print literal braces."""
        _, stdout, stderr, output_directory = self.run_failed_translation()

        self.assertIn("backend unavailable", stderr)
        self.assertIn(str(output_directory), stdout)
        self.assertNotIn("{e}", stderr)
        self.assertNotIn("{out_dir}", stdout)

    @unittest.expectedFailure
    def test_forwards_configured_sleep_to_translation(self):
        """P0.1 reproduction: --sleep is parsed but ignored by main()."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            input_directory = root / "input"
            output_directory = root / "output"
            input_directory.mkdir()
            source = input_directory / "lesson.srt"
            source.write_text("subtitle", encoding="utf-8")
            args = argparse.Namespace(
                input_dir=str(input_directory),
                output_dir=str(output_directory),
                src="en",
                tgt="es",
                backend="google",
                sleep=0.05,
                libre_url=None,
                libre_api_key=None,
                deepl_api_key=None,
                overwrite=False,
            )

            with (
                patch("local_translate_srt.parse_args", return_value=args),
                patch("local_translate_srt.load_translator"),
                patch(
                    "local_translate_srt.translate_srt",
                    return_value="translated",
                ) as translate,
                redirect_stdout(StringIO()),
            ):
                local_translate_srt.main()

        translate.assert_called_once_with("subtitle", sleep_duration=0.05)


if __name__ == "__main__":
    unittest.main()
