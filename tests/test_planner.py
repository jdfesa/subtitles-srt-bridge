import tempfile
import unittest
from pathlib import Path

from subtitles_bridge.batch_planner import BatchPlanner
from subtitles_bridge.errors import PlanningError
from subtitles_bridge.models import (
    ArtifactState,
    DiscoveryIssue,
    DiscoveryIssueKind,
    DiscoveryResult,
    MediaStream,
    PipelineStage,
    PlanningChoice,
    StageAction,
    StreamKind,
    SubtitleArtifact,
    SubtitleOrigin,
    VideoInventory,
)
from subtitles_bridge.paths import WorkspacePaths
from subtitles_bridge.summary import format_batch_plan, format_video_plan


def audio(index, *, default=False, language="eng"):
    return MediaStream(
        index,
        StreamKind.AUDIO,
        "aac",
        language=language,
        is_default=default,
    )


def external(path, state=ArtifactState.VALID, language="eng", message=None):
    return SubtitleArtifact(
        SubtitleOrigin.EXTERNAL,
        state,
        language=language,
        path=path,
        message=message,
    )


class PlannerTests(unittest.TestCase):
    def make_workspace(self, names=("lesson.mkv",)):
        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        root = Path(temporary_directory.name)
        sources = []
        for name in names:
            source = root / name
            source.touch()
            sources.append(source.resolve())
        return root, WorkspacePaths.from_directory(root), tuple(sources)

    @staticmethod
    def inventory(
        source,
        *,
        audios=(),
        subtitles=(),
        existing_output=None,
        existing_trash=None,
        extra_streams=(),
    ):
        streams = (
            MediaStream(0, StreamKind.VIDEO, "h264"),
            *audios,
            *extra_streams,
        )
        return VideoInventory(
            source,
            streams,
            subtitles,
            existing_output=existing_output,
            existing_trash=existing_trash,
        )

    def plan_one(self, inventory, paths, choices=(), issues=()):
        batch = BatchPlanner().plan(
            DiscoveryResult((inventory,), tuple(issues)),
            paths,
            choices,
        )
        return batch, batch.videos[0]

    def test_reuses_every_valid_subtitle_and_excludes_invalid_artifacts(self):
        root, paths, (source,) = self.make_workspace()
        valid_external = external(root / "lesson.en.srt")
        invalid_external = external(
            root / "lesson.bad.srt",
            ArtifactState.INVALID,
            message="Malformed SRT",
        )
        embedded_stream = MediaStream(2, StreamKind.SUBTITLE, "subrip", language="spa")
        embedded = SubtitleArtifact(
            SubtitleOrigin.EMBEDDED,
            ArtifactState.VALID,
            language="spa",
            stream_index=2,
        )
        inventory = self.inventory(
            source,
            audios=(audio(1),),
            subtitles=(embedded, valid_external, invalid_external),
            extra_streams=(embedded_stream,),
        )

        batch, plan = self.plan_one(inventory, paths)

        self.assertTrue(batch.is_executable)
        self.assertEqual(plan.selected_subtitles, (embedded, valid_external))
        self.assertEqual(
            plan.decision_for(PipelineStage.TRANSCRIBE).action,
            StageAction.SKIP,
        )
        self.assertEqual(plan.decision_for(PipelineStage.MUX).action, StageAction.RUN)
        self.assertIn("1 external", plan.decision_for(PipelineStage.MUX).reason)

    def test_invalid_subtitle_does_not_prevent_single_audio_transcription(self):
        root, paths, (source,) = self.make_workspace()
        invalid = external(
            root / "lesson.srt",
            ArtifactState.INVALID,
            message="Empty SRT",
        )
        inventory = self.inventory(source, audios=(audio(4),), subtitles=(invalid,))

        _, plan = self.plan_one(inventory, paths)

        self.assertEqual(
            plan.decision_for(PipelineStage.TRANSCRIBE).action,
            StageAction.RUN,
        )
        self.assertEqual(plan.transcription_audio_index, 4)
        self.assertEqual(plan.selected_subtitles, ())

    def test_selects_the_only_default_audio_or_an_explicit_audio(self):
        _, paths, (source,) = self.make_workspace()
        inventory = self.inventory(
            source,
            audios=(audio(1), audio(2, default=True, language="spa")),
        )

        _, automatic = self.plan_one(inventory, paths)
        _, explicit = self.plan_one(
            inventory,
            paths,
            (PlanningChoice(source, audio_stream_index=1),),
        )

        self.assertEqual(automatic.transcription_audio_index, 2)
        self.assertEqual(explicit.transcription_audio_index, 1)

    def test_blocks_zero_or_ambiguous_audio_candidates(self):
        _, paths, (source,) = self.make_workspace()
        inventories = (
            self.inventory(source),
            self.inventory(source, audios=(audio(1), audio(2))),
            self.inventory(
                source,
                audios=(audio(1, default=True), audio(2, default=True)),
            ),
        )

        for inventory in inventories:
            with self.subTest(audio_count=len(inventory.audio_streams)):
                _, plan = self.plan_one(inventory, paths)
                self.assertTrue(plan.has_needs_input)
                self.assertEqual(
                    {decision.action for decision in plan.decisions},
                    {StageAction.NEEDS_INPUT},
                )

    def test_blocks_invalid_explicit_audio_selection(self):
        _, paths, (source,) = self.make_workspace()
        inventory = self.inventory(source, audios=(audio(1), audio(2)))

        _, plan = self.plan_one(
            inventory,
            paths,
            (PlanningChoice(source, audio_stream_index=9),),
        )

        self.assertTrue(plan.has_needs_input)
        self.assertIn("#9", plan.decisions[0].reason)
        self.assertIn("[needs-input] transcribe", format_video_plan(plan))

    def test_blocks_ambiguous_artifact_or_discovery_association(self):
        root, paths, (source,) = self.make_workspace()
        ambiguous = external(
            root / "lesson.en.srt",
            ArtifactState.AMBIGUOUS,
            message="Conflicting language metadata",
        )
        inventory = self.inventory(
            source,
            audios=(audio(1),),
            subtitles=(ambiguous,),
        )

        _, artifact_plan = self.plan_one(inventory, paths)
        issue = DiscoveryIssue(
            DiscoveryIssueKind.AMBIGUOUS_SUBTITLE,
            root / "lesson.srt",
            "Subtitle matches multiple videos",
            (source,),
        )
        issue_batch, issue_plan = self.plan_one(inventory, paths, issues=(issue,))

        self.assertTrue(artifact_plan.has_needs_input)
        self.assertTrue(issue_plan.has_needs_input)
        self.assertTrue(issue_batch.has_needs_input)

    def test_existing_output_requires_verification_before_resume(self):
        root, paths, (source,) = self.make_workspace()
        output = root / "output" / "lesson.subtitled.mkv"
        output.parent.mkdir()
        output.touch()
        inventory = self.inventory(
            source,
            audios=(audio(1),),
            existing_output=output.resolve(),
        )

        _, collision = self.plan_one(inventory, paths)
        _, resumed = self.plan_one(
            inventory,
            paths,
            (PlanningChoice(source, verified_output=output),),
        )

        self.assertTrue(collision.has_needs_input)
        self.assertIn("not verified", collision.decisions[0].reason)
        self.assertTrue(resumed.uses_verified_output)
        for stage in (
            PipelineStage.TRANSCRIBE,
            PipelineStage.MUX,
            PipelineStage.VERIFY,
            PipelineStage.PUBLISH,
        ):
            self.assertEqual(resumed.decision_for(stage).action, StageAction.SKIP)
        self.assertEqual(
            resumed.decision_for(PipelineStage.ARCHIVE).action,
            StageAction.RUN,
        )

    def test_trash_collision_blocks_new_work_and_verified_output_archival(self):
        root, paths, (source,) = self.make_workspace()
        trash = root / "trash" / "lesson"
        trash.mkdir(parents=True)
        ordinary = self.inventory(
            source,
            audios=(audio(1),),
            existing_trash=trash.resolve(),
        )

        _, blocked = self.plan_one(ordinary, paths)
        self.assertEqual(
            {decision.action for decision in blocked.decisions},
            {StageAction.NEEDS_INPUT},
        )

        output = root / "output" / "lesson.subtitled.mkv"
        output.parent.mkdir()
        output.touch()
        resumed_inventory = self.inventory(
            source,
            audios=(audio(1),),
            existing_output=output.resolve(),
            existing_trash=trash.resolve(),
        )
        _, resumed = self.plan_one(
            resumed_inventory,
            paths,
            (PlanningChoice(source, verified_output=output),),
        )

        self.assertEqual(
            resumed.decision_for(PipelineStage.ARCHIVE).action,
            StageAction.NEEDS_INPUT,
        )
        self.assertEqual(
            resumed.decision_for(PipelineStage.PUBLISH).action,
            StageAction.SKIP,
        )

    def test_blocks_sidecars_that_flatten_to_the_same_trash_name(self):
        root, paths, (source,) = self.make_workspace()
        first = external(root / "sub" / "lesson.en.srt")
        second = external(root / "sub_en" / "Lesson.en.srt")
        inventory = self.inventory(
            source,
            audios=(audio(1),),
            subtitles=(first, second),
        )

        _, plan = self.plan_one(inventory, paths)

        self.assertTrue(plan.has_needs_input)
        self.assertIn("share a destination filename", plan.decisions[0].reason)

    def test_blocks_cross_video_output_and_trash_collisions_without_writes(self):
        root, paths, sources = self.make_workspace(("Lesson.mp4", "lesson.mkv"))
        inventories = tuple(
            self.inventory(source, audios=(audio(1),)) for source in sources
        )
        initial_entries = {path.relative_to(root) for path in root.rglob("*")}

        batch = BatchPlanner().plan(DiscoveryResult(inventories), paths)

        self.assertTrue(batch.has_needs_input)
        self.assertTrue(all(plan.has_needs_input for plan in batch.videos))
        self.assertIn("share the output", batch.videos[0].decisions[0].reason)
        self.assertIn("share the trash", batch.videos[0].decisions[0].reason)
        self.assertEqual(
            {path.relative_to(root) for path in root.rglob("*")},
            initial_entries,
        )

    def test_unassociated_discovery_issue_blocks_batch_but_remains_global(self):
        root, paths, (source,) = self.make_workspace()
        subtitle = external(root / "lesson.en.srt")
        inventory = self.inventory(
            source,
            audios=(audio(1),),
            subtitles=(subtitle,),
        )
        issue = DiscoveryIssue(
            DiscoveryIssueKind.UNASSOCIATED_SUBTITLE,
            root / "orphan.srt",
            "No video matches subtitle",
        )

        batch, video_plan = self.plan_one(inventory, paths, issues=(issue,))

        self.assertTrue(video_plan.is_executable)
        self.assertFalse(batch.is_executable)
        self.assertEqual(batch.issues, (issue,))
        self.assertIn("Discovery issues:", format_batch_plan(batch))
        self.assertIn("[needs-input] unassociated-subtitle", format_batch_plan(batch))

    def test_rejects_duplicate_or_unknown_planning_choices(self):
        root, paths, (source,) = self.make_workspace()
        inventory = self.inventory(source, audios=(audio(1),))
        choice = PlanningChoice(source, audio_stream_index=1)

        with self.assertRaisesRegex(PlanningError, "Duplicate"):
            BatchPlanner().plan(
                DiscoveryResult((inventory,)),
                paths,
                (choice, choice),
            )
        with self.assertRaisesRegex(PlanningError, "does not match"):
            BatchPlanner().plan(
                DiscoveryResult((inventory,)),
                paths,
                (PlanningChoice(root / "other.mkv"),),
            )

    def test_formats_deterministic_video_and_batch_summaries(self):
        root, paths, (source,) = self.make_workspace()
        subtitle = external(root / "lesson.en.srt")
        inventory = self.inventory(
            source,
            audios=(audio(1, default=True),),
            subtitles=(subtitle,),
        )
        batch, plan = self.plan_one(inventory, paths)

        video_summary = format_video_plan(plan)
        batch_summary = format_batch_plan(batch)

        self.assertIn(f"Video: {source}", video_summary)
        self.assertIn("Audio: #1 eng default", video_summary)
        self.assertIn("[valid] external", video_summary)
        self.assertIn("[skip] transcribe", video_summary)
        self.assertIn("[run] mux", video_summary)
        self.assertIn("Batch: 1 video(s)", batch_summary)
        self.assertIn("Status: ready", batch_summary)


if __name__ == "__main__":
    unittest.main()
