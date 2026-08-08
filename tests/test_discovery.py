import tempfile
import unittest
from pathlib import Path

from subtitles_bridge.discovery import (
    WorkspaceDiscovery,
    discover_subtitle_paths,
    discover_video_paths,
)
from subtitles_bridge.errors import MediaInspectionError
from subtitles_bridge.integrity import subtitle_sha256
from subtitles_bridge.models import (
    ArtifactState,
    DiscoveryIssueKind,
    MediaInspection,
    MediaStream,
    StreamKind,
    SubtitleOrigin,
)
from subtitles_bridge.paths import WorkspacePaths
from subtitles_bridge.srt import SrtValidator

VALID_SRT = "1\n00:00:00,000 --> 00:00:01,000\nHello\n"


class FakeProbe:
    def __init__(self, failures=()):
        self.failures = set(failures)
        self.calls = []

    def inspect(self, source):
        self.calls.append(source)
        if source.name in self.failures:
            raise MediaInspectionError(f"Cannot inspect {source.name}")
        return MediaInspection(
            streams=(
                MediaStream(0, StreamKind.VIDEO, "h264"),
                MediaStream(
                    1,
                    StreamKind.AUDIO,
                    "aac",
                    language="eng",
                    is_default=True,
                    dispositions=frozenset({"default"}),
                ),
                MediaStream(
                    2,
                    StreamKind.SUBTITLE,
                    "subrip",
                    language="fra",
                    title="French embedded",
                ),
            ),
            format_name="matroska,webm",
            duration_seconds=12.5,
            metadata=(("title", source.stem),),
        )


class DiscoveryPathTests(unittest.TestCase):
    def test_discovers_only_root_videos_and_recognized_srt_locations(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "b.MKV").touch()
            (root / "a.mp4").touch()
            nested = root / "nested"
            nested.mkdir()
            (nested / "ignored.mkv").touch()
            (root / "a.en.srt").write_text(VALID_SRT, encoding="utf-8")
            for directory_name in (
                "sub",
                "subs",
                "Subtitles",
                "sub_es",
                "other",
                "output",
                "trash",
                "staging",
            ):
                directory = root / directory_name
                directory.mkdir()
                (directory / f"{directory_name}.srt").write_text(
                    VALID_SRT,
                    encoding="utf-8",
                )
            nested_subtitles = root / "sub" / "nested"
            nested_subtitles.mkdir()
            (nested_subtitles / "ignored.srt").write_text(
                VALID_SRT,
                encoding="utf-8",
            )
            paths = WorkspacePaths.from_directory(root)

            videos = discover_video_paths(paths)
            subtitles = discover_subtitle_paths(paths)

        self.assertEqual([path.name for path in videos], ["a.mp4", "b.MKV"])
        self.assertEqual(
            [path.relative_to(paths.root).as_posix() for path in subtitles],
            [
                "a.en.srt",
                "sub/sub.srt",
                "sub_es/sub_es.srt",
                "subs/subs.srt",
                "Subtitles/Subtitles.srt",
            ],
        )


class WorkspaceDiscoveryTests(unittest.TestCase):
    def make_workspace(self):
        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        root = Path(temporary_directory.name)
        return root, WorkspacePaths.from_directory(root)

    def write_srt(self, path, content=VALID_SRT):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def test_builds_inventory_with_embedded_and_all_associated_sidecars(self):
        root, paths = self.make_workspace()
        video = root / "lesson.mp4"
        video.touch()
        self.write_srt(root / "lesson.en.srt")
        self.write_srt(root / "lesson-commentary.srt")
        self.write_srt(root / "sub_es" / "lesson.srt")
        invalid = root / "subtitles" / "lesson.forced.srt"
        self.write_srt(invalid, "not an srt")
        probe = FakeProbe()

        result = WorkspaceDiscovery(probe, SrtValidator()).inspect(paths)
        inventory = result.inventory_for(video)

        self.assertEqual(probe.calls, [video.resolve()])
        self.assertEqual(inventory.format_name, "matroska,webm")
        self.assertEqual(inventory.duration_seconds, 12.5)
        self.assertEqual(len(inventory.video_streams), 1)
        self.assertEqual(len(inventory.audio_streams), 1)
        self.assertEqual(len(inventory.subtitles), 5)
        self.assertEqual(inventory.subtitles[0].origin, SubtitleOrigin.EMBEDDED)
        external = [
            subtitle
            for subtitle in inventory.subtitles
            if subtitle.origin is SubtitleOrigin.EXTERNAL
        ]
        self.assertEqual(
            {subtitle.language for subtitle in external},
            {"eng", "spa", "und"},
        )
        self.assertEqual(
            [subtitle.state for subtitle in external].count(ArtifactState.INVALID),
            1,
        )
        invalid_artifact = next(
            subtitle for subtitle in external if subtitle.path == invalid.resolve()
        )
        self.assertFalse(invalid_artifact.validation.is_valid)
        for subtitle in external:
            expected_hash = (
                subtitle_sha256(subtitle.path)
                if subtitle.state is ArtifactState.VALID
                else None
            )
            self.assertEqual(subtitle.content_sha256, expected_hash)
        self.assertEqual(result.issues, ())

    def test_keeps_ambiguous_and_unassociated_sidecars_outside_inventories(self):
        root, paths = self.make_workspace()
        first = root / "lesson.mp4"
        second = root / "lesson.en.mkv"
        first.touch()
        second.touch()
        ambiguous = root / "lesson.en.srt"
        orphan = root / "orphan.srt"
        self.write_srt(ambiguous)
        self.write_srt(orphan)

        result = WorkspaceDiscovery(FakeProbe(), SrtValidator()).inspect(paths)

        self.assertEqual(
            {issue.kind for issue in result.issues},
            {
                DiscoveryIssueKind.AMBIGUOUS_SUBTITLE,
                DiscoveryIssueKind.UNASSOCIATED_SUBTITLE,
            },
        )
        ambiguous_issue = next(
            issue
            for issue in result.issues
            if issue.kind is DiscoveryIssueKind.AMBIGUOUS_SUBTITLE
        )
        self.assertEqual(
            set(ambiguous_issue.candidate_videos),
            {first.resolve(), second.resolve()},
        )
        for inventory in result.inventories:
            self.assertFalse(
                any(
                    subtitle.path in {ambiguous, orphan}
                    for subtitle in inventory.subtitles
                )
            )

    def test_keeps_multiple_sidecars_with_the_same_language(self):
        root, paths = self.make_workspace()
        video = root / "lesson.mp4"
        video.touch()
        self.write_srt(root / "lesson.en.srt")
        self.write_srt(root / "sub_en" / "lesson.srt")

        result = WorkspaceDiscovery(FakeProbe(), SrtValidator()).inspect(paths)
        english = [
            subtitle
            for subtitle in result.inventories[0].subtitles
            if subtitle.origin is SubtitleOrigin.EXTERNAL and subtitle.language == "eng"
        ]

        self.assertEqual(len(english), 2)

    def test_reports_probe_failure_and_continues_other_videos(self):
        root, paths = self.make_workspace()
        good = root / "good.mp4"
        broken = root / "broken.mkv"
        good.touch()
        broken.touch()

        result = WorkspaceDiscovery(
            FakeProbe(failures={"broken.mkv"}),
            SrtValidator(),
        ).inspect(paths)

        self.assertEqual(
            [inventory.source for inventory in result.inventories],
            [good.resolve()],
        )
        self.assertEqual(len(result.issues), 1)
        self.assertEqual(result.issues[0].kind, DiscoveryIssueKind.INSPECTION_FAILED)
        self.assertEqual(result.issues[0].path, broken.resolve())

    def test_records_existing_destinations_without_creating_managed_directories(self):
        root, paths = self.make_workspace()
        video = root / "lesson.mkv"
        video.touch()

        initial_entries = {path.relative_to(root) for path in root.rglob("*")}
        result = WorkspaceDiscovery(FakeProbe(), SrtValidator()).inspect(paths)
        self.assertIsNone(result.inventory_for(video).existing_output)
        self.assertIsNone(result.inventory_for(video).existing_trash)
        self.assertEqual(
            {path.relative_to(root) for path in root.rglob("*")},
            initial_entries,
        )

        output = root / "output" / "lesson.subtitled.mkv"
        output.parent.mkdir()
        output.touch()
        result = WorkspaceDiscovery(FakeProbe(), SrtValidator()).inspect(paths)

        self.assertEqual(result.inventory_for(video).existing_output, output.resolve())

        trash = root / "trash" / "lesson"
        trash.mkdir(parents=True)
        result = WorkspaceDiscovery(FakeProbe(), SrtValidator()).inspect(paths)

        self.assertEqual(result.inventory_for(video).existing_trash, trash.resolve())

    def test_numeric_suffix_is_not_guessed_as_metadata(self):
        root, paths = self.make_workspace()
        video = root / "lesson.mp4"
        sidecar = root / "lesson-01.srt"
        video.touch()
        self.write_srt(sidecar)

        result = WorkspaceDiscovery(FakeProbe(), SrtValidator()).inspect(paths)

        self.assertEqual(
            result.issues[0].kind, DiscoveryIssueKind.UNASSOCIATED_SUBTITLE
        )
        self.assertFalse(
            any(
                subtitle.path == sidecar for subtitle in result.inventories[0].subtitles
            )
        )

    def test_marks_conflicting_language_metadata_as_ambiguous(self):
        root, paths = self.make_workspace()
        video = root / "lesson.mp4"
        sidecar = root / "sub_es" / "lesson.en.srt"
        video.touch()
        self.write_srt(sidecar)

        result = WorkspaceDiscovery(FakeProbe(), SrtValidator()).inspect(paths)
        artifact = next(
            subtitle
            for subtitle in result.inventories[0].subtitles
            if subtitle.path == sidecar.resolve()
        )

        self.assertEqual(artifact.state, ArtifactState.AMBIGUOUS)
        self.assertEqual(artifact.language, "und")
        self.assertIn("Conflicting", artifact.message)


if __name__ == "__main__":
    unittest.main()
