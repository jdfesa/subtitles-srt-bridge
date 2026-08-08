import json
import subprocess
import unittest
from pathlib import Path

from subtitles_bridge.adapters.ffprobe import FFprobeMediaProbe
from subtitles_bridge.errors import MediaInspectionError
from subtitles_bridge.models import StreamKind


def completed(payload, returncode=0, stderr=""):
    stdout = payload if isinstance(payload, str) else json.dumps(payload)
    return subprocess.CompletedProcess(["ffprobe"], returncode, stdout, stderr)


class FFprobeMediaProbeTests(unittest.TestCase):
    def test_maps_streams_format_chapters_metadata_and_dispositions(self):
        payload = {
            "streams": [
                {
                    "index": 0,
                    "codec_type": "video",
                    "codec_name": "h264",
                    "width": 1920,
                    "height": 1080,
                    "tags": {"title": "Main video"},
                    "disposition": {"default": 1},
                },
                {
                    "index": 1,
                    "codec_type": "audio",
                    "codec_name": "aac",
                    "channels": 2,
                    "tags": {"language": "en", "title": "Original"},
                    "disposition": {"default": 1, "forced": 0},
                },
                {
                    "index": 2,
                    "codec_type": "subtitle",
                    "codec_name": "subrip",
                    "tags": {"language": "spa", "title": "Spanish"},
                    "disposition": {"default": 0, "forced": 1},
                },
            ],
            "chapters": [
                {
                    "id": 0,
                    "start_time": "0.000000",
                    "end_time": "60.000000",
                    "tags": {"title": "Intro"},
                }
            ],
            "format": {
                "format_name": "matroska,webm",
                "duration": "60.250000",
                "tags": {"title": "Lesson"},
            },
        }
        calls = []

        def runner(command, **kwargs):
            calls.append((command, kwargs))
            return completed(payload)

        inspection = FFprobeMediaProbe("/usr/bin/ffprobe", runner).inspect(
            Path("lesson.mkv")
        )

        self.assertEqual(
            calls[0][0],
            [
                "/usr/bin/ffprobe",
                "-v",
                "error",
                "-print_format",
                "json",
                "-show_format",
                "-show_streams",
                "-show_chapters",
                "lesson.mkv",
            ],
        )
        self.assertEqual(
            calls[0][1],
            {"capture_output": True, "text": True, "check": False},
        )
        self.assertEqual(inspection.format_name, "matroska,webm")
        self.assertEqual(inspection.duration_seconds, 60.25)
        self.assertEqual(inspection.metadata, (("title", "Lesson"),))
        self.assertEqual(inspection.chapters[0].title, "Intro")
        self.assertEqual(inspection.streams[1].language, "eng")
        self.assertTrue(inspection.streams[1].is_default)
        self.assertEqual(inspection.streams[2].dispositions, frozenset({"forced"}))
        self.assertIn(("channels", "2"), inspection.streams[1].properties)

    def test_rejects_process_error_invalid_json_and_missing_video(self):
        cases = (
            (completed("", 1, "broken media"), "broken media"),
            (completed("not json"), "invalid JSON"),
            (
                completed(
                    {
                        "streams": [
                            {"index": 0, "codec_type": "audio", "codec_name": "aac"}
                        ]
                    }
                ),
                "no video stream",
            ),
        )

        for result, message in cases:
            with self.subTest(message=message):
                probe = FFprobeMediaProbe(
                    runner=lambda *args, result=result, **kwargs: result
                )
                with self.assertRaisesRegex(MediaInspectionError, message):
                    probe.inspect(Path("lesson.mkv"))

    def test_wraps_missing_executable(self):
        def runner(*args, **kwargs):
            raise FileNotFoundError("ffprobe not found")

        with self.assertRaisesRegex(MediaInspectionError, "Cannot execute"):
            FFprobeMediaProbe(runner=runner).inspect(Path("lesson.mkv"))

    def test_preserves_unknown_stream_kind(self):
        payload = {
            "streams": [
                {"index": 0, "codec_type": "video", "codec_name": "h264"},
                {"index": 1, "codec_type": "mystery", "codec_name": "bin_data"},
            ]
        }

        inspection = FFprobeMediaProbe(
            runner=lambda *args, **kwargs: completed(payload)
        ).inspect(Path("lesson.mkv"))

        self.assertEqual(inspection.streams[1].kind, StreamKind.UNKNOWN)


if __name__ == "__main__":
    unittest.main()
