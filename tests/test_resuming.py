from pathlib import Path
import tempfile
import unittest

from subtitles_bridge.errors import VerificationError
from subtitles_bridge.integrity import subtitle_sha256
from subtitles_bridge.models import (
    ArtifactState,
    DiscoveryResult,
    MediaInspection,
    MediaStream,
    StreamKind,
    SubtitleArtifact,
    SubtitleOrigin,
    VerifiedOutput,
    VideoInventory,
)
from subtitles_bridge.paths import WorkspacePaths
from subtitles_bridge.resuming import ExistingOutputResumer
from subtitles_bridge.srt import SrtValidator


class RecordingVerifier:
    def __init__(self):
        self.calls = []

    def verify(self, inventory, output, expected_subtitles):
        expected_subtitles = tuple(expected_subtitles)
        self.calls.append((inventory, output, expected_subtitles))
        inspection = MediaInspection(
            (MediaStream(0, StreamKind.VIDEO, "h264"),),
            "matroska",
        )
        return VerifiedOutput(
            inventory.source,
            output,
            inspection,
            expected_subtitles,
            output.stat().st_size,
            output.stat().st_mtime_ns,
        )


class ExistingOutputResumerTests(unittest.TestCase):
    def test_reverifies_existing_output_with_discovered_subtitles(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "lesson.mp4"
            sidecar = root / "lesson.en.srt"
            output = root / "output" / "lesson.subtitled.mkv"
            source.write_bytes(b"source")
            sidecar.write_text(
                "1\n00:00:00,000 --> 00:00:01,000\nHello\n",
                encoding="utf-8",
            )
            output.parent.mkdir()
            output.write_bytes(b"output")
            validation = SrtValidator().validate(sidecar)
            subtitle = SubtitleArtifact(
                SubtitleOrigin.EXTERNAL,
                ArtifactState.VALID,
                language="eng",
                path=sidecar,
                validation=validation,
            )
            inventory = VideoInventory(
                source.resolve(),
                subtitles=(subtitle,),
                existing_output=output,
            )
            verifier = RecordingVerifier()
            resumer = ExistingOutputResumer(verifier, SrtValidator())

            proofs = resumer.verify(
                DiscoveryResult((inventory,)),
                WorkspacePaths.from_directory(root),
            )

        self.assertEqual(verifier.calls[0][2], (subtitle,))
        self.assertEqual(proofs[0].final_path, output)
        self.assertEqual(proofs[0].expected_subtitles, (subtitle,))

    def test_uses_valid_staged_generated_subtitle_as_resume_proof(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "lesson.mkv"
            output = root / "output" / "lesson.subtitled.mkv"
            generated = root / "staging" / "lesson.generated.eng.srt"
            source.write_bytes(b"source")
            output.parent.mkdir()
            output.write_bytes(b"output")
            generated.parent.mkdir()
            generated.write_text(
                "1\n00:00:00,000 --> 00:00:01,000\nHello\n",
                encoding="utf-8",
            )
            generated_hash = subtitle_sha256(generated)
            inventory = VideoInventory(
                source.resolve(),
                existing_output=output,
            )
            verifier = RecordingVerifier()
            resumer = ExistingOutputResumer(verifier, SrtValidator())

            proof = resumer.verify(
                DiscoveryResult((inventory,)),
                WorkspacePaths.from_directory(root),
            )[0]

        subtitle = proof.expected_subtitles[0]
        self.assertEqual(subtitle.origin, SubtitleOrigin.GENERATED)
        self.assertEqual(subtitle.path, generated.resolve())
        self.assertEqual(subtitle.language, "eng")
        self.assertEqual(subtitle.title, "Whisper transcription (eng)")
        self.assertEqual(subtitle.content_sha256, generated_hash)

    def test_refuses_generated_resume_without_staged_sidecar(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "lesson.mkv"
            output = root / "output" / "lesson.subtitled.mkv"
            source.write_bytes(b"source")
            output.parent.mkdir()
            output.write_bytes(b"output")
            inventory = VideoInventory(
                source.resolve(),
                existing_output=output,
            )
            resumer = ExistingOutputResumer(RecordingVerifier(), SrtValidator())

            with self.assertRaisesRegex(
                VerificationError,
                "without the generated subtitle proof",
            ):
                resumer.verify(
                    DiscoveryResult((inventory,)),
                    WorkspacePaths.from_directory(root),
                )


if __name__ == "__main__":
    unittest.main()
