"""Deterministic text summaries for read-only preflight plans."""

from __future__ import annotations

from .models import (
    BatchPlan,
    MediaStream,
    SubtitleArtifact,
    SubtitleOrigin,
    VideoPlan,
)


def _format_audio(stream: MediaStream) -> str:
    details = [f"#{stream.index}", stream.language]
    if stream.is_default:
        details.append("default")
    if stream.title:
        details.append(stream.title)
    return " ".join(details)


def _format_subtitle(subtitle: SubtitleArtifact) -> str:
    if subtitle.origin is SubtitleOrigin.EMBEDDED:
        location = f"stream #{subtitle.stream_index}"
    else:
        location = str(subtitle.path)
    details = [
        f"[{subtitle.state.value}]",
        subtitle.origin.value,
        location,
        f"({subtitle.language})",
    ]
    if subtitle.title:
        details.append(subtitle.title)
    if subtitle.message:
        details.append(f"- {subtitle.message}")
    return " ".join(details)


def format_video_plan(plan: VideoPlan) -> str:
    inventory = plan.inventory
    lines = [
        f"Video: {inventory.source}",
        f"Status: {'ready' if plan.is_executable else 'needs-input'}",
    ]

    if inventory.audio_streams:
        lines.append(
            "Audio: " + ", ".join(_format_audio(stream) for stream in inventory.audio_streams)
        )
    else:
        lines.append("Audio: none")

    lines.append("Subtitles:")
    if inventory.subtitles:
        lines.extend(f"  - {_format_subtitle(item)}" for item in inventory.subtitles)
    else:
        lines.append("  - none")

    output_state = (
        "verified"
        if plan.uses_verified_output
        else "existing-unverified"
        if inventory.existing_output is not None
        else "missing"
    )
    trash_state = "existing" if inventory.existing_trash is not None else "missing"
    lines.extend(
        (
            f"Output: {plan.output_path} ({output_state})",
            f"Trash: {plan.trash_path} ({trash_state})",
            "Plan:",
        )
    )
    lines.extend(
        f"  [{decision.action.value}] {decision.stage.value}: {decision.reason}"
        for decision in plan.decisions
    )
    return "\n".join(lines)


def format_batch_plan(plan: BatchPlan) -> str:
    status = "ready" if plan.is_executable else "needs-input"
    lines = [f"Batch: {len(plan.videos)} video(s)", f"Status: {status}"]
    if plan.issues:
        lines.append("Discovery issues:")
        lines.extend(
            f"  [needs-input] {issue.kind.value}: {issue.path} - {issue.message}"
            for issue in plan.issues
        )
    for video_plan in plan.videos:
        lines.extend(("", format_video_plan(video_plan)))
    return "\n".join(lines)
