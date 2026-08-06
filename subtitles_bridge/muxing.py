"""Plan-gated assembly of a copy-only MKV inside staging."""

from __future__ import annotations

from pathlib import Path
import re

from .errors import MuxingCollisionError, MuxingError
from .models import (
    ArtifactState,
    BatchPlan,
    PipelineStage,
    StageAction,
    SubtitleArtifact,
    SubtitleOrigin,
    VideoPlan,
)
from .paths import WorkspacePaths
from .ports import MediaMuxer


class MuxingStage:
    def __init__(self, muxer: MediaMuxer) -> None:
        self.muxer = muxer

    def execute(
        self,
        batch_plan: BatchPlan,
        source: Path,
        paths: WorkspacePaths,
        *,
        generated_subtitle: SubtitleArtifact | None = None,
    ) -> Path | None:
        if not batch_plan.is_executable:
            raise MuxingError(
                "Muxing batch is not executable until all issues are resolved"
            )
        try:
            plan = batch_plan.plan_for(source)
        except KeyError as exc:
            raise MuxingError(f"No video plan exists for {source}") from exc
        try:
            decision = plan.decision_for(PipelineStage.MUX)
        except KeyError as exc:
            raise MuxingError("Plan has no muxing decision") from exc

        if decision.action is StageAction.SKIP:
            return None
        if decision.action is StageAction.NEEDS_INPUT or not plan.is_executable:
            raise MuxingError(f"Muxing plan is not executable: {decision.reason}")

        subtitles = self._planned_subtitles(
            plan,
            paths,
            generated_subtitle,
        )
        staging_directory = paths.staging_directory
        if staging_directory.is_symlink() or (
            staging_directory.exists() and not staging_directory.is_dir()
        ):
            raise MuxingCollisionError(
                f"Staging path is not a safe directory: {staging_directory}"
            )
        try:
            staging_directory.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise MuxingError(
                f"Cannot create staging directory {staging_directory}: {exc}"
            ) from exc

        destination = paths.staged_output_for(plan.inventory.source)
        if destination.exists() or destination.is_symlink():
            raise MuxingCollisionError(
                f"Staged output already exists: {destination}"
            )

        self.muxer.mux(plan.inventory, subtitles, destination)
        try:
            if not destination.is_file() or destination.stat().st_size == 0:
                if destination.is_file():
                    destination.unlink(missing_ok=True)
                raise MuxingError(
                    f"Muxer did not create a usable staged MKV: {destination}"
                )
        except OSError as exc:
            raise MuxingError(
                f"Cannot inspect staged MKV {destination}: {exc}"
            ) from exc
        return destination

    @classmethod
    def _planned_subtitles(
        cls,
        plan: VideoPlan,
        paths: WorkspacePaths,
        generated_subtitle: SubtitleArtifact | None,
    ) -> tuple[SubtitleArtifact, ...]:
        if plan.selected_subtitles != plan.inventory.valid_subtitles:
            raise MuxingError(
                "Plan does not select every valid subtitle from the inventory"
            )
        try:
            transcription = plan.decision_for(PipelineStage.TRANSCRIBE)
        except KeyError as exc:
            raise MuxingError("Plan has no transcription decision") from exc

        if transcription.action is StageAction.RUN:
            if plan.selected_subtitles:
                raise MuxingError(
                    "A transcription plan cannot also select existing subtitles"
                )
            if generated_subtitle is None:
                raise MuxingError(
                    "Muxing requires the generated subtitle from transcription"
                )
            cls._validate_generated_subtitle(
                plan,
                paths,
                generated_subtitle,
            )
            return (generated_subtitle,)

        if transcription.action is not StageAction.SKIP:
            raise MuxingError("Transcription must complete before muxing")
        if generated_subtitle is not None:
            raise MuxingError(
                "Generated subtitle was not planned for this video"
            )
        return plan.selected_subtitles

    @staticmethod
    def _validate_generated_subtitle(
        plan: VideoPlan,
        paths: WorkspacePaths,
        subtitle: SubtitleArtifact,
    ) -> None:
        if subtitle.origin is not SubtitleOrigin.GENERATED:
            raise MuxingError("Transcription did not return a generated subtitle")
        if subtitle.state is not ArtifactState.VALID:
            raise MuxingError("Generated subtitle is not valid")
        if subtitle.validation is None or not subtitle.validation.is_valid:
            raise MuxingError("Generated subtitle was not validated")
        if subtitle.path is None:
            raise MuxingError("Generated subtitle has no path")

        expected = paths.generated_subtitle_target(plan.inventory.source)
        candidate_pattern = re.compile(
            rf"{re.escape(expected.stem)}(?:\.[a-zA-Z]{{2,3}})?\.srt"
        )
        if candidate_pattern.fullmatch(subtitle.path.name) is None:
            raise MuxingError(
                f"Generated subtitle does not belong to the video: {subtitle.path}"
            )
        if subtitle.path.resolve().parent != paths.staging_directory.resolve():
            raise MuxingError("Generated subtitle is outside staging")
        try:
            if not subtitle.path.is_file() or subtitle.path.stat().st_size == 0:
                raise MuxingError(
                    f"Generated subtitle is missing or empty: {subtitle.path}"
                )
        except OSError as exc:
            raise MuxingError(
                f"Cannot inspect generated subtitle {subtitle.path}: {exc}"
            ) from exc
