import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from subtitles_bridge.batch_planner import BatchPlanner
from subtitles_bridge.errors import VerificationError
from subtitles_bridge.integrity import subtitle_sha256
from subtitles_bridge.models import (
    ArtifactState,
    DiscoveryIssue,
    DiscoveryIssueKind,
    DiscoveryResult,
    MediaChapter,
    MediaInspection,
    MediaStream,
    PlanningChoice,
    StreamKind,
    SubtitleArtifact,
    SubtitleOrigin,
    SubtitleValidation,
    VerifiedOutput,
    VideoInventory,
)
from subtitles_bridge.paths import WorkspacePaths
from subtitles_bridge.verification import (
    OutputContractVerifier,
    VerificationStage,
)


class FakeProbe:
    def __init__(self, inspection, hook=None):
        self.inspection = inspection
        self.hook = hook
        self.calls = []

    def inspect(self, source):
        self.calls.append(source)
        if self.hook is not None:
            self.hook(source)
        return self.inspection


class OutputContractVerifierTests(unittest.TestCase):
    def make_case(self):
        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        root = Path(temporary_directory.name)
        source = root / "lesson.mp4"
        source.write_bytes(b"source")
        sidecar_path = root / "lesson.en.srt"
        sidecar_path.write_text(
            "1\n00:00:00,000 --> 00:00:01,000\nHello\n",
            encoding="utf-8",
        )
        sidecar_hash = subtitle_sha256(sidecar_path)
        staged = root / "staging" / "lesson.subtitled.mkv"
        staged.parent.mkdir()
        staged.write_bytes(b"verified-mkv")

        source_streams = (
            MediaStream(
                0,
                StreamKind.VIDEO,
                "h264",
                metadata=(
                    ("creation_time", "2026-01-01T00:00:00Z"),
                    ("handler_name", "VideoHandler"),
                ),
            ),
            MediaStream(
                1,
                StreamKind.AUDIO,
                "aac",
                language="eng",
                title="English Audio",
                is_default=True,
                dispositions=frozenset({"default", "dub"}),
                metadata=(
                    ("comment", "Primary"),
                    ("handler_name", "SoundHandler"),
                    ("language", "en"),
                    ("title", "English Audio"),
                ),
            ),
            MediaStream(
                2,
                StreamKind.SUBTITLE,
                "subrip",
                language="spa",
                title="Embedded Spanish",
                is_default=True,
                dispositions=frozenset({"default", "forced"}),
                metadata=(
                    ("comment", "Embedded"),
                    ("language", "spa"),
                    ("title", "Embedded Spanish"),
                ),
            ),
        )
        embedded = SubtitleArtifact(
            SubtitleOrigin.EMBEDDED,
            ArtifactState.VALID,
            language="spa",
            title="Embedded Spanish",
            stream_index=2,
        )
        external = SubtitleArtifact(
            SubtitleOrigin.EXTERNAL,
            ArtifactState.VALID,
            language="eng",
            title="English",
            path=sidecar_path.resolve(),
            validation=SubtitleValidation(True, 1, "utf-8"),
            content_sha256=sidecar_hash,
        )
        chapter = MediaChapter(
            7,
            0.0,
            10.0,
            "Intro",
            (
                ("comment", "Opening"),
                ("language", "eng"),
                ("title", "Intro"),
            ),
        )
        inventory = VideoInventory(
            source.resolve(),
            source_streams,
            (embedded, external),
            format_name="mov,mp4,m4a,3gp,3g2,mj2",
            duration_seconds=10.0,
            chapters=(chapter,),
            metadata=(
                ("encoder", "SourceMuxer"),
                ("major_brand", "isom"),
                ("title", "Lesson"),
            ),
        )

        output_streams = (
            replace(
                source_streams[0],
                metadata=(),
            ),
            replace(
                source_streams[1],
                metadata=(
                    ("COMMENT", "Primary"),
                    ("language", "eng"),
                    ("title", "English Audio"),
                ),
            ),
            replace(
                source_streams[2],
                is_default=False,
                dispositions=frozenset({"forced"}),
            ),
            MediaStream(
                3,
                StreamKind.SUBTITLE,
                "subrip",
                language="eng",
                title="English",
                metadata=(("SUBTITLES_BRIDGE_SHA256", sidecar_hash),),
            ),
        )
        output_chapter = MediaChapter(
            1,
            0.01,
            10.03,
            "Intro",
            (
                ("COMMENT", "Opening"),
                ("LANGUAGE", "eng"),
                ("TITLE", "Intro"),
            ),
        )
        inspection = MediaInspection(
            output_streams,
            format_name="matroska,webm",
            duration_seconds=10.4,
            chapters=(output_chapter,),
            metadata=(("ENCODER", "Lavf"), ("TITLE", "Lesson")),
        )
        return root, inventory, (embedded, external), staged, inspection

    def verify(self, inventory, expected, staged, inspection):
        probe = FakeProbe(inspection)
        proof = OutputContractVerifier(probe).verify(
            inventory,
            staged,
            expected,
        )
        return proof, probe

    def test_returns_immutable_snapshot_for_a_complete_output(self):
        _, inventory, expected, staged, inspection = self.make_case()

        proof, probe = self.verify(inventory, expected, staged, inspection)

        stat = staged.stat()
        self.assertEqual(probe.calls, [staged])
        self.assertEqual(proof.source, inventory.source)
        self.assertEqual(proof.staged_path, staged)
        self.assertEqual(proof.expected_subtitles, expected)
        self.assertEqual(proof.size_bytes, stat.st_size)
        self.assertEqual(proof.modified_time_ns, stat.st_mtime_ns)

    def test_rejects_missing_reordered_or_changed_source_streams(self):
        cases = (
            (
                lambda inspection: replace(
                    inspection,
                    streams=inspection.streams[:-1],
                ),
                "Stream count mismatch",
            ),
            (
                lambda inspection: replace(
                    inspection,
                    streams=(
                        replace(inspection.streams[0], codec_name="hevc"),
                        *inspection.streams[1:],
                    ),
                ),
                "changed codec",
            ),
            (
                lambda inspection: replace(
                    inspection,
                    streams=(
                        inspection.streams[0],
                        replace(inspection.streams[1], language="spa"),
                        *inspection.streams[2:],
                    ),
                ),
                "changed language",
            ),
            (
                lambda inspection: replace(
                    inspection,
                    streams=(
                        inspection.streams[0],
                        replace(
                            inspection.streams[1],
                            is_default=False,
                            dispositions=frozenset({"dub"}),
                        ),
                        *inspection.streams[2:],
                    ),
                ),
                "changed dispositions",
            ),
        )
        for change, message in cases:
            with self.subTest(message=message):
                _, inventory, expected, staged, inspection = self.make_case()
                with self.assertRaisesRegex(VerificationError, message):
                    self.verify(inventory, expected, staged, change(inspection))

    def test_rejects_lost_embedded_flags_or_incorrect_added_subtitles(self):
        cases = (
            (
                lambda streams: (
                    *streams[:2],
                    replace(
                        streams[2],
                        is_default=True,
                        dispositions=frozenset({"default", "forced"}),
                    ),
                    streams[3],
                ),
                "changed dispositions",
            ),
            (
                lambda streams: (
                    *streams[:3],
                    replace(
                        streams[3],
                        is_default=True,
                        dispositions=frozenset({"default"}),
                    ),
                ),
                "marked as default",
            ),
            (
                lambda streams: (
                    *streams[:3],
                    replace(streams[3], title="Wrong"),
                ),
                "changed title",
            ),
            (
                lambda streams: (
                    *streams[:3],
                    replace(
                        streams[3],
                        metadata=(("SUBTITLES_BRIDGE_SHA256", "b" * 64),),
                    ),
                ),
                "changed subtitle SHA-256",
            ),
        )
        for change, message in cases:
            with self.subTest(message=message):
                _, inventory, expected, staged, inspection = self.make_case()
                changed = replace(inspection, streams=change(inspection.streams))
                with self.assertRaisesRegex(VerificationError, message):
                    self.verify(inventory, expected, staged, changed)

    def test_rejects_format_duration_chapter_and_stable_metadata_mismatches(self):
        cases = (
            (lambda item: replace(item, format_name="mov,mp4"), "not Matroska"),
            (lambda item: replace(item, duration_seconds=12.0), "Duration mismatch"),
            (
                lambda item: replace(
                    item,
                    chapters=(replace(item.chapters[0], start_seconds=0.2),),
                ),
                "time range",
            ),
            (
                lambda item: replace(
                    item,
                    chapters=(
                        replace(
                            item.chapters[0],
                            metadata=(("comment", "Opening"),),
                        ),
                    ),
                ),
                "metadata was not preserved",
            ),
            (lambda item: replace(item, metadata=()), "metadata was not preserved"),
        )
        for change, message in cases:
            with self.subTest(message=message):
                _, inventory, expected, staged, inspection = self.make_case()
                with self.assertRaisesRegex(VerificationError, message):
                    self.verify(inventory, expected, staged, change(inspection))

    def test_rejects_missing_expectations_and_files_that_change_during_probe(self):
        _, inventory, expected, staged, inspection = self.make_case()
        with self.assertRaisesRegex(VerificationError, "embedded subtitles"):
            self.verify(inventory, expected[1:], staged, inspection)

        expected[1].path.unlink()
        with self.assertRaisesRegex(VerificationError, "missing or empty"):
            self.verify(inventory, expected, staged, inspection)

        _, inventory, expected, staged, inspection = self.make_case()
        expected[1].path.write_text(
            "1\n00:00:00,000 --> 00:00:01,000\nChanged\n",
            encoding="utf-8",
        )
        with self.assertRaisesRegex(VerificationError, "changed after mux"):
            self.verify(inventory, expected, staged, inspection)

        _, inventory, expected, staged, inspection = self.make_case()
        probe = FakeProbe(
            inspection,
            hook=lambda path: path.write_bytes(path.read_bytes() + b"changed"),
        )
        with self.assertRaisesRegex(VerificationError, "changed while"):
            OutputContractVerifier(probe).verify(inventory, staged, expected)


class RecordingVerifier:
    def __init__(self, inspection):
        self.inspection = inspection
        self.calls = []

    def verify(self, inventory, output, expected_subtitles):
        self.calls.append((inventory, output, tuple(expected_subtitles)))
        stat = output.stat()
        return VerifiedOutput(
            inventory.source,
            output,
            self.inspection,
            tuple(expected_subtitles),
            stat.st_size,
            stat.st_mtime_ns,
        )


class VerificationStageTests(unittest.TestCase):
    def make_workspace(self, *, with_subtitle=True):
        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        root = Path(temporary_directory.name)
        source = root / "lesson.mp4"
        source.write_bytes(b"source")
        subtitles = ()
        if with_subtitle:
            sidecar = root / "lesson.en.srt"
            sidecar.write_text(
                "1\n00:00:00,000 --> 00:00:01,000\nHello\n",
                encoding="utf-8",
            )
            subtitles = (
                SubtitleArtifact(
                    SubtitleOrigin.EXTERNAL,
                    ArtifactState.VALID,
                    language="eng",
                    title="English",
                    path=sidecar.resolve(),
                    validation=SubtitleValidation(True, 1, "utf-8"),
                ),
            )
        inventory = VideoInventory(
            source.resolve(),
            (
                MediaStream(0, StreamKind.VIDEO, "h264"),
                MediaStream(1, StreamKind.AUDIO, "aac"),
            ),
            subtitles,
            duration_seconds=10.0,
        )
        paths = WorkspacePaths.from_directory(root)
        return root, source.resolve(), inventory, paths

    def test_passes_exact_planned_subtitles_to_verifier(self):
        _, source, inventory, paths = self.make_workspace()
        batch = BatchPlanner().plan(DiscoveryResult((inventory,)), paths)
        staged = paths.staged_output_for(source)
        staged.parent.mkdir()
        staged.write_bytes(b"staged")
        inspection = MediaInspection(
            (*inventory.streams, MediaStream(2, StreamKind.SUBTITLE, "subrip")),
            format_name="matroska",
            duration_seconds=10.0,
        )
        verifier = RecordingVerifier(inspection)

        proof = VerificationStage(verifier).execute(batch, source, paths)

        self.assertEqual(verifier.calls[0][2], inventory.valid_subtitles)
        self.assertEqual(proof.staged_path, staged)

    def test_skip_and_blocked_plans_never_invoke_verifier(self):
        root, source, inventory, paths = self.make_workspace()
        final = paths.output_for(source)
        final.parent.mkdir()
        final.write_bytes(b"verified")
        resumed_inventory = replace(inventory, existing_output=final.resolve())
        resumed = BatchPlanner().plan(
            DiscoveryResult((resumed_inventory,)),
            paths,
            (PlanningChoice(source, verified_output=final),),
        )
        verifier = RecordingVerifier(MediaInspection(inventory.streams))

        self.assertIsNone(VerificationStage(verifier).execute(resumed, source, paths))
        self.assertEqual(verifier.calls, [])

        issue = DiscoveryIssue(
            DiscoveryIssueKind.UNASSOCIATED_SUBTITLE,
            root / "orphan.srt",
            "No video matches subtitle",
        )
        blocked = BatchPlanner().plan(
            DiscoveryResult((inventory,), (issue,)),
            paths,
        )
        with self.assertRaisesRegex(VerificationError, "batch is not executable"):
            VerificationStage(verifier).execute(blocked, source, paths)
        self.assertEqual(verifier.calls, [])

    def test_generated_plan_requires_the_validated_transcription_artifact(self):
        _, source, inventory, paths = self.make_workspace(with_subtitle=False)
        batch = BatchPlanner().plan(DiscoveryResult((inventory,)), paths)
        staged = paths.staged_output_for(source)
        staged.parent.mkdir()
        staged.write_bytes(b"staged")
        verifier = RecordingVerifier(
            MediaInspection(
                (*inventory.streams, MediaStream(2, StreamKind.SUBTITLE, "subrip")),
                format_name="matroska",
                duration_seconds=10.0,
            )
        )

        with self.assertRaisesRegex(VerificationError, "requires the generated"):
            VerificationStage(verifier).execute(batch, source, paths)

        generated_path = paths.staging_directory / "lesson.generated.eng.srt"
        generated_path.write_text(
            "1\n00:00:00,000 --> 00:00:01,000\nHello\n",
            encoding="utf-8",
        )
        generated = SubtitleArtifact(
            SubtitleOrigin.GENERATED,
            ArtifactState.VALID,
            language="eng",
            path=generated_path,
            validation=SubtitleValidation(True, 1, "utf-8"),
        )

        proof = VerificationStage(verifier).execute(
            batch,
            source,
            paths,
            generated_subtitle=generated,
        )

        self.assertEqual(proof.expected_subtitles, (generated,))


if __name__ == "__main__":
    unittest.main()
