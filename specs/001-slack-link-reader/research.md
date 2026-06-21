# Research: Slack Link Reader

## Slack API Authentication with xoxc/xoxd Tokens

### Decision: Use xoxc as Bearer token + xoxd as cookie

**Rationale**: Both reference tools (slacker, slack-mcp-server) confirm the
same pattern. The xoxc token goes in the `Authorization: Bearer` header,
and the xoxd token goes as a cookie named `d`.

**Request format**:
```python
response = requests.post(
    "https://slack.com/api/<method>",
    headers={"Authorization": f"Bearer {xoxc_token}"},
    cookies={"d": xoxd_token},
    data={"channel": channel_id, ...}
)
```

**Alternatives considered**:
- Passing token as form data `token=` field: Works but less standard.
- Using `slack_sdk` Python library: Designed for OAuth tokens (xoxp/xoxb),
  not tested with xoxc/xoxd session tokens. Would add a heavy dependency
  for something we can do with simple HTTP calls.

### Enterprise Slack: User-Agent Requirement

**Decision**: Support configurable User-Agent via `SLACK_CLI_USER_AGENT`
environment variable (and config file).

**Rationale**: Enterprise Slack workspaces reject requests with non-browser
User-Agents and invalidate sessions. The slack-mcp-server project uses
custom TLS fingerprinting (utls in Go) for additional evasion. In Python,
the `requests` library uses standard TLS which may be sufficient when
combined with a browser User-Agent. If custom TLS becomes necessary,
`curl_cffi` could be added later.

**Alternatives considered**:
- Custom TLS via `curl_cffi`: Would add a compiled dependency. Try
  User-Agent alone first.
- No User-Agent support: Would break enterprise Slack users.

## Slack API Endpoints Needed

### Decision: Use four standard API endpoints

| Endpoint | Purpose | Parameters |
|----------|---------|------------|
| `conversations.history` | Fetch channel/DM messages | channel, oldest, latest, limit, cursor |
| `conversations.replies` | Fetch thread replies | channel, ts, limit, cursor |
| `users.info` | Resolve user ID → display name | user |
| `conversations.info` | Resolve channel ID → name | channel |

**Rationale**: These are the minimum set required. Both reference tools use
these same endpoints. All are standard Slack Web API methods that work
with xoxc/xoxd tokens.

**Alternatives considered**:
- `users.list` for bulk user loading: Over-fetches. We only need users
  who appear in the fetched messages.
- Edge API (`client.boot`, etc.): Undocumented, may change. Standard API
  is sufficient for our read-only use case.

## Slack Message Format (mrkdwn)

### Decision: Custom mrkdwn→Markdown converter using regex

**Rationale**: Slack uses a proprietary format called "mrkdwn" (not HTML,
not standard Markdown). No existing Python library converts mrkdwn TO
Markdown — the available libraries (`markdown-to-mrkdwn`, `slackify-markdown`)
convert in the opposite direction (Markdown → mrkdwn).

The conversion rules are straightforward enough for regex:

| mrkdwn | Markdown | Regex complexity |
|--------|----------|-----------------|
| `*bold*` | `**bold**` | Simple |
| `_italic_` | `*italic*` | Simple |
| `~strike~` | `~~strike~~` | Simple |
| `` `code` `` | `` `code` `` | No change needed |
| ` ```block``` ` | ` ```block``` ` | No change needed |
| `<url\|text>` | `[text](url)` | Moderate |
| `<url>` | `url` | Simple |
| `<@U123>` | `@displayname` | Requires API lookup |
| `<#C123\|name>` | `#name` | Simple |
| `<!channel>` | `@channel` | Simple |
| `&amp;` `&lt;` `&gt;` | `&` `<` `>` | Simple |

**Alternatives considered**:
- Using an existing library: None exists for this direction.
- Full parser (AST): Over-engineering for the conversion rules above.

## HTTP Client Library

### Decision: `requests` library

**Rationale**: Single external dependency. Provides clean API for headers,
cookies, form data, and error handling. The stdlib `urllib` would require
significantly more code for the same functionality (cookie handling,
redirect following, etc.).

**Alternatives considered**:
- `httpx`: More modern, supports async. But we don't need async — our
  tool processes one link per invocation. Extra dependency weight not
  justified.
- `urllib` (stdlib): Possible but would require manual cookie jar
  management, header construction, and error handling. Violates
  "clean, maintainable code" principle for no benefit.

## Configuration and Storage

### Decision: TOML config file + XDG directories

- Config: `~/.config/slack-cli/config.toml` (via `$XDG_CONFIG_HOME`)
- Cache: `~/.cache/slack-cli/` (via `$XDG_CACHE_HOME`)
- Log file: `~/.cache/slack-cli/debug.log`

**Rationale**: TOML is human-readable and parseable with stdlib `tomllib`
(Python 3.11+). XDG Base Directory Specification is the standard on
Linux. Config file provides persistent storage for tokens so users don't
need to export env vars in every shell.

**Precedence order**: CLI args > environment variables > config file.

**Alternatives considered**:
- INI format: Less expressive, no standard for nested structures.
- YAML: Requires `PyYAML` dependency.
- JSON: Poor for human editing (no comments).
- Single directory (`~/.config/slack-cli/` for everything): Violates
  XDG spec, but simpler. User suggested this — cache will go here if
  XDG vars are not set.

## Caching Strategy

### Decision: JSON files for user/channel name caches with 24h TTL

**Rationale**: The slack-mcp-server caches user and channel info as JSON
files with configurable TTL and atomic writes. We need the same to avoid
repeated API calls for user/channel name resolution. Files are simple,
inspectable, and require no dependencies.

**Cache files**:
- `~/.cache/slack-cli/users.json` — `{user_id: display_name}` map
- `~/.cache/slack-cli/channels.json` — `{channel_id: channel_name}` map

**Alternatives considered**:
- No cache (fetch every time): Too slow for messages with many mentions.
- SQLite: Over-engineering for simple key-value lookups.
- In-memory only: Would work for single invocations but wastes API calls
  across runs.

## Python Version

### Decision: Python 3.11+

**Rationale**: Provides `tomllib` in stdlib (zero-dependency config parsing).
Python 3.10 is in security-only maintenance. A new CLI tool in 2026 should
target a modern Python version.

**Alternatives considered**:
- Python 3.8+ (like slacker): Broader compatibility but requires
  `tomli` dependency for TOML parsing.
- Python 3.12+: Unnecessary restriction.

## Logging Approach

### Decision: Python `logging` module with dual handlers

1. **stderr handler**: Configurable level (default INFO), concise format
2. **File handler**: Always DEBUG level, verbose format with timestamps

**Rationale**: The user explicitly requested this configuration. The stdlib
`logging` module provides everything needed. Log file at
`~/.cache/slack-cli/debug.log`.

**Alternatives considered**:
- `structlog`: Structured logging. Over-engineering for a CLI tool.
- Print-based (like slacker): No log levels, no file output.
