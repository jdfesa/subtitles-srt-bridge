"""Conservative language metadata normalization without external packages."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import unicodedata


LANGUAGE_ALIASES = {
    "ar": ("ara", "Arabic"),
    "ara": ("ara", "Arabic"),
    "arabic": ("ara", "Arabic"),
    "castellano": ("spa", "Spanish"),
    "de": ("deu", "German"),
    "deu": ("deu", "German"),
    "eng": ("eng", "English"),
    "en": ("eng", "English"),
    "english": ("eng", "English"),
    "es": ("spa", "Spanish"),
    "espanol": ("spa", "Spanish"),
    "esp": ("spa", "Spanish"),
    "fr": ("fra", "French"),
    "fra": ("fra", "French"),
    "fre": ("fra", "French"),
    "french": ("fra", "French"),
    "ger": ("deu", "German"),
    "german": ("deu", "German"),
    "ingles": ("eng", "English"),
    "it": ("ita", "Italian"),
    "ita": ("ita", "Italian"),
    "italian": ("ita", "Italian"),
    "ja": ("jpn", "Japanese"),
    "japanese": ("jpn", "Japanese"),
    "jp": ("jpn", "Japanese"),
    "jpn": ("jpn", "Japanese"),
    "por": ("por", "Portuguese"),
    "portuguese": ("por", "Portuguese"),
    "pt": ("por", "Portuguese"),
    "spa": ("spa", "Spanish"),
    "spanish": ("spa", "Spanish"),
}

SUBTITLE_QUALIFIERS = {
    "cc": "CC",
    "commentary": "Commentary",
    "forced": "Forced",
    "full": "Full",
    "hi": "Hearing Impaired",
    "sdh": "SDH",
    "signs": "Signs",
    "songs": "Songs",
}


@dataclass(frozen=True, slots=True)
class SubtitleMetadata:
    language: str
    title: str
    conflict: str | None = None


def ascii_fold(value: str) -> str:
    folded = unicodedata.normalize("NFKD", value)
    return folded.encode("ascii", "ignore").decode("ascii").casefold()


def normalize_language_code(raw_language: str | None) -> str:
    if raw_language is None:
        return "und"
    folded = ascii_fold(raw_language.strip())
    if not folded:
        return "und"
    if folded in LANGUAGE_ALIASES:
        return LANGUAGE_ALIASES[folded][0]
    if re.fullmatch(r"[a-z]{3}", folded):
        return folded
    return "und"


def is_subtitle_metadata_token(token: str) -> bool:
    folded = ascii_fold(token)
    return (
        folded in LANGUAGE_ALIASES
        or folded in SUBTITLE_QUALIFIERS
        or re.fullmatch(r"[a-z]{3}", folded) is not None
    )


def _metadata_tokens(
    path: Path,
    video_stem: str,
    subtitle_directory: str | None,
) -> list[str]:
    tokens: list[str] = []
    if subtitle_directory is not None:
        parent = ascii_fold(subtitle_directory)
        if parent.startswith("sub_"):
            tokens.extend(re.split(r"[^a-z0-9]+", parent.removeprefix("sub_")))

    subtitle_stem = path.stem
    suffix = subtitle_stem[len(video_stem) :].lstrip("._-")
    tokens.extend(re.split(r"[^a-z0-9]+", ascii_fold(suffix)))
    return [token for token in tokens if token]


def infer_subtitle_metadata(
    path: Path,
    video_stem: str,
    subtitle_directory: str | None = None,
) -> SubtitleMetadata:
    languages: list[tuple[str, str]] = []
    qualifiers: list[str] = []

    for token in _metadata_tokens(path, video_stem, subtitle_directory):
        alias = LANGUAGE_ALIASES.get(token)
        if token in SUBTITLE_QUALIFIERS:
            qualifiers.append(SUBTITLE_QUALIFIERS[token])
        elif alias is not None:
            if alias not in languages:
                languages.append(alias)
        elif re.fullmatch(r"[a-z]{3}", token):
            candidate = (token, token.upper())
            if candidate not in languages:
                languages.append(candidate)
        else:
            qualifiers.append(token.title())

    distinct_codes = {code for code, _ in languages}
    if len(distinct_codes) > 1:
        codes = ", ".join(sorted(distinct_codes))
        return SubtitleMetadata(
            "und",
            path.stem,
            f"Conflicting subtitle language metadata: {codes}",
        )
    if not languages:
        return SubtitleMetadata("und", path.stem)

    language, language_title = languages[0]
    if qualifiers:
        qualifier_title = " ".join(qualifiers)
        return SubtitleMetadata(language, f"{language_title} ({qualifier_title})")
    return SubtitleMetadata(language, language_title)
