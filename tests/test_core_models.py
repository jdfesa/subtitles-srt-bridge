from dataclasses import FrozenInstanceError
from pathlib import Path
import unittest

from subtitles_bridge.models import (
    ArtifactState,
    MediaStream,
    PipelineStage,
    PlanDecision,
    ResultStatus,
    StageAction,
    StreamKind,
    SubtitleArtifact,
    SubtitleOrigin,
    VideoInventory,
    VideoPlan,
    VideoResult,
)


class MediaStreamTests(unittest.TestCase):
    def test_stream_is_immutable(self):
        stream = MediaStream(0, StreamKind.VIDEO, "h264")

        with self.assertRaises(FrozenInstanceError):
            stream.codec_name = "hevc"

    def test_rejects_negative_index(self):
        with self.assertRaisesRegex(ValueError, "cannot be negative"):
            MediaStream(-1, StreamKind.AUDIO, "aac")

    def test_rejects_empty_codec_or_language(self):
        with self.assertRaisesRegex(ValueError, "codec"):
            MediaStream(0, StreamKind.VIDEO, " ")
        with self.assertRaisesRegex(ValueError, "language"):
            MediaStream(0, StreamKind.AUDIO, "aac", language="")


class SubtitleArtifactTests(unittest.TestCase):
    def test_external_subtitle_requires_a_path(self):
        with self.assertRaisesRegex(ValueError, "require a path"):
            SubtitleArtifact(
                origin=SubtitleOrigin.EXTERNAL,
                state=ArtifactState.VALID,
            )

    def test_generated_subtitle_cannot_reference_a_stream(self):
        with self.assertRaisesRegex(ValueError, "cannot use a stream index"):
            SubtitleArtifact(
                origin=SubtitleOrigin.GENERATED,
                state=ArtifactState.VALID,
                path=Path("lesson.en.srt"),
                stream_index=2,
            )

    def test_embedded_subtitle_requires_only_a_stream_index(self):
        subtitle = SubtitleArtifact(
            origin=SubtitleOrigin.EMBEDDED,
            state=ArtifactState.VALID,
            language="eng",
            stream_index=3,
        )

        self.assertEqual(subtitle.stream_index, 3)
        self.assertIsNone(subtitle.path)

        with self.assertRaisesRegex(ValueError, "external path"):
            SubtitleArtifact(
                origin=SubtitleOrigin.EMBEDDED,
                state=ArtifactState.VALID,
                path=Path("lesson.srt"),
                stream_index=3,
            )


class VideoInventoryTests(unittest.TestCase):
    def make_inventory(self):
        streams = (
            MediaStream(0, StreamKind.VIDEO, "h264"),
            MediaStream(1, StreamKind.AUDIO, "aac", language="eng", is_default=True),
            MediaStream(2, StreamKind.AUDIO, "aac", language="spa"),
            MediaStream(3, StreamKind.SUBTITLE, "subrip", language="eng"),
        )
        subtitles = (
            SubtitleArtifact(
                origin=SubtitleOrigin.EMBEDDED,
                state=ArtifactState.VALID,
                language="eng",
                stream_index=3,
            ),
            SubtitleArtifact(
                origin=SubtitleOrigin.EXTERNAL,
                state=ArtifactState.INVALID,
                language="spa",
                path=Path("lesson.es.srt"),
            ),
        )
        return VideoInventory(Path("lesson.mkv"), streams, subtitles)

    def test_filters_streams_and_valid_subtitles(self):
        inventory = self.make_inventory()

        self.assertEqual([stream.index for stream in inventory.video_streams], [0])
        self.assertEqual([stream.index for stream in inventory.audio_streams], [1, 2])
        self.assertEqual(
            [subtitle.stream_index for subtitle in inventory.embedded_subtitles],
            [3],
        )
        self.assertEqual(len(inventory.valid_subtitles), 1)
        self.assertTrue(inventory.has_valid_subtitles)

    def test_rejects_duplicate_stream_indices(self):
        streams = (
            MediaStream(0, StreamKind.VIDEO, "h264"),
            MediaStream(0, StreamKind.AUDIO, "aac"),
        )

        with self.assertRaisesRegex(ValueError, "unique"):
            VideoInventory(Path("lesson.mkv"), streams)


class VideoPlanTests(unittest.TestCase):
    def setUp(self):
        self.inventory = VideoInventory(Path("lesson.mkv"))

    def test_finds_decision_by_stage(self):
        decision = PlanDecision(
            PipelineStage.TRANSCRIBE,
            StageAction.SKIP,
            "A valid subtitle already exists",
        )
        plan = VideoPlan(
            self.inventory,
            Path("output/lesson.subtitled.mkv"),
            Path("trash/lesson"),
            (decision,),
        )

        self.assertIs(plan.decision_for(PipelineStage.TRANSCRIBE), decision)
        with self.assertRaises(KeyError):
            plan.decision_for(PipelineStage.MUX)

    def test_rejects_duplicate_stage_decisions(self):
        decisions = (
            PlanDecision(PipelineStage.MUX, StageAction.RUN, "Build output"),
            PlanDecision(PipelineStage.MUX, StageAction.SKIP, "Output exists"),
        )

        with self.assertRaisesRegex(ValueError, "only once"):
            VideoPlan(
                self.inventory,
                Path("output/lesson.subtitled.mkv"),
                Path("trash/lesson"),
                decisions,
            )

    def test_decision_requires_a_reason(self):
        with self.assertRaisesRegex(ValueError, "require a reason"):
            PlanDecision(PipelineStage.VERIFY, StageAction.RUN, " ")


class VideoResultTests(unittest.TestCase):
    def test_represents_partial_output_without_hiding_final_path(self):
        result = VideoResult(
            source=Path("lesson.mp4"),
            status=ResultStatus.PARTIAL,
            message="Output verified but archival failed",
            output_path=Path("output/lesson.subtitled.mkv"),
        )

        self.assertEqual(result.status.value, "partial")
        self.assertIsNotNone(result.output_path)


if __name__ == "__main__":
    unittest.main()
