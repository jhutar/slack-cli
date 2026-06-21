# Implementation Plan: Slack Link Reader

**Branch**: `001-slack-link-reader` | **Date**: 2026-06-21 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/001-slack-link-reader/spec.md`

## Summary

CLI tool that takes a Slack message link and outputs the message content
as Markdown to stdout. Supports channel messages, threads, DMs, and
follow-up message ranges. Authenticates via xoxc/xoxd session tokens.
Converts Slack's mrkdwn format to standard Markdown. Built in Python
with argparse subcommands, dual-handler logging, TOML config, and
JSON-based user/channel name caching.

## Technical Context

**Language/Version**: Python 3.11+

**Primary Dependencies**: `requests` (HTTP client) — single external
dependency. All other needs covered by stdlib (`argparse`, `logging`,
`tomllib`, `json`, `re`, `pathlib`, `datetime`).

**Storage**: JSON cache files for user/channel name resolution at
`~/.cache/slack-cli/`. TOML config file at
`~/.config/slack-cli/config.toml`.

**Testing**: `pytest`

**Target Platform**: Linux/macOS CLI

**Project Type**: CLI tool

**Performance Goals**: Single command invocation completes in under 5
seconds for typical use (1 message + thread). Network latency dominates.

**Constraints**: Single external dependency (`requests`). No async
required — tool processes one link per invocation.

**Scale/Scope**: Single user, single invocation. Not designed for bulk
export. Typical use: 1–50 messages per invocation.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Evidence |
|-----------|--------|----------|
| I. Minimal Dependencies | PASS | Single external dep (`requests`). Config via stdlib `tomllib`. Cache via stdlib `json`. |
| II. Fail Fast | PASS | Missing tokens → immediate error with env var name. Invalid link → immediate error with format hint. API failures → immediate error with Slack error message. |
| III. Separation of Concerns | PASS | Modules split by responsibility: `link.py` (parsing), `api.py` (HTTP), `mrkdwn.py` (conversion), `formatter.py` (output), `config.py` (config), `log.py` (logging), `commands/read.py` (orchestration). |
| IV. Error Handling & Feedback | PASS | All errors to stderr with what/why/next-step. Three distinct exit codes (1=input, 2=auth, 3=API). |
| V. No Over-Engineering | PASS | One subcommand (`read`). No plugin system, no async, no abstract base classes. Regex-based mrkdwn conversion (no parser generator). |
| VI. Testable Code | PASS | API client accepts base URL and credentials as parameters. mrkdwn converter is pure function. Link parser is pure function. Formatter takes data objects, returns strings. |

## Project Structure

### Documentation (this feature)

```text
specs/001-slack-link-reader/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   └── cli-interface.md
└── tasks.md
```

### Source Code (repository root)

```text
src/
└── slack_cli/
    ├── __init__.py           # Version string
    ├── __main__.py           # Entry point: main()
    ├── cli.py                # argparse setup with subcommands
    ├── config.py             # TOML config + env var loading
    ├── log.py                # Dual-handler logging setup
    ├── api.py                # Slack API client (requests-based)
    ├── link.py               # Slack URL parser
    ├── mrkdwn.py             # mrkdwn → Markdown converter
    ├── formatter.py          # Message → Markdown output formatting
    ├── cache.py              # User/channel name cache (JSON files)
    └── commands/
        ├── __init__.py
        └── read.py           # Read subcommand implementation

tests/
├── unit/
│   ├── test_link.py          # Link parsing tests
│   ├── test_mrkdwn.py        # mrkdwn conversion tests
│   ├── test_formatter.py     # Output formatting tests
│   ├── test_config.py        # Config loading tests
│   └── test_cache.py         # Cache read/write tests
└── integration/
    └── test_read_command.py  # End-to-end with mocked API

pyproject.toml                # Project metadata, dependencies, entry point
```

**Structure Decision**: Single-project layout with `src/` layout
(recommended Python packaging practice). The `commands/` package enables
adding future subcommands (e.g., `write`) by adding new modules without
modifying existing code. Each module has a single responsibility per
Constitution Principle III.

## Complexity Tracking

No Constitution Check violations. Table intentionally left empty.

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| — | — | — |

## Phase 0: Repository Scaffolding

Before any feature code, set up the project skeleton with build
tooling, linting, and testing infrastructure. Follows the pattern from
the `external/jira_query/` reference project.

### Makefile

Primary interface for running linters and tests. Targets:

| Target | Description |
|--------|-------------|
| `help` | Show available targets (default goal) |
| `bootstrap` | Install Python 3.11 via uv, install pre-commit, install hooks |
| `test` | Run `PYTHONPATH=src pytest -v` |
| `check` | Run pre-commit on staged changes only |
| `check-all` | Run pre-commit on all files |

### Pre-commit Configuration

`.pre-commit-config.yaml` with hook types `pre-commit, commit-msg`:

- **pre-commit-hooks**: check-yaml, end-of-file-fixer,
  trailing-whitespace, detect-private-key, check-added-large-files,
  check-merge-conflict, check-json, mixed-line-ending
- **ruff-pre-commit**: ruff (with `--fix`), ruff-format
- **bandit**: security scanning (skip B101 for test asserts)
- **gitleaks**: secret detection
- **shellcheck-py**: shell script linting

### pyproject.toml

- Build backend: `hatchling`
- Package location: `src/slack_cli`
- Entry point: `slack-cli = "slack_cli.__main__:main"`
- Python: `>=3.11`
- Runtime dependency: `requests`
- Dev dependency group: `pytest`

### Initial File Tree

```text
slack-cli/
├── Makefile
├── .pre-commit-config.yaml
├── pyproject.toml
├── .gitignore                   # (already exists, extend for Python)
├── src/
│   └── slack_cli/
│       ├── __init__.py          # version = "0.1.0"
│       └── __main__.py          # stub main() with argparse skeleton
└── tests/
    └── test_placeholder.py      # single passing test to verify setup
```

### Validation

After scaffolding is complete:
1. `make bootstrap` succeeds
2. `make test` runs pytest and the placeholder test passes
3. `make check-all` runs all pre-commit hooks cleanly
4. `pip install -e .` installs the package
5. `slack-cli --help` shows the argparse help output

## Key Design Decisions

### Module Responsibilities

| Module | Responsibility | Inputs | Outputs |
|--------|---------------|--------|---------|
| `cli.py` | Parse CLI arguments | sys.argv | Namespace object |
| `config.py` | Load config from file + env | File path, env | Config dict |
| `log.py` | Set up stderr + file logging | Log level, file path | Configured logger |
| `link.py` | Parse Slack URL into components | URL string | SlackLink dataclass |
| `api.py` | Make Slack API HTTP calls | Credentials, endpoint, params | JSON response dict |
| `cache.py` | Read/write user/channel caches | Cache dir, TTL | Name lookups |
| `mrkdwn.py` | Convert mrkdwn to Markdown | mrkdwn string, user/channel maps | Markdown string |
| `formatter.py` | Format messages as Markdown output | List of Message objects | Markdown string |
| `commands/read.py` | Orchestrate the read flow | Parsed args, config | stdout output |

### Main Flow (commands/read.py)

```
1. Parse Slack link → SlackLink
2. Load config (file + env vars)
3. Set up logging (stderr + file)
4. Validate auth tokens (fail fast if missing)
5. Determine fetch strategy:
   a. Thread link → fetch thread via conversations.replies
   b. Reply link → fetch single message via conversations.history
   c. Channel message:
      - Fetch the message via conversations.history
      - If message has thread replies → fetch thread
      - If --after specified → fetch follow-up messages
        - For each follow-up with thread → fetch its thread
6. Resolve user mentions and channel refs (with caching)
7. Convert mrkdwn to Markdown for each message
8. Format and output to stdout
```

### Slack API Call Pattern

All API calls use the same HTTP pattern discovered from reference tools:

```python
response = requests.post(
    f"https://slack.com/api/{method}",
    headers={
        "Authorization": f"Bearer {xoxc_token}",
        "User-Agent": user_agent,  # if configured
    },
    cookies={"d": xoxd_token},
    data=params,
)
```

### Logging Configuration

```
stderr handler:
  - Level: configurable (default WARNING)
  - Format: "%(levelname)s: %(message)s"

file handler:
  - Level: always DEBUG
  - Path: ~/.cache/slack-cli/debug.log
  - Format: "%(asctime)s %(levelname)s %(name)s: %(message)s"
  - Rotation: not in v1 (file can be manually deleted)
```

### mrkdwn Conversion Pipeline

```
Input: raw mrkdwn string + user_map + channel_map
  1. Resolve user mentions: <@U123> → @displayname
  2. Resolve channel refs: <#C123|name> → #name
  3. Resolve special mentions: <!channel> → @channel
  4. Convert links: <url|text> → [text](url)
  5. Convert bare links: <url> → url
  6. Convert bold: *text* → **text**
  7. Convert italic: _text_ → *text*
  8. Convert strikethrough: ~text~ → ~~text~~
  9. Decode HTML entities: &amp; &lt; &gt;
Output: standard Markdown string
```

Note: Steps 6-8 must skip content inside code blocks and inline code
to avoid corrupting code samples.

## References

- [research.md](research.md) — Technology decisions and rationale
- [data-model.md](data-model.md) — Entity definitions and cache format
- [contracts/cli-interface.md](contracts/cli-interface.md) — CLI interface contract
- [quickstart.md](quickstart.md) — Validation scenarios
