"""Read-only reconstruction of proof for safely resumed published outputs."""

from __future__ import annotations

from .errors import VerificationError
from .models import DiscoveryResult, PublishedOutput
from .paths import WorkspacePaths
from .ports import OutputVerifier, SubtitleValidator
from .transcription import find_existing_generated_subtitle


class ExistingOutputResumer:
    def __init__(
        self,
        verifier: OutputVerifier,
        validator: SubtitleValidator,
    ) -> None:
        self.verifier = verifier
        self.validator = validator

    def verify(
        self,
        discovery: DiscoveryResult,
        paths: WorkspacePaths,
    ) -> tuple[PublishedOutput, ...]:
        proofs = []
        for inventory in discovery.inventories:
            existing_output = inventory.existing_output
            if existing_output is None:
                continue

            expected_subtitles = inventory.valid_subtitles
            if not expected_subtitles:
                generated = find_existing_generated_subtitle(
                    paths.generated_subtitle_target(inventory.source),
                    self.validator,
                )
                if generated is None:
                    raise VerificationError(
                        "Cannot resume published output without the generated "
                        f"subtitle proof for {inventory.source}"
                    )
                expected_subtitles = (generated,)

            verified = self.verifier.verify(
                inventory,
                existing_output,
                expected_subtitles,
            )
            proofs.append(
                PublishedOutput(
                    source=verified.source,
                    final_path=verified.staged_path,
                    inspection=verified.inspection,
                    expected_subtitles=verified.expected_subtitles,
                    size_bytes=verified.size_bytes,
                    modified_time_ns=verified.modified_time_ns,
                )
            )
        return tuple(proofs)
