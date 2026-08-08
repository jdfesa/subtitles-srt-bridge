import tempfile
import unittest
from pathlib import Path

from subtitles_bridge.adapters.filesystem_publish import AtomicOutputPublisher
from subtitles_bridge.errors import PublicationCollisionError, PublicationError


class AtomicOutputPublisherTests(unittest.TestCase):
    def make_paths(self):
        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        root = Path(temporary_directory.name)
        staged = root / "staging" / "lesson.subtitled.mkv"
        staged.parent.mkdir()
        staged.write_bytes(b"verified-output")
        final = root / "output" / "lesson.subtitled.mkv"
        return root, staged, final

    def test_atomically_moves_staged_output_to_an_exclusive_destination(self):
        _, staged, final = self.make_paths()

        AtomicOutputPublisher().publish(staged, final)

        self.assertFalse(staged.exists())
        self.assertEqual(final.read_bytes(), b"verified-output")

    def test_rejects_existing_or_unsafe_output_routes_without_overwrite(self):
        root, staged, final = self.make_paths()
        final.parent.mkdir()
        final.write_bytes(b"existing")

        with self.assertRaisesRegex(PublicationCollisionError, "already exists"):
            AtomicOutputPublisher().publish(staged, final)
        self.assertEqual(final.read_bytes(), b"existing")
        self.assertEqual(staged.read_bytes(), b"verified-output")

        final.unlink()
        final.parent.rmdir()
        final.parent.write_bytes(b"not-a-directory")
        with self.assertRaisesRegex(PublicationCollisionError, "safe directory"):
            AtomicOutputPublisher().publish(staged, final)
        self.assertEqual(root.joinpath("output").read_bytes(), b"not-a-directory")
        self.assertEqual(staged.read_bytes(), b"verified-output")

    def test_cleans_only_its_reservation_when_atomic_move_fails(self):
        _, staged, final = self.make_paths()
        calls = []

        def failing_replace(source, destination):
            calls.append((source, destination, destination.read_bytes()))
            raise OSError("cross-device move")

        with self.assertRaisesRegex(PublicationError, "cross-device move"):
            AtomicOutputPublisher(replacer=failing_replace).publish(staged, final)

        self.assertEqual(calls, [(staged, final, b"")])
        self.assertEqual(staged.read_bytes(), b"verified-output")
        self.assertFalse(final.exists())

    def test_rejects_missing_empty_or_symlinked_staging(self):
        root, staged, final = self.make_paths()
        staged.unlink()
        with self.assertRaisesRegex(PublicationError, "missing or empty"):
            AtomicOutputPublisher().publish(staged, final)

        staged.touch()
        with self.assertRaisesRegex(PublicationError, "missing or empty"):
            AtomicOutputPublisher().publish(staged, final)

        staged.unlink()
        target = root / "other.mkv"
        target.write_bytes(b"other")
        staged.symlink_to(target)
        with self.assertRaisesRegex(PublicationError, "symlink"):
            AtomicOutputPublisher().publish(staged, final)


if __name__ == "__main__":
    unittest.main()
