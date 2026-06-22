# Tasks: Extract Tokens from Slack Desktop App

**Input**: Design documents from `specs/002-extract-desktop-tokens/`

**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md, data-model.md, contracts/

**Tests**: Not explicitly requested in the spec — test tasks are omitted.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Phase 1: Setup

**Purpose**: Add new dependencies and create module scaffolding

- [x] T001 Add `plyvel`, `secretstorage`, and `cryptography` to `dependencies` in `pyproject.toml`
- [x] T002 Create empty module `src/slack_cli/slack_tokens.py` with docstring describing its purpose (token extraction from Slack desktop app local storage)
- [x] T003 Create empty module `src/slack_cli/commands/extract.py` with docstring describing its purpose (extract subcommand entry point)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core extraction logic that all user stories depend on

**Note**: User Story 1 (browser cookie login) is already implemented. The foundational work here supports User Stories 2–4.

- [x] T004 Implement `find_slack_installation(search_paths)` in `src/slack_cli/slack_tokens.py` — accepts a list of `(base_path, source_label)` tuples, returns the first where `Local Storage/leveldb` subdirectory exists, or raises an error listing all searched paths. Default search order: Flatpak (`~/.var/app/com.slack.Slack/config/Slack/`) first, then standard (`~/.config/Slack/`).
- [x] T005 Implement `extract_tokens(leveldb_path)` in `src/slack_cli/slack_tokens.py` — opens the LevelDB database via `plyvel`, finds the `localConfig_v2` key, parses it with the `_parse_local_config` logic (port from `external/slacktokens/slacktokens.py`), and returns a list of `WorkspaceToken` dicts (`url`, `name`, `token`). Raises a clear error if the DB is locked (Slack is running) or if no `localConfig_v2` key is found.
- [x] T006 Implement `decrypt_cookie(cookies_path)` in `src/slack_cli/slack_tokens.py` — reads the `Cookies` SQLite database, queries the `d` cookie for `.slack.com`, retrieves the "Slack Safe Storage" password from GNOME Keyring via `secretstorage`, derives the AES key via PBKDF2, decrypts the `v11`-encrypted value, and returns the plaintext cookie string. Raises a clear error if the keyring is locked or the cookie is not found.

**Checkpoint**: Core extraction functions are ready — user story phases can begin.

---

## Phase 3: User Story 2 — Extract tokens from Flatpak Slack and update config (Priority: P1) :dart: MVP

**Goal**: User runs `slack-cli extract` and gets a working config from their Flatpak Slack installation without touching a browser.

**Independent Test**: Run `slack-cli extract` with Flatpak Slack closed → config file is written → `slack-cli read` works with a valid Slack link.

### Implementation for User Story 2

- [x] T007 [US2] Register the `extract` subparser in `src/slack_cli/cli.py` — add `extract` subcommand with `--list` flag, following the existing pattern for `login` and `read`. Wire it to call `extract.run(args, config)`.
- [x] T008 [US2] Implement `run(args, config)` in `src/slack_cli/commands/extract.py` — orchestrate the full flow: call `find_slack_installation()` with default paths, call `extract_tokens()`, call `decrypt_cookie()`, select workspace (auto-select if one, prompt if multiple via `input()`), verify via `SlackAPI.call("auth.test")`, and write config via `write_config()`. Print progress messages to stdout and errors to stderr. Follow the error message patterns from `contracts/cli-extract.md`.
- [x] T009 [US2] Implement workspace selection logic in `src/slack_cli/commands/extract.py` — when one workspace: auto-select and print its name. When multiple: print numbered list, prompt with `input()`, validate selection, and return the chosen workspace.

**Checkpoint**: `slack-cli extract` works end-to-end for Flatpak Slack installations.

---

## Phase 4: User Story 3 — Extract tokens from standard Linux Slack install (Priority: P2)

**Goal**: Same extraction flow works for standard Linux Slack installations at `~/.config/Slack/`.

**Independent Test**: Run `slack-cli extract` on a system with standard Slack install → tokens extracted and config written identically to Flatpak flow.

### Implementation for User Story 3

- [x] T010 [US3] Verify and adjust `find_slack_installation()` in `src/slack_cli/slack_tokens.py` — ensure standard path `~/.config/Slack/` is in the default search list (it should already be from T004). Verify cookie path resolution works for both Flatpak and standard layouts. No code change expected if T004 was implemented correctly; this task is a validation pass.
- [x] T011 [US3] Verify error message when neither Flatpak nor standard installation exists — run with no Slack data dirs present and confirm the error lists both searched paths per `contracts/cli-extract.md`.

**Checkpoint**: `slack-cli extract` works for both Flatpak and standard installations.

---

## Phase 5: User Story 4 — List available workspaces without writing config (Priority: P3)

**Goal**: User can discover which workspaces are available without modifying any files.

**Independent Test**: Run `slack-cli extract --list` → workspace names and URLs printed to stdout, no files modified.

### Implementation for User Story 4

- [x] T012 [US4] Implement `--list` mode in `src/slack_cli/commands/extract.py` — when `args.list` is true, find installation, extract tokens, print workspace names and URLs to stdout, then exit without calling `decrypt_cookie()`, `auth.test`, or `write_config()`.

**Checkpoint**: `slack-cli extract --list` works independently.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Documentation and final validation

- [x] T013 [P] Update `README.md` — add documentation for the `slack-cli extract` command under the Authentication section, including usage examples for default mode and `--list` mode.
- [x] T014 Run all quickstart.md validation scenarios manually to confirm end-to-end behavior.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion — BLOCKS all user stories
- **User Story 2 (Phase 3)**: Depends on Foundational phase — MVP
- **User Story 3 (Phase 4)**: Depends on Foundational phase — can start after Phase 2 (parallel with US2 in theory, but shares files)
- **User Story 4 (Phase 5)**: Depends on Phase 3 (reuses `run()` with `--list` branch)
- **Polish (Phase 6)**: Depends on all user story phases

### User Story Dependencies

- **User Story 1 (P1)**: Already implemented — no tasks needed
- **User Story 2 (P1)**: Depends on Foundational (Phase 2) — no dependency on other stories
- **User Story 3 (P2)**: Depends on Foundational (Phase 2) — validation of US2 implementation for standard paths
- **User Story 4 (P3)**: Depends on US2 (Phase 3) — adds `--list` branch to existing `run()` function

### Within Each User Story

- Core extraction logic (Phase 2) before CLI wiring (Phase 3+)
- CLI registration (T007) before command implementation (T008)
- Command implementation (T008) before selection logic (T009)

### Parallel Opportunities

- T002 and T003 can run in parallel (different files)
- T004, T005, and T006 can each be developed independently (different functions in same file, but no dependencies between them)
- T013 can run in parallel with T014

---

## Parallel Example: Foundational Phase

```
# These three functions have no dependencies on each other:
Task T004: "Implement find_slack_installation() in src/slack_cli/slack_tokens.py"
Task T005: "Implement extract_tokens() in src/slack_cli/slack_tokens.py"
Task T006: "Implement decrypt_cookie() in src/slack_cli/slack_tokens.py"
```

---

## Implementation Strategy

### MVP First (User Story 2 Only)

1. Complete Phase 1: Setup (T001–T003)
2. Complete Phase 2: Foundational (T004–T006)
3. Complete Phase 3: User Story 2 (T007–T009)
4. **STOP and VALIDATE**: Run `slack-cli extract` with Flatpak Slack
5. Confirm extracted tokens work with `slack-cli read`

### Incremental Delivery

1. Setup + Foundational → Core extraction ready
2. User Story 2 → Flatpak extraction works → MVP!
3. User Story 3 → Standard Linux path validated
4. User Story 4 → `--list` mode added
5. Polish → README updated, full validation

---

## Notes

- User Story 1 (browser cookie login) is already implemented — no tasks generated for it
- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Commit after each task or logical group
- Stop at any checkpoint to validate story independently
