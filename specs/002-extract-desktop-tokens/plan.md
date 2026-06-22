# Implementation Plan: Extract Tokens from Slack Desktop App

**Branch**: `002-extract-desktop-tokens` | **Date**: 2026-06-22 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/002-extract-desktop-tokens/spec.md`

## Summary

Add a `slack-cli extract` subcommand that reads authentication tokens (xoxc) and the session cookie (xoxd) directly from the Slack desktop app's local storage, supporting both Flatpak and standard Linux installations. The command auto-detects the installation path, extracts credentials, verifies them against the Slack API, and writes them to the config file — enabling a zero-browser authentication flow.

## Technical Context

**Language/Version**: Python 3.11+

**Primary Dependencies**: `requests` (existing), `plyvel` (new — LevelDB access), `secretstorage` (new — GNOME Keyring), `cryptography` (new — AES cookie decryption)

**Storage**: LevelDB (read-only, Slack's local storage), SQLite (read-only, Slack's cookie store), TOML (config file, via existing `write_config`)

**Testing**: pytest (existing)

**Target Platform**: Linux (Flatpak and standard installs)

**Project Type**: CLI

**Performance Goals**: Complete extraction in under 30 seconds (SC-001)

**Constraints**: LevelDB requires exclusive access (Slack must be closed). GNOME Keyring must be unlocked for cookie decryption.

**Scale/Scope**: Single-user CLI tool, 1-5 workspaces typical

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Minimal Dependencies | PASS | Three new deps (`plyvel`, `secretstorage`, `cryptography`) each provide non-trivial functionality impossible with stdlib. See [research.md](research.md) R5. |
| II. Fail Fast | PASS | All error conditions (locked DB, missing install, failed auth, no keyring) produce immediate, actionable errors. No silent fallbacks. |
| III. Separation of Concerns | PASS | Extraction logic (path detection, LevelDB reading, cookie decryption) is separated from CLI handling and config writing. |
| IV. Error Handling & Feedback | PASS | Every failure mode has a specific error message with what/why/next-step. See [cli-extract.md](contracts/cli-extract.md). |
| V. No Over-Engineering | PASS | Direct implementation: detect path, read DB, decrypt cookie, verify, write config. No plugin systems, no abstraction layers. |
| VI. Testable Code | PASS | Extraction functions accept paths as parameters (no hardcoded globals). Business logic testable without filesystem/network. |

**Post-Phase 1 re-check**: All gates still pass. Design adds no unnecessary abstraction.

## Project Structure

### Documentation (this feature)

```text
specs/002-extract-desktop-tokens/
├── plan.md              # This file
├── spec.md              # Feature specification
├── research.md          # Phase 0: technology decisions
├── data-model.md        # Phase 1: entity definitions
├── quickstart.md        # Phase 1: validation guide
├── contracts/
│   └── cli-extract.md   # Phase 1: CLI contract
└── tasks.md             # Phase 2 output (created by /speckit-tasks)
```

### Source Code (repository root)

```text
src/slack_cli/
├── commands/
│   ├── extract.py       # NEW: extract subcommand entry point
│   ├── login.py         # Existing login command
│   └── read.py          # Existing read command
├── slack_tokens.py      # NEW: token extraction from LevelDB + cookie decryption
├── cli.py               # Modified: register extract subparser
├── config.py            # Existing: write_config reused as-is
└── ...

tests/
├── unit/
│   ├── test_slack_tokens.py  # NEW: unit tests for extraction logic
│   └── ...
└── integration/
    └── ...
```

**Structure Decision**: New code follows the existing pattern — one module per command under `commands/`, with shared logic in a top-level module. The `slack_tokens.py` module encapsulates all Slack-app-specific extraction logic (path detection, LevelDB reading, cookie decryption) so it can be tested independently of the CLI layer.

## Complexity Tracking

No constitution violations to justify.
