from pathlib import Path
import unittest

from subtitles_bridge.languages import (
    infer_subtitle_metadata,
    is_subtitle_metadata_token,
    normalize_language_code,
    normalize_trusted_language,
)


class LanguageNormalizationTests(unittest.TestCase):
    def test_normalizes_known_aliases_and_three_letter_codes(self):
        self.assertEqual(normalize_language_code("en"), "eng")
        self.assertEqual(normalize_language_code("Español"), "spa")
        self.assertEqual(normalize_language_code("rus"), "rus")

    def test_uses_und_for_missing_or_untrusted_two_letter_code(self):
        self.assertEqual(normalize_language_code(None), "und")
        self.assertEqual(normalize_language_code(""), "und")
        self.assertEqual(normalize_language_code("xx"), "und")

    def test_preserves_trusted_detected_two_letter_language(self):
        self.assertEqual(normalize_trusted_language("ru"), "ru")
        self.assertEqual(normalize_trusted_language("en"), "eng")

    def test_recognizes_language_and_subtitle_qualifier_tokens(self):
        self.assertTrue(is_subtitle_metadata_token("english"))
        self.assertTrue(is_subtitle_metadata_token("rus"))
        self.assertTrue(is_subtitle_metadata_token("forced"))
        self.assertFalse(is_subtitle_metadata_token("01"))


class SubtitleMetadataInferenceTests(unittest.TestCase):
    def test_infers_language_and_qualifier_from_filename(self):
        metadata = infer_subtitle_metadata(
            Path("lesson.en.forced.srt"),
            "lesson",
        )

        self.assertEqual(
            (metadata.language, metadata.title, metadata.conflict),
            ("eng", "English (Forced)", None),
        )

    def test_uses_recognized_sub_language_directory(self):
        metadata = infer_subtitle_metadata(
            Path("/media/sub_por/lesson.srt"),
            "lesson",
            "sub_por",
        )

        self.assertEqual((metadata.language, metadata.title), ("por", "Portuguese"))

    def test_does_not_infer_language_from_workspace_name(self):
        metadata = infer_subtitle_metadata(
            Path("/media/sub_en/lesson.srt"),
            "lesson",
            subtitle_directory=None,
        )

        self.assertEqual(metadata.language, "und")
        self.assertEqual(metadata.title, "lesson")

    def test_preserves_unknown_three_letter_language_code(self):
        metadata = infer_subtitle_metadata(
            Path("lesson.rus.srt"),
            "lesson",
        )

        self.assertEqual((metadata.language, metadata.title), ("rus", "RUS"))

    def test_reports_conflicting_folder_and_filename_languages(self):
        metadata = infer_subtitle_metadata(
            Path("/media/sub_es/lesson.en.srt"),
            "lesson",
            "sub_es",
        )

        self.assertEqual(metadata.language, "und")
        self.assertIn("eng", metadata.conflict)
        self.assertIn("spa", metadata.conflict)


if __name__ == "__main__":
    unittest.main()
