# Project instructions

## Source of truth

- Read `docs/PROJECT.md`, `docs/WORKFLOW.md`, and `BACKLOG.md` before changing
  behavior.
- Document product decisions before implementing them.
- Ask the user when file association, destructive cleanup, or expected output
  is ambiguous; do not silently guess.

## Product constraints

- Target macOS first while keeping the Python core portable to Linux and
  Windows.
- Initial video inputs are non-recursive `.mp4` and `.mkv` files.
- Reuse valid external or embedded subtitles before invoking Whisper or a
  translation backend.
- Preserve English and Spanish SRT sidecars and package them as selectable,
  non-default VLC tracks in a new MP4.
- Preserve all audio streams and prefer English as the default when its language
  is known.
- Never destroy or overwrite source media without explicit user intent and a
  successfully verified output.
- Source deletion defaults to off. Interactive deletion requires confirmation
  after verification; automation requires an explicit `--delete-source` flag.

## Engineering constraints

- Avoid monolithic modules; split by clear responsibility after protecting
  existing behavior with characterization tests.
- Keep unit tests deterministic and offline. Replace Whisper, translation
  services, FFmpeg execution, and filesystem side effects with test doubles
  where appropriate.
- End-to-end media fixtures must be tiny and generated during tests rather than
  committed as binaries.
- Propagate failures with non-zero exit codes and actionable messages.
- Prefer cross-platform Python for core behavior; shell scripts may only be
  convenience wrappers.
- Use Conventional Commits in English.
