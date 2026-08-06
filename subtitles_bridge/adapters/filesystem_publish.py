"""Exclusive atomic publication of a verified staged MKV."""

from __future__ import annotations

from collections.abc import Callable
import os
from pathlib import Path

from ..errors import PublicationCollisionError, PublicationError


Replacer = Callable[[Path, Path], None]


class AtomicOutputPublisher:
    def __init__(self, replacer: Replacer = os.replace) -> None:
        self.replacer = replacer

    def publish(self, staged_output: Path, final_output: Path) -> None:
        if staged_output.resolve() == final_output.resolve():
            raise PublicationError("Staged and final output paths must differ")
        if staged_output.is_symlink():
            raise PublicationError(
                f"Verified staged output cannot be a symlink: {staged_output}"
            )
        try:
            if not staged_output.is_file() or staged_output.stat().st_size == 0:
                raise PublicationError(
                    f"Verified staged output is missing or empty: {staged_output}"
                )
        except OSError as exc:
            raise PublicationError(
                f"Cannot inspect verified staged output {staged_output}: {exc}"
            ) from exc
        if final_output.suffix.casefold() != ".mkv":
            raise PublicationError(f"Final output must use .mkv: {final_output}")

        output_directory = final_output.parent
        if output_directory.is_symlink() or (
            output_directory.exists() and not output_directory.is_dir()
        ):
            raise PublicationCollisionError(
                f"Output path is not a safe directory: {output_directory}"
            )
        try:
            output_directory.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise PublicationError(
                f"Cannot create output directory {output_directory}: {exc}"
            ) from exc

        if final_output.exists() or final_output.is_symlink():
            raise PublicationCollisionError(
                f"Final output already exists: {final_output}"
            )
        try:
            final_output.touch(exist_ok=False)
        except FileExistsError as exc:
            raise PublicationCollisionError(
                f"Final output already exists: {final_output}"
            ) from exc
        except OSError as exc:
            raise PublicationError(
                f"Cannot reserve final output {final_output}: {exc}"
            ) from exc

        try:
            self.replacer(staged_output, final_output)
        except OSError as exc:
            cleanup_error = self._remove_reservation(final_output)
            message = f"Cannot atomically publish {staged_output}: {exc}"
            if cleanup_error is not None:
                message += f"; output reservation cleanup also failed: {cleanup_error}"
            raise PublicationError(message) from exc

    @staticmethod
    def _remove_reservation(path: Path) -> str | None:
        try:
            path.unlink(missing_ok=True)
        except OSError as exc:
            return f"{path}: {exc}"
        return None
