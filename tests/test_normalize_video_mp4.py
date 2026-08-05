import argparse
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from tools.normalize_video_mp4 import normalize_video_mp4 as normalizer


class SubtitleMetadataTests(unittest.TestCase):
    def test_tokenises_accents_and_punctuation(self):
        path = Path("Lección.01.Español-forzado.srt")

        self.assertEqual(
            normalizer.tokenise_name(path),
            ["leccion", "01", "espanol", "forzado"],
        )

    def test_guesses_known_language_from_filename(self):
        language, title = normalizer.guess_subtitle_language(
            Path("lesson.portuguese.srt")
        )

        self.assertEqual((language, title), ("por", "Portuguese"))

    def test_keeps_unknown_language_with_descriptive_title(self):
        path = Path("lesson.commentary.srt")

        language, title = normalizer.guess_subtitle_language(path)

        self.assertEqual(language, "und")
        self.assertEqual(title, path.stem)

    def test_detects_cp1252_subtitle(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            subtitle = Path(temp_dir) / "lesson.es.srt"
            subtitle.write_bytes("Olé €".encode("cp1252"))

            encoding = normalizer.detect_subtitle_charenc(subtitle)

        self.assertEqual(encoding, "CP1252")

    def test_builds_tracks_with_per_track_overrides(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            english = root / "lesson.en.srt"
            unknown = root / "lesson.commentary.srt"
            english.write_text("hello", encoding="utf-8")
            unknown.write_text("notes", encoding="utf-8")

            tracks = normalizer.build_subtitle_tracks(
                [english, unknown],
                languages=None,
                titles=["Primary", "Director commentary"],
            )

        self.assertEqual(
            [(track.language, track.title, track.charenc) for track in tracks],
            [
                ("eng", "Primary", None),
                ("und", "Director commentary", None),
            ],
        )


class ProbeTests(unittest.TestCase):
    def test_probe_media_uses_json_without_running_real_ffprobe(self):
        payload = {"streams": [{"codec_type": "video", "codec_name": "h264"}]}
        completed = subprocess.CompletedProcess(
            ["ffprobe"],
            0,
            stdout=json.dumps(payload),
            stderr="",
        )

        with patch.object(normalizer.subprocess, "run", return_value=completed) as run:
            result = normalizer.probe_media("ffprobe", Path("lesson.mkv"))

        self.assertEqual(result, payload)
        run.assert_called_once_with(
            [
                "ffprobe",
                "-v",
                "error",
                "-print_format",
                "json",
                "-show_streams",
                "lesson.mkv",
            ],
            capture_output=True,
            text=True,
            check=False,
        )

    def test_probe_media_raises_actionable_error(self):
        completed = subprocess.CompletedProcess(
            ["ffprobe"],
            1,
            stdout="",
            stderr="invalid media",
        )

        with (
            patch.object(normalizer.subprocess, "run", return_value=completed),
            self.assertRaisesRegex(normalizer.ScriptError, "invalid media"),
        ):
            normalizer.probe_media("ffprobe", Path("broken.mkv"))


class CodecPolicyTests(unittest.TestCase):
    def make_args(self, **overrides):
        values = {
            "video_codec": "auto",
            "audio_codec": "auto",
            "preset": "medium",
            "crf": 20,
            "audio_bitrate": None,
        }
        values.update(overrides)
        return argparse.Namespace(**values)

    def test_explicit_copy_keeps_video_and_audio_codecs(self):
        probe = {
            "streams": [
                {"codec_type": "video", "codec_name": "hevc", "pix_fmt": "yuv420p"},
                {"codec_type": "audio", "codec_name": "ac3", "channels": 6},
            ]
        }
        args = self.make_args(video_codec="copy", audio_codec="copy")

        video_plan = normalizer.build_video_codec_plan(
            args,
            probe,
            Path("lesson.mkv"),
        )
        audio_plan = normalizer.build_audio_codec_plan(
            args,
            probe,
            Path("lesson.mkv"),
        )

        self.assertEqual(video_plan.args, ["-c:v", "copy"])
        self.assertEqual(audio_plan.args, ["-c:a", "copy"])


class FfmpegCommandTests(unittest.TestCase):
    def test_characterizes_selectable_subtitle_command(self):
        video = Path("lesson.mkv")
        output = Path("lesson.normalized.mp4")
        subtitle = normalizer.SubtitleTrack(
            path=Path("lesson.en.srt"),
            language="eng",
            title="English",
            charenc=None,
        )

        command = normalizer.build_ffmpeg_command(
            ffmpeg="ffmpeg",
            video_path=video,
            output_path=output,
            subtitles=[subtitle],
            video_plan=normalizer.CodecPlan(["-c:v", "copy"], "copy"),
            audio_plan=normalizer.CodecPlan(["-c:a", "copy"], "copy"),
            embedded_subtitles=[{"codec_type": "subtitle"}],
            default_audio=None,
            default_subtitle=None,
            overwrite=False,
        )

        self.assertEqual(
            command,
            [
                "ffmpeg",
                "-hide_banner",
                "-n",
                "-i",
                str(video),
                "-i",
                str(subtitle.path),
                "-map",
                "0:v:0",
                "-map",
                "0:a?",
                "-map",
                "0:s?",
                "-map",
                "1:0",
                "-c:v",
                "copy",
                "-c:a",
                "copy",
                "-c:s",
                "mov_text",
                "-map_metadata",
                "0",
                "-map_chapters",
                "0",
                "-disposition:s",
                "0",
                "-metadata:s:s:1",
                "language=eng",
                "-metadata:s:s:1",
                "title=English",
                "-metadata:s:s:1",
                "handler_name=English",
                "-disposition:s:1",
                "0",
                "-movflags",
                "+faststart",
                str(output),
            ],
        )

    def test_omitted_default_audio_keeps_existing_dispositions(self):
        command = normalizer.build_ffmpeg_command(
            ffmpeg="ffmpeg",
            video_path=Path("lesson.mp4"),
            output_path=Path("lesson.normalized.mp4"),
            subtitles=[],
            video_plan=normalizer.CodecPlan(["-c:v", "copy"], "copy"),
            audio_plan=normalizer.CodecPlan(["-c:a", "copy"], "copy"),
            embedded_subtitles=[],
            default_audio=None,
            default_subtitle=None,
            overwrite=False,
        )

        self.assertNotIn("-disposition:a", command)


if __name__ == "__main__":
    unittest.main()
