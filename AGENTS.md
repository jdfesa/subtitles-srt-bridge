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
- Reuse every valid associated external or embedded subtitle, regardless of
  language.
- Invoke Whisper only when no valid subtitle exists, and generate one subtitle
  in the spoken language; do not translate merely to complete a language pair.
- Produce a new MKV with selectable, non-default subtitle tracks.
- Copy every source stream without compression, transcoding, silent removal, or
  changes to audio dispositions.
- Stage and verify the complete output before publishing it.
- After successful verification, automatically move the original and only the
  sidecars actually integrated into `trash/<video>/`.
- Treat `trash/` as reversible quarantine: never empty it, permanently delete
  its contents, or overwrite an existing path.
- Leave ambiguous, invalid, and unused files untouched.

## Engineering constraints

- Avoid monolithic modules; split by clear responsibility after protecting
  existing behavior with characterization tests.
- Implement the agreed workflow in small, independently validated phases.
- Keep unit tests deterministic and offline. Replace Whisper, translation
  services, FFmpeg execution, and filesystem side effects with test doubles
  where appropriate.
- End-to-end media fixtures must be tiny and generated during tests rather than
  committed as binaries.
- Propagate failures with non-zero exit codes and actionable messages.
- Prefer cross-platform Python for core behavior; shell scripts may be setup or
  convenience wrappers but must not contain the only implementation.
- Use Conventional Commits in English.
