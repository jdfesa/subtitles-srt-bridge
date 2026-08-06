"""Transactional quarantine of source media and incorporated sidecars."""

from __future__ import annotations

from collections.abc import Callable, Sequence
import os
from pathlib import Path

from ..errors import (
    ArchivingCollisionError,
    ArchivingError,
    ArchivingPartialError,
)
from ..models import ArchivedInputs


Mover = Callable[[Path, Path], None]
Snapshot = tuple[int, int]


class TransactionalInputArchiver:
    def __init__(self, mover: Mover = os.replace) -> None:
        self.mover = mover

    def archive(
        self,
        source: Path,
        sidecars: Sequence[Path],
        destination: Path,
    ) -> ArchivedInputs:
        inputs = (source, *sidecars)
        snapshots = self._validate_inputs(inputs)
        targets = tuple(destination / path.name for path in inputs)
        self._validate_routes(inputs, targets, destination)
        self._reserve_destination(destination, targets)

        mappings = tuple(zip(inputs, targets, strict=True))
        move_order = (*mappings[1:], mappings[0])
        moved: list[tuple[Path, Path]] = []
        try:
            for original, archived in move_order:
                self.mover(original, archived)
                moved.append((original, archived))
                self._require_moved(original, archived, snapshots[original])
        except (OSError, ArchivingError) as exc:
            errors = self._rollback(moved, targets, destination, snapshots)
            if errors:
                rendered = "; ".join(errors)
                raise ArchivingPartialError(
                    f"Archive failed and rollback was incomplete: {exc}; {rendered}"
                ) from exc
            raise ArchivingError(
                f"Archive failed; all moved inputs were restored: {exc}"
            ) from exc

        return ArchivedInputs(source, destination, inputs, targets)

    @staticmethod
    def _validate_inputs(inputs: Sequence[Path]) -> dict[Path, Snapshot]:
        keys = [str(path.resolve()).casefold() for path in inputs]
        if len(keys) != len(set(keys)):
            raise ArchivingCollisionError("Archive inputs contain duplicate paths")

        snapshots: dict[Path, Snapshot] = {}
        for position, path in enumerate(inputs):
            if path.is_symlink():
                raise ArchivingError(f"Archive input cannot be a symlink: {path}")
            try:
                if not path.is_file():
                    raise ArchivingError(f"Archive input is missing: {path}")
                stat = path.stat()
            except OSError as exc:
                raise ArchivingError(
                    f"Cannot inspect archive input {path}: {exc}"
                ) from exc
            if stat.st_size <= 0:
                raise ArchivingError(f"Archive input is empty: {path}")
            if position > 0 and path.suffix.casefold() != ".srt":
                raise ArchivingError(f"Archived sidecar must use .srt: {path}")
            snapshots[path] = (stat.st_size, stat.st_mtime_ns)
        return snapshots

    @staticmethod
    def _validate_routes(
        inputs: Sequence[Path],
        targets: Sequence[Path],
        destination: Path,
    ) -> None:
        target_names = [target.name.casefold() for target in targets]
        if len(target_names) != len(set(target_names)):
            raise ArchivingCollisionError(
                "Archive inputs share a destination filename"
            )
        destination_route = destination.resolve()
        if any(path.resolve() == destination_route for path in inputs):
            raise ArchivingError("Archive destination cannot be an input")
        if destination.is_symlink() or destination.exists():
            raise ArchivingCollisionError(
                f"Trash destination already exists: {destination}"
            )
        parent = destination.parent
        if parent.is_symlink() or (parent.exists() and not parent.is_dir()):
            raise ArchivingCollisionError(
                f"Trash path is not a safe directory: {parent}"
            )

    @classmethod
    def _reserve_destination(
        cls,
        destination: Path,
        targets: Sequence[Path],
    ) -> None:
        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.mkdir(exist_ok=False)
        except FileExistsError as exc:
            raise ArchivingCollisionError(
                f"Trash destination already exists: {destination}"
            ) from exc
        except OSError as exc:
            raise ArchivingError(
                f"Cannot reserve trash destination {destination}: {exc}"
            ) from exc

        try:
            for target in targets:
                target.touch(exist_ok=False)
        except FileExistsError as exc:
            errors = cls._cleanup_reservations(targets, destination)
            message = f"Trash target already exists: {target}"
            if errors:
                message += f"; reservation cleanup failed: {'; '.join(errors)}"
            raise ArchivingCollisionError(message) from exc
        except OSError as exc:
            errors = cls._cleanup_reservations(targets, destination)
            message = f"Cannot reserve trash target {target}: {exc}"
            if errors:
                message += f"; reservation cleanup failed: {'; '.join(errors)}"
            raise ArchivingError(message) from exc

    @staticmethod
    def _require_moved(
        original: Path,
        archived: Path,
        snapshot: Snapshot,
    ) -> None:
        if original.exists() or original.is_symlink():
            raise ArchivingError(f"Mover left the archive input in place: {original}")
        if archived.is_symlink():
            raise ArchivingError(f"Archived input became a symlink: {archived}")
        try:
            if not archived.is_file():
                raise ArchivingError(f"Mover did not create archive target: {archived}")
            stat = archived.stat()
        except OSError as exc:
            raise ArchivingError(
                f"Cannot inspect archived input {archived}: {exc}"
            ) from exc
        if (stat.st_size, stat.st_mtime_ns) != snapshot:
            raise ArchivingError(f"Archived input changed while moving: {archived}")

    def _rollback(
        self,
        moved: Sequence[tuple[Path, Path]],
        targets: Sequence[Path],
        destination: Path,
        snapshots: dict[Path, Snapshot],
    ) -> list[str]:
        errors: list[str] = []
        for original, archived in reversed(moved):
            if original.exists() or original.is_symlink():
                errors.append(f"original path is occupied: {original}")
                continue
            if archived.is_symlink() or not archived.is_file():
                errors.append(f"archived path is unavailable: {archived}")
                continue
            try:
                original.touch(exist_ok=False)
                self.mover(archived, original)
                self._require_restored(original, archived, snapshots[original])
            except (OSError, ArchivingError) as exc:
                self._remove_empty_reservation(original)
                errors.append(f"cannot restore {original}: {exc}")

        errors.extend(self._cleanup_reservations(targets, destination))
        return errors

    @staticmethod
    def _require_restored(
        original: Path,
        archived: Path,
        snapshot: Snapshot,
    ) -> None:
        if archived.exists() or archived.is_symlink():
            raise ArchivingError(f"Rollback left archived input in place: {archived}")
        if original.is_symlink() or not original.is_file():
            raise ArchivingError(f"Rollback did not restore input: {original}")
        stat = original.stat()
        if (stat.st_size, stat.st_mtime_ns) != snapshot:
            raise ArchivingError(f"Restored input changed: {original}")

    @classmethod
    def _cleanup_reservations(
        cls,
        targets: Sequence[Path],
        destination: Path,
    ) -> list[str]:
        errors: list[str] = []
        for target in targets:
            if target.is_symlink():
                errors.append(f"refusing to remove symlink reservation: {target}")
                continue
            try:
                if target.is_file() and target.stat().st_size == 0:
                    target.unlink()
                elif target.exists():
                    errors.append(f"archive target remains: {target}")
            except OSError as exc:
                errors.append(f"cannot clean reservation {target}: {exc}")
        try:
            destination.rmdir()
        except FileNotFoundError:
            pass
        except OSError as exc:
            errors.append(f"cannot remove partial destination {destination}: {exc}")
        return errors

    @staticmethod
    def _remove_empty_reservation(path: Path) -> None:
        if path.is_symlink():
            return
        try:
            if path.is_file() and path.stat().st_size == 0:
                path.unlink()
        except OSError:
            pass
