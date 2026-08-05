"""Batch-level planning, discovery blockers, and destination collisions."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from .errors import PlanningError
from .models import (
    BatchPlan,
    DiscoveryIssueKind,
    DiscoveryResult,
    PlanningChoice,
    VideoInventory,
)
from .paths import WorkspacePaths
from .planner import VideoPlanner


def _source_key(path: Path) -> str:
    return str(path.resolve())


def _destination_key(path: Path) -> str:
    return str(path.resolve()).casefold()


class BatchPlanner:
    def __init__(self, video_planner: VideoPlanner | None = None) -> None:
        self.video_planner = video_planner or VideoPlanner()

    def plan(
        self,
        discovery: DiscoveryResult,
        paths: WorkspacePaths,
        choices: Sequence[PlanningChoice] = (),
    ) -> BatchPlan:
        choice_by_source = self._choice_map(choices)
        inventory_keys = {_source_key(item.source) for item in discovery.inventories}
        unknown_choices = set(choice_by_source) - inventory_keys
        if unknown_choices:
            raise PlanningError("A planning choice does not match a discovered video")

        routes = {
            _source_key(inventory.source): (
                paths.output_for(inventory.source),
                paths.trash_for(inventory.source),
            )
            for inventory in discovery.inventories
        }
        blockers: dict[str, list[str]] = {
            _source_key(inventory.source): [] for inventory in discovery.inventories
        }
        self._add_discovery_blockers(discovery, blockers)
        self._add_destination_blockers(discovery, routes, blockers)

        plans = tuple(
            self.video_planner.plan(
                inventory,
                routes[_source_key(inventory.source)][0],
                routes[_source_key(inventory.source)][1],
                choice=choice_by_source.get(_source_key(inventory.source)),
                blockers=blockers[_source_key(inventory.source)],
            )
            for inventory in discovery.inventories
        )
        return BatchPlan(plans, discovery.issues)

    @staticmethod
    def _choice_map(
        choices: Sequence[PlanningChoice],
    ) -> dict[str, PlanningChoice]:
        result: dict[str, PlanningChoice] = {}
        for choice in choices:
            key = _source_key(choice.source)
            if key in result:
                raise PlanningError(f"Duplicate planning choice for {choice.source}")
            result[key] = choice
        return result

    @staticmethod
    def _add_discovery_blockers(
        discovery: DiscoveryResult,
        blockers: dict[str, list[str]],
    ) -> None:
        for issue in discovery.issues:
            if issue.kind is not DiscoveryIssueKind.AMBIGUOUS_SUBTITLE:
                continue
            for candidate in issue.candidate_videos:
                key = _source_key(candidate)
                if key in blockers:
                    blockers[key].append(issue.message)

    @staticmethod
    def _add_destination_blockers(
        discovery: DiscoveryResult,
        routes: dict[str, tuple[Path, Path]],
        blockers: dict[str, list[str]],
    ) -> None:
        for label, route_position in (("output", 0), ("trash", 1)):
            groups: dict[str, list[VideoInventory]] = {}
            for inventory in discovery.inventories:
                source_key = _source_key(inventory.source)
                destination_key = _destination_key(routes[source_key][route_position])
                groups.setdefault(destination_key, []).append(inventory)
            for inventories in groups.values():
                if len(inventories) < 2:
                    continue
                names = ", ".join(item.source.name for item in inventories)
                destination = routes[_source_key(inventories[0].source)][route_position]
                reason = (
                    f"Multiple videos share the {label} destination "
                    f"{destination}: {names}"
                )
                for inventory in inventories:
                    blockers[_source_key(inventory.source)].append(reason)
