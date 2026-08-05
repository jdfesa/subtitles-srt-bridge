from pathlib import Path
import tempfile
import unittest

from subtitles_bridge.srt import SrtValidator


class SrtValidatorTests(unittest.TestCase):
    def validate_bytes(self, data: bytes):
        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        path = Path(temporary_directory.name) / "subtitle.srt"
        path.write_bytes(data)
        return SrtValidator().validate(path)

    def test_accepts_lf_crlf_multiline_tags_and_no_final_newline(self):
        variants = (
            b"1\n00:00:00,000 --> 00:00:01,000\nHello",
            b"1\r\n00:00:00,000 --> 00:00:01,000\r\nHello\r\n",
            (
                b"1\n00:00:00,000 --> 00:00:01,000\n"
                b"First line\n<i>Second line</i>\n"
            ),
        )

        for data in variants:
            with self.subTest(data=data):
                result = self.validate_bytes(data)
                self.assertTrue(result.is_valid)
                self.assertEqual(result.cue_count, 1)

    def test_accepts_multiple_blocks_and_utf8_bom(self):
        data = (
            b"\xef\xbb\xbf1\n00:00:00,000 --> 00:00:01,000\nHello\n\n"
            b"2\n00:00:02,000 --> 00:00:03,000\nWorld\n"
        )

        result = self.validate_bytes(data)

        self.assertTrue(result.is_valid)
        self.assertEqual(result.cue_count, 2)
        self.assertEqual(result.encoding, "utf-8-sig")

    def test_accepts_cp1252(self):
        data = "1\n00:00:00,000 --> 00:00:01,000\nOlé €".encode("cp1252")

        result = self.validate_bytes(data)

        self.assertTrue(result.is_valid)
        self.assertEqual(result.encoding, "cp1252")

    def test_accepts_utf16_with_bom(self):
        data = "1\n00:00:00,000 --> 00:00:01,000\nHello".encode("utf-16")

        result = self.validate_bytes(data)

        self.assertTrue(result.is_valid)
        self.assertEqual(result.encoding, "utf-16")

    def test_rejects_empty_and_whitespace_only_files(self):
        for data in (b"", b"\n \n"):
            with self.subTest(data=data):
                result = self.validate_bytes(data)
                self.assertFalse(result.is_valid)
                self.assertEqual(result.cue_count, 0)
                self.assertTrue(result.error)

    def test_rejects_non_numeric_index(self):
        result = self.validate_bytes(
            b"one\n00:00:00,000 --> 00:00:01,000\nHello"
        )

        self.assertFalse(result.is_valid)
        self.assertIn("non-numeric index", result.error)

    def test_rejects_invalid_or_reversed_timestamp(self):
        variants = (
            (b"1\nnot a timestamp\nHello", "invalid timestamp"),
            (b"1\n00:00:61,000 --> 00:01:02,000\nHello", "below 60"),
            (b"1\n00:00:02,000 --> 00:00:01,000\nHello", "ends before"),
        )

        for data, expected_error in variants:
            with self.subTest(data=data):
                result = self.validate_bytes(data)
                self.assertFalse(result.is_valid)
                self.assertIn(expected_error, result.error)

    def test_rejects_cue_without_text(self):
        result = self.validate_bytes(
            b"1\n00:00:00,000 --> 00:00:01,000\n   "
        )

        self.assertFalse(result.is_valid)
        self.assertIn("no subtitle text", result.error)

    def test_reports_unreadable_path_without_raising(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            result = SrtValidator().validate(Path(temp_dir) / "missing.srt")

        self.assertFalse(result.is_valid)
        self.assertIn("Cannot read", result.error)


if __name__ == "__main__":
    unittest.main()
