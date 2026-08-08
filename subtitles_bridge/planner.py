"""Pure planning rules over read-only discovery results."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from pathlib import Path

from .errors import PlanningError
from .models import (
    ArtifactState,
    MediaStream,
    PipelineStage,
    PlanDecision,
    PlanningChoice,
    StageAction,
    SubtitleArtifact,
    SubtitleOrigin,
    VideoInventory,
    VideoPlan,
)

EXECUTION_STAGES = (
    PipelineStage.TRANSCRIBE,
    PipelineStage.MUX,
    PipelineStage.VERIFY,
    PipelineStage.PUBLISH,
    PipelineStage.ARCHIVE,
)


def _source_key(path: Path) -> str:
    return str(path.resolve())


def _destination_key(path: Path) -> str:
    return str(path.resolve()).casefold()


def _blocked_decisions(reason: str) -> tuple[PlanDecision, ...]:
    return tuple(
        PlanDecision(stage, StageAction.NEEDS_INPUT, reason)
        for stage in EXECUTION_STAGES
    )


def _join_reasons(reasons: Iterable[str]) -> str:
    return "; ".join(dict.fromkeys(reasons))


def _archive_name_collision(inventory: VideoInventory) -> str | None:
    paths = [inventory.source]
    paths.extend(
        subtitle.path
        for subtitle in inventory.valid_subtitles
        if subtitle.origin is SubtitleOrigin.EXTERNAL and subtitle.path is not None
    )
    groups: dict[str, list[Path]] = {}
    for path in paths:
        groups.setdefault(path.name.casefold(), []).append(path)
    for colliding in groups.values():
        if len(colliding) > 1:
            rendered = ", ".join(str(path) for path in colliding)
            return f"Archive inputs share a destination filename: {rendered}"
    return None


def _select_audio(
    inventory: VideoInventory,
    requested_index: int | None,
) -> tuple[MediaStream | None, str | None]:
    audio_streams = inventory.audio_streams
    if requested_index is not None:
        for stream in audio_streams:
            if stream.index == requested_index:
                return stream, None
        return None, f"Selected audio stream #{requested_index} is not available"

    if not audio_streams:
        return None, "No audio stream is available for transcription"
    if len(audio_streams) == 1:
        return audio_streams[0], None

    default_streams = tuple(stream for stream in audio_streams if stream.is_default)
    if len(default_streams) == 1:
        return default_streams[0], None

    indices = ", ".join(f"#{stream.index}" for stream in audio_streams)
    return None, f"Select one audio stream for transcription: {indices}"


class VideoPlanner:
    def plan(
        self,
        inventory: VideoInventory,
        output_path: Path,
        trash_path: Path,
        *,
        choice: PlanningChoice | None = None,
        blockers: Sequence[str] = (),
    ) -> VideoPlan:
        if choice is not None and _source_key(choice.source) != _source_key(
            inventory.source
        ):
            raise PlanningError("Planning choice does not match the video inventory")
        selected_subtitles = inventory.valid_subtitles
        ambiguity_reasons = [
            subtitle.message or "Subtitle metadata requires a decision"
            for subtitle in inventory.subtitles
            if subtitle.state is ArtifactState.AMBIGUOUS
        ]
        all_blockers = list(blockers) + ambiguity_reasons
        archive_collision = _archive_name_collision(inventory)
        if archive_collision is not None:
            all_blockers.append(archive_collision)

        verified_output, verification_error = self._verified_output(
            inventory,
            output_path,
            choice,
        )
        if verification_error is not None:
            all_blockers.append(verification_error)
        if not verified_output and inventory.existing_output is not None:
            all_blockers.append(
                f"Existing output is not verified: {inventory.existing_output}"
            )
        if not verified_output and inventory.existing_trash is not None:
            all_blockers.append(
                f"Trash destination already exists: {inventory.existing_trash}"
            )
        if all_blockers:
            return VideoPlan(
                inventory,
                output_path,
                trash_path,
                _blocked_decisions(_join_reasons(all_blockers)),
                selected_subtitles=selected_subtitles,
            )
        if verified_output:
            return self._resume_verified_output(
                inventory,
                output_path,
                trash_path,
                selected_subtitles,
            )

        if selected_subtitles:
            return self._reuse_subtitles(
                inventory,
                output_path,
                trash_path,
                selected_subtitles,
            )

        requested_audio = choice.audio_stream_index if choice is not None else None
        audio, selection_error = _select_audio(inventory, requested_audio)
        if selection_error is not None:
            return VideoPlan(
                inventory,
                output_path,
                trash_path,
                _blocked_decisions(selection_error),
            )
        assert audio is not None
        return self._generate_subtitle(inventory, output_path, trash_path, audio)

    @staticmethod
    def _verified_output(
        inventory: VideoInventory,
        output_path: Path,
        choice: PlanningChoice | None,
    ) -> tuple[bool, str | None]:
        if choice is None or choice.verified_output is None:
            return False, None
        if inventory.existing_output is None:
            return False, "The selected verified output no longer exists"
        if _destination_key(choice.verified_output) != _destination_key(output_path):
            return False, f"Verified output does not match destination: {output_path}"
        if _destination_key(inventory.existing_output) != _destination_key(output_path):
            return False, f"Discovered output does not match destination: {output_path}"
        return True, None

    @staticmethod
    def _resume_verified_output(
        inventory: VideoInventory,
        output_path: Path,
        trash_path: Path,
        selected_subtitles: tuple[SubtitleArtifact, ...],
    ) -> VideoPlan:
        decisions = [
            PlanDecision(
                PipelineStage.TRANSCRIBE,
                StageAction.SKIP,
                "A verified output already satisfies the subtitle contract",
            ),
            PlanDecision(
                PipelineStage.MUX,
                StageAction.SKIP,
                "A verified output already contains the required streams",
            ),
            PlanDecision(
                PipelineStage.VERIFY,
                StageAction.SKIP,
                "The existing output was verified during preflight",
            ),
            PlanDecision(
                PipelineStage.PUBLISH,
                StageAction.SKIP,
                "The verified output is already published",
            ),
        ]
        if inventory.existing_trash is None:
            decisions.append(
                PlanDecision(
                    PipelineStage.ARCHIVE,
                    StageAction.RUN,
                    "Archive the remaining source and incorporated sidecars",
                )
            )
        else:
            decisions.append(
                PlanDecision(
                    PipelineStage.ARCHIVE,
                    StageAction.NEEDS_INPUT,
                    f"Trash destination already exists: {inventory.existing_trash}",
                )
            )
        return VideoPlan(
            inventory,
            output_path,
            trash_path,
            tuple(decisions),
            selected_subtitles=selected_subtitles,
            uses_verified_output=True,
        )

    @staticmethod
    def _reuse_subtitles(
        inventory: VideoInventory,
        output_path: Path,
        trash_path: Path,
        selected_subtitles: tuple[SubtitleArtifact, ...],
    ) -> VideoPlan:
        embedded_count = sum(
            subtitle.origin is SubtitleOrigin.EMBEDDED
            for subtitle in selected_subtitles
        )
        external_count = sum(
            subtitle.origin is SubtitleOrigin.EXTERNAL
            for subtitle in selected_subtitles
        )
        decisions = (
            PlanDecision(
                PipelineStage.TRANSCRIBE,
                StageAction.SKIP,
                f"Reuse {len(selected_subtitles)} valid subtitle track(s)",
            ),
            PlanDecision(
                PipelineStage.MUX,
                StageAction.RUN,
                (
                    f"Copy all {len(inventory.streams)} source stream(s), preserve "
                    f"{embedded_count} embedded subtitle(s), and add "
                    f"{external_count} external sidecar(s)"
                ),
            ),
            PlanDecision(
                PipelineStage.VERIFY,
                StageAction.RUN,
                "Verify streams, subtitle tracks, metadata, and duration",
            ),
            PlanDecision(
                PipelineStage.PUBLISH,
                StageAction.RUN,
                f"Publish the verified MKV to {output_path}",
            ),
            PlanDecision(
                PipelineStage.ARCHIVE,
                StageAction.RUN,
                f"Archive the source and {external_count} incorporated sidecar(s)",
            ),
        )
        return VideoPlan(
            inventory,
            output_path,
            trash_path,
            decisions,
            selected_subtitles=selected_subtitles,
        )

    @staticmethod
    def _generate_subtitle(
        inventory: VideoInventory,
        output_path: Path,
        trash_path: Path,
        audio: MediaStream,
    ) -> VideoPlan:
        decisions = (
            PlanDecision(
                PipelineStage.TRANSCRIBE,
                StageAction.RUN,
                f"Generate one subtitle from audio stream #{audio.index}",
            ),
            PlanDecision(
                PipelineStage.MUX,
                StageAction.RUN,
                (
                    f"Copy all {len(inventory.streams)} source stream(s) and add "
                    "the generated subtitle"
                ),
            ),
            PlanDecision(
                PipelineStage.VERIFY,
                StageAction.RUN,
                "Verify streams, subtitle tracks, metadata, and duration",
            ),
            PlanDecision(
                PipelineStage.PUBLISH,
                StageAction.RUN,
                f"Publish the verified MKV to {output_path}",
            ),
            PlanDecision(
                PipelineStage.ARCHIVE,
                StageAction.RUN,
                "Archive the source and generated sidecar",
            ),
        )
        return VideoPlan(
            inventory,
            output_path,
            trash_path,
            decisions,
            transcription_audio_index=audio.index,
        )
