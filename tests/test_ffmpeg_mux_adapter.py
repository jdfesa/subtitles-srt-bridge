from pathlib import Path
import subprocess
import tempfile
import unittest

from subtitles_bridge.adapters.ffmpeg_mux import (
    FFmpegMediaMuxer,
    build_ffmpeg_mux_command,
)
from subtitles_bridge.errors import MuxingCollisionError, MuxingError
from subtitles_bridge.models import (
    ArtifactState,
    MediaStream,
    StreamKind,
    SubtitleArtifact,
    SubtitleOrigin,
    SubtitleValidation,
    VideoInventory,
)


class FFmpegMuxCommandTests(unittest.TestCase):
    def make_artifacts(self):
        source = Path("/media/lesson.mp4")
        english = Path("/media/lesson.en.srt")
        spanish = Path("/media/lesson.es.srt")
        inventory = VideoInventory(
            source,
            (
                MediaStream(0, StreamKind.VIDEO, "h264"),
                MediaStream(1, StreamKind.AUDIO, "aac", is_default=True),
                MediaStream(2, StreamKind.SUBTITLE, "subrip"),
                MediaStream(3, StreamKind.ATTACHMENT, "ttf"),
                MediaStream(4, StreamKind.UNKNOWN, "bin_data"),
            ),
        )
        embedded = SubtitleArtifact(
            SubtitleOrigin.EMBEDDED,
            ArtifactState.VALID,
            stream_index=2,
        )
        external = SubtitleArtifact(
            SubtitleOrigin.EXTERNAL,
            ArtifactState.VALID,
            language="eng",
            title="English",
            path=english,
            validation=SubtitleValidation(True, 1, "utf-8"),
        )
        generated = SubtitleArtifact(
            SubtitleOrigin.GENERATED,
            ArtifactState.VALID,
            language="spa",
            title="Spanish generated",
            path=spanish,
            validation=SubtitleValidation(True, 1, "cp1252"),
        )
        return inventory, embedded, external, generated

    def test_maps_every_source_stream_and_each_sidecar_with_copy_only(self):
        inventory, embedded, external, generated = self.make_artifacts()
        destination = Path("/media/staging/lesson.working.mkv")

        command = build_ffmpeg_mux_command(
            inventory,
            (embedded, external, generated),
            destination,
        )

        self.assertEqual(
            command,
            [
                "ffmpeg",
                "-v",
                "error",
                "-nostdin",
                "-n",
                "-copy_unknown",
                "-i",
                "/media/lesson.mp4",
                "-i",
                "/media/lesson.en.srt",
                "-sub_charenc",
                "CP1252",
                "-i",
                "/media/lesson.es.srt",
                "-map",
                "0",
                "-map",
                "1:0",
                "-map",
                "2:0",
                "-map_metadata",
                "0",
                "-map_chapters",
                "0",
                "-c",
                "copy",
                "-metadata:s:s:1",
                "language=eng",
                "-metadata:s:s:1",
                "title=English",
                "-metadata:s:s:2",
                "language=spa",
                "-metadata:s:s:2",
                "title=Spanish generated",
                "-disposition:s:0",
                "-default",
                "-disposition:s:1",
                "-default",
                "-disposition:s:2",
                "-default",
                "-default_mode",
                "passthrough",
                "-f",
                "matroska",
                str(destination),
            ],
        )
        self.assertNotIn("-c:v", command)
        self.assertNotIn("-c:a", command)

    def test_preserves_embedded_subtitle_without_adding_an_input(self):
        inventory, embedded, _, _ = self.make_artifacts()

        command = build_ffmpeg_mux_command(
            inventory,
            (embedded,),
            Path("/media/staging/lesson.working.mkv"),
        )

        self.assertEqual(command.count("-i"), 1)
        self.assertEqual(command.count("-map"), 1)
        self.assertIn("-disposition:s:0", command)

    def test_passes_utf16_and_cp1252_encodings_without_rewriting_sidecars(self):
        inventory, _, external, generated = self.make_artifacts()
        utf16 = SubtitleArtifact(
            SubtitleOrigin.EXTERNAL,
            ArtifactState.VALID,
            language="deu",
            path=Path("/media/lesson.de.srt"),
            validation=SubtitleValidation(True, 1, "utf-16"),
        )

        command = build_ffmpeg_mux_command(
            inventory,
            (external, generated, utf16),
            Path("/media/staging/lesson.working.mkv"),
        )

        self.assertEqual(command.count("-sub_charenc"), 2)
        self.assertIn("CP1252", command)
        self.assertIn("UTF-16", command)

    def test_rejects_unvalidated_duplicate_or_unowned_subtitles(self):
        inventory, _, external, _ = self.make_artifacts()
        unvalidated = SubtitleArtifact(
            SubtitleOrigin.EXTERNAL,
            ArtifactState.VALID,
            path=Path("/media/unvalidated.srt"),
        )
        unowned_embedded = SubtitleArtifact(
            SubtitleOrigin.EMBEDDED,
            ArtifactState.VALID,
            stream_index=99,
        )
        destination = Path("/media/staging/lesson.working.mkv")

        cases = (
            ((unvalidated,), "not validated"),
            ((external, external), "duplicated"),
            ((unowned_embedded,), "does not belong"),
        )
        for subtitles, message in cases:
            with self.subTest(message=message):
                with self.assertRaisesRegex(MuxingError, message):
                    build_ffmpeg_mux_command(inventory, subtitles, destination)


class FFmpegMediaMuxerTests(unittest.TestCase):
    def make_workspace(self):
        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        root = Path(temporary_directory.name)
        source = root / "lesson.mp4"
        source.write_bytes(b"source")
        subtitle_path = root / "lesson.en.srt"
        subtitle_path.write_bytes(b"subtitle")
        inventory = VideoInventory(
            source.resolve(),
            (
                MediaStream(0, StreamKind.VIDEO, "h264"),
                MediaStream(1, StreamKind.AUDIO, "aac"),
            ),
        )
        subtitle = SubtitleArtifact(
            SubtitleOrigin.EXTERNAL,
            ArtifactState.VALID,
            language="eng",
            title="English",
            path=subtitle_path.resolve(),
            validation=SubtitleValidation(True, 1, "utf-8"),
        )
        staging = root / "staging"
        staging.mkdir()
        destination = staging / "lesson.subtitled.mkv"
        working = staging / ".lesson.working.mkv"
        return source, inventory, subtitle_path, subtitle, destination, working

    def make_muxer(self, runner, working):
        return FFmpegMediaMuxer(
            runner=runner,
            temporary_output_factory=lambda destination: working,
        )

    def test_reserves_destination_and_finalizes_complete_working_output(self):
        source, inventory, sidecar, subtitle, destination, working = (
            self.make_workspace()
        )
        source_content = source.read_bytes()
        sidecar_content = sidecar.read_bytes()
        calls = []

        def runner(command, **options):
            calls.append((command, options, destination.exists()))
            Path(command[-1]).write_bytes(b"complete-mkv")
            return subprocess.CompletedProcess(command, 0, "", "")

        self.make_muxer(runner, working).mux(
            inventory,
            (subtitle,),
            destination,
        )

        self.assertEqual(destination.read_bytes(), b"complete-mkv")
        self.assertFalse(working.exists())
        self.assertTrue(calls[0][2])
        self.assertEqual(
            calls[0][1],
            {"capture_output": True, "text": True, "check": False},
        )
        self.assertEqual(source.read_bytes(), source_content)
        self.assertEqual(sidecar.read_bytes(), sidecar_content)

    def test_cleans_reserved_and_partial_outputs_when_ffmpeg_fails(self):
        source, inventory, sidecar, subtitle, destination, working = (
            self.make_workspace()
        )
        source_content = source.read_bytes()
        sidecar_content = sidecar.read_bytes()

        def runner(command, **options):
            Path(command[-1]).write_bytes(b"partial")
            return subprocess.CompletedProcess(
                command,
                1,
                "",
                "Unsupported stream codec",
            )

        with self.assertRaisesRegex(MuxingError, "Unsupported stream codec"):
            self.make_muxer(runner, working).mux(
                inventory,
                (subtitle,),
                destination,
            )

        self.assertFalse(destination.exists())
        self.assertFalse(working.exists())
        self.assertEqual(source.read_bytes(), source_content)
        self.assertEqual(sidecar.read_bytes(), sidecar_content)

    def test_cleans_reservation_when_ffmpeg_cannot_launch(self):
        _, inventory, _, subtitle, destination, working = self.make_workspace()

        def runner(command, **options):
            raise FileNotFoundError("ffmpeg missing")

        with self.assertRaisesRegex(MuxingError, "ffmpeg missing"):
            self.make_muxer(runner, working).mux(
                inventory,
                (subtitle,),
                destination,
            )

        self.assertFalse(destination.exists())
        self.assertFalse(working.exists())

    def test_rejects_collisions_and_missing_sidecars_before_execution(self):
        _, inventory, sidecar, subtitle, destination, working = self.make_workspace()
        calls = []
        muxer = self.make_muxer(
            lambda *args, **kwargs: calls.append(args),
            working,
        )
        destination.write_bytes(b"existing")

        with self.assertRaisesRegex(MuxingCollisionError, "already exists"):
            muxer.mux(inventory, (subtitle,), destination)
        self.assertEqual(destination.read_bytes(), b"existing")

        destination.unlink()
        sidecar.unlink()
        with self.assertRaisesRegex(MuxingError, "missing or empty"):
            muxer.mux(inventory, (subtitle,), destination)

        self.assertEqual(calls, [])

    def test_rejects_success_without_a_nonempty_output_and_cleans_reservation(self):
        _, inventory, _, subtitle, destination, working = self.make_workspace()
        command_seen = []

        def runner(command, **options):
            command_seen.append(command)
            return subprocess.CompletedProcess(command, 0, "", "")

        with self.assertRaisesRegex(MuxingError, "usable staged MKV"):
            self.make_muxer(runner, working).mux(
                inventory,
                (subtitle,),
                destination,
            )

        self.assertEqual(len(command_seen), 1)
        self.assertFalse(destination.exists())
        self.assertFalse(working.exists())


if __name__ == "__main__":
    unittest.main()
