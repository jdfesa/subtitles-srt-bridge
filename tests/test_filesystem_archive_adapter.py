import os
import tempfile
import unittest
from pathlib import Path

from subtitles_bridge.adapters.filesystem_archive import (
    TransactionalInputArchiver,
)
from subtitles_bridge.errors import (
    ArchivingCollisionError,
    ArchivingError,
    ArchivingPartialError,
)


class TransactionalInputArchiverTests(unittest.TestCase):
    def make_inputs(self):
        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        root = Path(temporary_directory.name)
        source = root / "lesson.mp4"
        source.write_bytes(b"source-video")
        first = root / "lesson.en.srt"
        first.write_text("English", encoding="utf-8")
        second = root / "sub_es" / "lesson.es.srt"
        second.parent.mkdir()
        second.write_text("Spanish", encoding="utf-8")
        destination = root / "trash" / "lesson"
        return root, source, (first, second), destination

    def test_moves_sidecars_before_source_and_returns_exact_receipt(self):
        _, source, sidecars, destination = self.make_inputs()
        calls = []

        def recording_move(original, archived):
            calls.append((original, archived))
            os.replace(original, archived)

        receipt = TransactionalInputArchiver(recording_move).archive(
            source,
            sidecars,
            destination,
        )

        self.assertEqual(
            [original for original, _ in calls],
            [*sidecars, source],
        )
        self.assertEqual(receipt.original_paths, (source, *sidecars))
        self.assertEqual(
            receipt.archived_paths,
            tuple(destination / path.name for path in (source, *sidecars)),
        )
        self.assertTrue(all(path.is_file() for path in receipt.archived_paths))
        self.assertFalse(any(path.exists() for path in receipt.original_paths))

    def test_archives_only_the_source_when_no_sidecar_was_incorporated(self):
        _, source, sidecars, destination = self.make_inputs()

        receipt = TransactionalInputArchiver().archive(
            source,
            (),
            destination,
        )

        self.assertEqual(receipt.original_paths, (source,))
        self.assertEqual(receipt.archived_paths, (destination / source.name,))
        self.assertTrue(receipt.archived_paths[0].is_file())
        self.assertTrue(all(path.is_file() for path in sidecars))

    def test_rejects_collisions_and_unsafe_routes_before_moving(self):
        root, source, sidecars, destination = self.make_inputs()
        destination.mkdir(parents=True)
        keeper = destination / "keep.txt"
        keeper.write_text("keep", encoding="utf-8")

        with self.assertRaisesRegex(
            ArchivingCollisionError,
            "already exists",
        ):
            TransactionalInputArchiver().archive(source, sidecars, destination)
        self.assertEqual(keeper.read_text(encoding="utf-8"), "keep")
        self.assertTrue(source.exists())
        self.assertTrue(all(path.exists() for path in sidecars))

        other = root / "other" / "LESSON.EN.SRT"
        other.parent.mkdir()
        other.write_text("duplicate", encoding="utf-8")
        fresh_destination = root / "trash" / "other"
        with self.assertRaisesRegex(
            ArchivingCollisionError,
            "share a destination filename",
        ):
            TransactionalInputArchiver().archive(
                source,
                (sidecars[0], other),
                fresh_destination,
            )
        self.assertFalse(fresh_destination.exists())

    def test_rejects_missing_empty_non_srt_and_symlink_inputs(self):
        root, source, sidecars, destination = self.make_inputs()
        invalid_cases = []

        missing = root / "missing.srt"
        invalid_cases.append(((missing,), "missing"))

        empty = root / "empty.srt"
        empty.touch()
        invalid_cases.append(((empty,), "empty"))

        wrong_extension = root / "notes.txt"
        wrong_extension.write_text("notes", encoding="utf-8")
        invalid_cases.append(((wrong_extension,), "must use .srt"))

        symlink = root / "linked.srt"
        symlink.symlink_to(sidecars[0])
        invalid_cases.append(((symlink,), "symlink"))

        for candidates, message in invalid_cases:
            with self.subTest(message=message):
                with self.assertRaisesRegex(ArchivingError, message):
                    TransactionalInputArchiver().archive(
                        source,
                        candidates,
                        destination,
                    )
                self.assertFalse(destination.exists())
                self.assertTrue(source.exists())

    def test_rolls_back_an_interrupted_move_and_allows_retry(self):
        _, source, sidecars, destination = self.make_inputs()
        calls = 0

        def fail_once(original, archived):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("injected move failure")
            os.replace(original, archived)

        with self.assertRaisesRegex(ArchivingError, "all moved inputs were restored"):
            TransactionalInputArchiver(fail_once).archive(
                source,
                sidecars,
                destination,
            )

        self.assertTrue(source.is_file())
        self.assertTrue(all(path.is_file() for path in sidecars))
        self.assertFalse(destination.exists())

        receipt = TransactionalInputArchiver().archive(
            source,
            sidecars,
            destination,
        )
        self.assertTrue(all(path.is_file() for path in receipt.archived_paths))

    def test_preserves_partial_destination_when_rollback_also_fails(self):
        _, source, sidecars, destination = self.make_inputs()
        calls = 0

        def fail_move_and_rollback(original, archived):
            nonlocal calls
            calls += 1
            if calls in {2, 3}:
                raise OSError(f"injected failure #{calls}")
            os.replace(original, archived)

        with self.assertRaisesRegex(
            ArchivingPartialError,
            "rollback was incomplete",
        ):
            TransactionalInputArchiver(fail_move_and_rollback).archive(
                source,
                sidecars,
                destination,
            )

        self.assertTrue(source.is_file())
        self.assertFalse(sidecars[0].exists())
        self.assertTrue(sidecars[1].is_file())
        self.assertEqual(
            (destination / sidecars[0].name).read_text(encoding="utf-8"),
            "English",
        )


if __name__ == "__main__":
    unittest.main()
