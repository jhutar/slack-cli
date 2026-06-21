# Tasks: Slack Link Reader

**Input**: Design documents from `specs/001-slack-link-reader/`

**Prerequisites**: plan.md (required), spec.md (required), research.md, data-model.md, contracts/cli-interface.md

**Tests**: Test tasks are included for core pure-logic modules (link parser, mrkdwn converter, formatter, config, cache) where unit tests provide high value with low cost.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

---

## Phase 1: Setup (Repository Scaffolding)

**Purpose**: Project initialization with build tooling, linting, and testing infrastructure. Follows the pattern from `external/jira_query/`.

- [x] T001 Create `pyproject.toml` with hatchling build backend, `src/slack_cli` package, `slack-cli = "slack_cli.__main__:main"` entry point, `requires-python = ">=3.11"`, `requests` runtime dependency, and `pytest` dev dependency
- [x] T002 Create `Makefile` with targets: `help` (default), `bootstrap` (install Python 3.11 via uv + pre-commit), `test` (PYTHONPATH=src pytest -v), `check` (pre-commit on staged), `check-all` (pre-commit on all files)
- [x] T003 [P] Create `.pre-commit-config.yaml` with hook types `pre-commit, commit-msg`: pre-commit-hooks (check-yaml, end-of-file-fixer, trailing-whitespace, detect-private-key, check-added-large-files, check-merge-conflict, check-json, mixed-line-ending), ruff-pre-commit (ruff with --fix, ruff-format), bandit (skip B101), gitleaks, shellcheck-py
- [x] T004 [P] Extend `.gitignore` with Python patterns: `__pycache__/`, `*.pyc`, `*.egg-info/`, `dist/`, `build/`, `.eggs/`, `.pytest_cache/`, `.ruff_cache/`, `*.egg`, `.venv/`
- [x] T005 Create `src/slack_cli/__init__.py` with `__version__ = "0.1.0"`
- [x] T006 Create `src/slack_cli/__main__.py` with stub `main()` function that sets up argparse with `read` subcommand placeholder, `--help`, `--version`, `--config`, `--log-level` global options, and prints help if no subcommand given
- [x] T007 [P] Create `tests/test_placeholder.py` with a single passing test to verify pytest setup works

**Checkpoint**: `make bootstrap` succeeds, `make test` passes, `make check-all` passes, `pip install -e .` works, `slack-cli --help` shows output.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure modules that ALL user stories depend on

**CRITICAL**: No user story work can begin until this phase is complete

- [x] T008 Implement config loader in `src/slack_cli/config.py`: load TOML from `~/.config/slack-cli/config.toml` (or `--config` path) via stdlib `tomllib`, merge with env vars (`SLACK_CLI_XOXC_TOKEN`, `SLACK_CLI_XOXD_TOKEN`, `SLACK_CLI_USER_AGENT`), enforce precedence (CLI args > env > config file > defaults), return a config dict. Fail fast with clear error if config file exists but is malformed TOML.
- [x] T009 [P] Implement logging setup in `src/slack_cli/log.py`: configure stdlib `logging` with two handlers — stderr handler at configurable level (default WARNING, format `%(levelname)s: %(message)s`) and file handler always at DEBUG level to `~/.cache/slack-cli/debug.log` (format `%(asctime)s %(levelname)s %(name)s: %(message)s`). Create cache directory if it does not exist.
- [x] T010 Implement Slack API client in `src/slack_cli/api.py`: `SlackAPI` class that accepts xoxc token, xoxd token, and optional user_agent. Methods: `call(method, params)` that POSTs to `https://slack.com/api/{method}` with `Authorization: Bearer {xoxc}` header, `Cookie: d={xoxd}`, optional `User-Agent`, and form-encoded `params`. Check response JSON `ok` field — if false, raise a typed error with Slack's error string. Handle HTTP errors and rate limiting (Retry-After header) with up to 3 retries. Log all API calls at DEBUG level.
- [x] T011 [P] Implement link parser in `src/slack_cli/link.py`: `parse_slack_link(url)` function that parses `https://<workspace>.slack.com/archives/<channel_id>/p<timestamp>[?thread_ts=<ts>&cid=<cid>]`, returns a `SlackLink` dataclass (workspace, channel_id, message_ts, thread_ts, is_thread, is_reply per data-model.md). Convert `p`-prefixed timestamp by removing `p` and inserting dot before last 6 digits. Raise `ValueError` with clear message for invalid URLs.
- [x] T012 [P] Implement user/channel cache in `src/slack_cli/cache.py`: read/write JSON cache files at `~/.cache/slack-cli/users.json` and `channels.json` per format in data-model.md. Functions: `load_cache(path, ttl)` returns cached dict or None if expired/missing, `save_cache(path, data)` writes atomically (write to temp file then rename). `resolve_user(api, user_id, cache)` fetches from cache or calls `users.info` API and updates cache. `resolve_channel(api, channel_id, cache)` same for `conversations.info`.

**Checkpoint**: All foundational modules importable, config loads from file and env, logging writes to stderr and file, API client can be instantiated, link parser handles valid/invalid URLs, cache reads/writes JSON files.

---

## Phase 3: User Story 1 - Fetch a single channel message by link (Priority: P1) MVP

**Goal**: User provides a Slack channel message link and sees the message content (with thread replies if present) as Markdown on stdout.

**Independent Test**: `slack-cli read '<channel-message-link>'` outputs Markdown with author, timestamp, content. If message has thread replies, they are included.

### Tests for User Story 1

- [x] T013 [P] [US1] Unit tests for link parser in `tests/unit/test_link.py`: valid channel link, link with thread_ts, link with reply (thread_ts != message_ts), invalid URL, missing parts, DM link prefix detection
- [x] T014 [P] [US1] Unit tests for mrkdwn converter in `tests/unit/test_mrkdwn.py`: bold, italic, strikethrough, inline code (no conversion), fenced code blocks (no conversion inside), links with display text, bare links, user mentions with mock map, channel refs, special mentions (@channel/@here/@everyone), HTML entity decoding, mixed formatting, code blocks containing mrkdwn that should not be converted
- [x] T015 [P] [US1] Unit tests for formatter in `tests/unit/test_formatter.py`: single message output format (heading with @author and timestamp, content, separator), message with file attachment placeholder, thread output with sub-numbering (parent as N, replies as N.1, N.2)
- [x] T016 [P] [US1] Unit tests for config loader in `tests/unit/test_config.py`: load from TOML file, env var override, missing file (use defaults), malformed TOML error, missing required tokens error
- [x] T017 [P] [US1] Unit tests for cache in `tests/unit/test_cache.py`: load valid cache, load expired cache returns None, save and reload cache, resolve user with cache hit, resolve user with cache miss (mock API)

### Implementation for User Story 1

- [x] T018 [P] [US1] Implement mrkdwn-to-Markdown converter in `src/slack_cli/mrkdwn.py`: `convert(text, user_map, channel_map)` pure function that applies the conversion pipeline from plan.md — resolve mentions, convert links, convert bold/italic/strikethrough, decode HTML entities. Must skip conversions inside code blocks and inline code spans.
- [x] T019 [US1] Implement message formatter in `src/slack_cli/formatter.py`: `format_messages(messages)` function that takes a list of Message objects (from data-model.md) and returns a Markdown string per contracts/cli-interface.md output format — heading `### @username (YYYY-MM-DD HH:MM UTC)`, message content, `---` separator. For messages with thread replies, use `####` headings with sub-numbering (N.1, N.2). For file attachments with no text, output `[Attachment: filename]`.
- [x] T020 [US1] Implement read subcommand in `src/slack_cli/commands/read.py` and `src/slack_cli/commands/__init__.py`: orchestrate the main flow — parse link, validate auth tokens (fail fast with exit code 2 if missing), create API client, fetch message via `conversations.history` (oldest=ts, latest=ts, inclusive=true, limit=1), check if message has `reply_count > 0` and if so fetch thread via `conversations.replies`, resolve user mentions and channel refs via cache, convert mrkdwn, format output, print to stdout.
- [x] T021 [US1] Wire full CLI in `src/slack_cli/cli.py`: build argparse with global options (`--config`, `--log-level`, `--version`) and `read` subcommand with positional `slack-link` argument and `--after` option. Connect to `commands.read` handler. Update `src/slack_cli/__main__.py` to call `cli.main()`.

**Checkpoint**: `slack-cli read '<channel-link>'` outputs the message as Markdown. If the message has thread replies, the full thread is displayed. Invalid links and missing tokens produce clear errors. `make test` passes all unit tests.

---

## Phase 4: User Story 2 - Fetch a thread by link (Priority: P1)

**Goal**: User provides a thread link (URL with `thread_ts`) and sees the full thread or just the specific reply.

**Independent Test**: `slack-cli read '<thread-link>'` outputs full thread. Link to a specific reply outputs only that reply. Thread with 50+ replies includes all.

### Implementation for User Story 2

- [x] T022 [US2] Extend read command in `src/slack_cli/commands/read.py` to handle thread links: if `SlackLink.is_thread` and not `is_reply`, fetch full thread via `conversations.replies` with parent's thread_ts. If `is_reply`, fetch single message via `conversations.history` (oldest=message_ts, inclusive=true, limit=1) and output only that reply.
- [x] T023 [US2] Add pagination support to API client in `src/slack_cli/api.py`: add `call_paginated(method, params, key)` method that follows Slack's cursor-based pagination (`response_metadata.next_cursor`) and collects all results. Use for `conversations.replies` to handle threads with 50+ replies.
- [x] T024 [US2] Add integration test in `tests/integration/test_read_command.py`: test the full read command flow with mocked API responses for channel message, thread link, reply link, and long thread (paginated). Use `unittest.mock.patch` on `requests.post` to return canned Slack API JSON responses.

**Checkpoint**: Thread links show full thread. Reply links show single reply. Long threads are fully paginated. Integration test passes with mocked API.

---

## Phase 5: User Story 3 - Fetch follow-up messages (Priority: P2)

**Goal**: User provides a channel message link with `--after N` (count) or `--after 2H` (duration) and sees the linked message plus follow-up messages with inline threads.

**Independent Test**: `slack-cli read --after 5 '<link>'` outputs linked message plus next 5 channel messages. `--after 2H` outputs messages within 2-hour window. Threads among follow-ups are inlined.

### Implementation for User Story 3

- [x] T025 [US3] Implement `--after` argument parsing in `src/slack_cli/commands/read.py`: parse value as integer (message count) or duration string matching `^\d+[MH]$` (minutes/hours). Fail fast with clear error if format is invalid. Fail with error if `--after` is used with a thread link.
- [x] T026 [US3] Extend read command in `src/slack_cli/commands/read.py` for follow-up fetch: if `--after` is an integer, call `conversations.history` with `oldest=message_ts` and `limit=N+1` (inclusive to include the linked message). If duration, compute `latest` timestamp from `oldest + duration` and call with no limit. For each fetched message that has `reply_count > 0`, fetch its thread via `conversations.replies` and attach as `message.replies`.
- [x] T027 [US3] Extend formatter in `src/slack_cli/formatter.py` for numbered multi-message output: number channel messages sequentially (1, 2, 3...) in headings, inline thread replies as sub-numbers (3.1, 3.2, 3.3) per contracts/cli-interface.md format. Maintain chronological sequence so message 4 follows after message 3's thread.
- [x] T028 [US3] Add unit tests for `--after` parsing and numbered formatting in `tests/unit/test_formatter.py` and extend `tests/integration/test_read_command.py`: test count-based and duration-based after, thread inlining in multi-message output, fewer messages than requested, `--after` with thread link error.

**Checkpoint**: `slack-cli read --after 5 '<link>'` and `slack-cli read --after 2H '<link>'` work correctly. Inline threads maintain proper numbering. Error on `--after` with thread link.

---

## Phase 6: User Story 4 - Fetch a DM by link (Priority: P2)

**Goal**: User provides a DM link (channel ID starting with `D` or `G`) and sees the message content.

**Independent Test**: `slack-cli read '<dm-link>'` outputs DM content. `--after` works with DM links. Access denied produces clear error.

### Implementation for User Story 4

- [x] T029 [US4] Verify DM support in `src/slack_cli/link.py`: ensure `parse_slack_link` correctly handles channel IDs starting with `D` (1:1 DM) and `G` (group DM). Add unit tests in `tests/unit/test_link.py` for DM link patterns.
- [x] T030 [US4] Add DM-specific error handling in `src/slack_cli/commands/read.py`: when Slack API returns `channel_not_found` or `not_in_channel` for a DM channel, produce a clear error message on stderr mentioning it is a DM and the token may lack access. Verify `--after` works with DM links (same as channel messages).
- [x] T031 [US4] Add DM test cases in `tests/integration/test_read_command.py`: DM message fetch, DM with `--after`, DM access denied error response.

**Checkpoint**: DM links work identically to channel links. Access errors produce clear messages. All DM test cases pass.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Final quality improvements across all user stories

- [x] T032 Review and harden error handling across all modules — verify every Slack API error code produces an actionable message on stderr per spec edge cases (deleted message, private channel, rate limit, expired tokens, session invalidation with User-Agent hint)
- [x] T033 [P] Verify `--help` output for both `slack-cli --help` and `slack-cli read --help` matches contracts/cli-interface.md usage examples and descriptions
- [x] T034 [P] Run `make check-all` and fix any linting/formatting issues across all source and test files
- [x] T035 Run full quickstart.md validation scenarios end-to-end (requires valid Slack tokens)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately
- **Foundational (Phase 2)**: Depends on Setup completion — BLOCKS all user stories
- **User Stories (Phase 3+)**: All depend on Foundational phase completion
  - US1 (Phase 3) must complete before US2 (Phase 4) — US2 extends US1's code
  - US3 (Phase 5) depends on US2 (needs pagination from T023)
  - US4 (Phase 6) can start after US1 (Phase 3) — independent of US2/US3
- **Polish (Phase 7)**: Depends on all user stories being complete

### Within Each Phase

- Tests can run in parallel with each other [P]
- Models/pure functions before services that use them
- Core implementation before CLI wiring
- Story complete before moving to next priority

### Parallel Opportunities

**Phase 1 (Setup)**:
```
T001 (pyproject.toml) → T005 (init) → T006 (__main__)
T002 (Makefile)       ─────────────────────────────────→ T007 (placeholder test)
T003 (.pre-commit)    ─ parallel ─┐
T004 (.gitignore)     ─ parallel ─┘
```

**Phase 2 (Foundational)**:
```
T008 (config) ─────→ T010 (api, needs config for tokens)
T009 (log)    ─ parallel with T008 ─┐
T011 (link)   ─ parallel ───────────┤
T012 (cache)  ─ parallel ───────────┘
```

**Phase 3 (US1)**:
```
T013-T017 (tests)  ─ all parallel ─┐
T018 (mrkdwn)      ─ parallel ─────┤
                                    → T019 (formatter, needs mrkdwn)
                                    → T020 (read cmd, needs api+link+cache+mrkdwn+formatter)
                                    → T021 (CLI wiring, needs read cmd)
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (T001-T007)
2. Complete Phase 2: Foundational (T008-T012)
3. Complete Phase 3: User Story 1 (T013-T021)
4. **STOP and VALIDATE**: `slack-cli read '<link>'` works end-to-end
5. This alone delivers the core value: Slack link → Markdown on stdout

### Incremental Delivery

1. Setup + Foundational → Project ready
2. Add US1 → Single message + thread reading works (MVP!)
3. Add US2 → Thread links and reply links work
4. Add US3 → `--after` ranges work with inline threads
5. Add US4 → DM links work
6. Polish → Error handling hardened, help text verified
