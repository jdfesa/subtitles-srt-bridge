import os
from pathlib import Path
import tempfile
import unittest

from subtitles_bridge.errors import InputPathError, SourceVideoError
from subtitles_bridge.paths import WorkspacePaths


class WorkspacePathsTests(unittest.TestCase):
    def test_resolves_workspace_independently_of_repository_cwd(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            workspace = root / "media"
            elsewhere = root / "elsewhere"
            workspace.mkdir()
            elsewhere.mkdir()

            original_directory = Path.cwd()
            try:
                os.chdir(elsewhere)
                paths = WorkspacePaths.from_directory(workspace)
            finally:
                os.chdir(original_directory)

        self.assertEqual(paths.root, workspace.resolve())

    def test_rejects_missing_directory_and_regular_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            regular_file = root / "not-a-directory"
            regular_file.touch()

            with self.assertRaisesRegex(InputPathError, "does not exist"):
                WorkspacePaths.from_directory(root / "missing")
            with self.assertRaisesRegex(InputPathError, "not a directory"):
                WorkspacePaths.from_directory(regular_file)

    def test_derives_output_and_trash_paths_without_creating_them(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            video = root / "Lesson.01.MP4"
            video.touch()
            paths = WorkspacePaths.from_directory(root)

            output = paths.output_for(video)
            trash = paths.trash_for(video)

            self.assertEqual(
                output,
                paths.root / "output" / "Lesson.01.subtitled.mkv",
            )
            self.assertEqual(trash, paths.root / "trash" / "Lesson.01")
            self.assertFalse(paths.output_directory.exists())
            self.assertFalse(paths.trash_directory.exists())

    def test_accepts_mkv_source_in_workspace_root(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            video = root / "lesson.mkv"
            video.touch()
            paths = WorkspacePaths.from_directory(root)

            source = paths.source_video(video)

        self.assertEqual(source, video.resolve())

    def test_rejects_nested_source(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            nested = root / "nested"
            nested.mkdir()
            video = nested / "lesson.mkv"
            video.touch()
            paths = WorkspacePaths.from_directory(root)

            with self.assertRaisesRegex(SourceVideoError, "directly inside"):
                paths.source_video(video)

    def test_rejects_unsupported_source_extension(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            video = root / "lesson.mov"
            video.touch()
            paths = WorkspacePaths.from_directory(root)

            with self.assertRaisesRegex(SourceVideoError, "Unsupported"):
                paths.source_video(video)

    def test_rejects_missing_source_and_directory_candidate(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            directory_candidate = root / "lesson.mkv"
            directory_candidate.mkdir()
            paths = WorkspacePaths.from_directory(root)

            with self.assertRaisesRegex(SourceVideoError, "does not exist"):
                paths.source_video(root / "missing.mkv")
            with self.assertRaisesRegex(SourceVideoError, "not a file"):
                paths.source_video(directory_candidate)


if __name__ == "__main__":
    unittest.main()
