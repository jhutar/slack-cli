# CLI Interface Contract: slack-cli

## Command Structure

```
slack-cli [global-options] <subcommand> [subcommand-options] [arguments]
```

## Global Options

| Option | Short | Type | Default | Description |
|--------|-------|------|---------|-------------|
| `--config` | `-c` | path | `~/.config/slack-cli/config.toml` | Path to config file |
| `--log-level` | | choice | `WARNING` | Logging level for stderr: DEBUG, INFO, WARNING, ERROR |
| `--help` | `-h` | flag | | Show help and exit |
| `--version` | | flag | | Show version and exit |

## Subcommand: `read`

Fetch and display Slack messages from a link.

```
slack-cli read [options] <slack-link>
```

### Positional Arguments

| Argument | Required | Description |
|----------|----------|-------------|
| `slack-link` | Yes | Slack message URL |

### Options

| Option | Short | Type | Default | Description |
|--------|-------|------|---------|-------------|
| `--after` | `-a` | str | None | Number of follow-up messages (integer) or duration (e.g., `30M`, `2H`) |
| `--help` | `-h` | flag | | Show help for read subcommand |

### Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | General error (invalid input, unknown error) |
| 2 | Authentication error (missing/invalid/expired tokens) |
| 3 | Slack API error (rate limit, access denied, not found) |

## Output Format (stdout)

Messages are output as Markdown to stdout. Each message follows this
format:

```markdown
### @username (2026-06-21 14:30 UTC)

Message content converted to standard Markdown.

Code blocks, **bold**, *italic*, ~~strikethrough~~, and
[links](https://example.com) are preserved.

> Quoted text preserved as blockquotes.

---
```

### Thread Output

When a message has thread replies, they appear indented with sub-numbering:

```markdown
### 1. @alice (2026-06-21 14:30 UTC)

Parent message content.

#### 1.1. @bob (2026-06-21 14:32 UTC)

First reply in thread.

#### 1.2. @carol (2026-06-21 14:35 UTC)

Second reply in thread.

---

### 2. @dave (2026-06-21 14:40 UTC)

Next channel message after the thread.

---
```

### Single Reply Output

When the link points to a specific reply (not the parent), only that
reply is shown:

```markdown
### @bob (2026-06-21 14:32 UTC)

The specific reply message content.

---
```

### File Attachments

When a message contains file attachments with no text:

```markdown
### @alice (2026-06-21 14:30 UTC)

[Attachment: report.pdf]

---
```

## Error Output (stderr)

Errors are written to stderr with a prefix:

```
Error: Invalid Slack link format. Expected: https://<workspace>.slack.com/archives/<channel>/p<timestamp>
Error: SLACK_CLI_XOXC_TOKEN is not set. Set it in the environment or in ~/.config/slack-cli/config.toml
Error: Access denied to channel C01234567. The token may lack permission.
Error: --after is only supported for channel messages, not thread links.
```

## Config File Format

Location: `~/.config/slack-cli/config.toml`

```toml
[auth]
xoxc_token = "xoxc-..."
xoxd_token = "xoxd-..."
user_agent = "Mozilla/5.0 ..."

[logging]
level = "WARNING"           # stderr log level
log_file = ""               # override log file path

[cache]
ttl = 86400                 # cache TTL in seconds (default: 24h)
```

### Configuration Precedence

1. CLI arguments (highest priority)
2. Environment variables (`SLACK_CLI_XOXC_TOKEN`, `SLACK_CLI_XOXD_TOKEN`,
   `SLACK_CLI_USER_AGENT`)
3. Config file values
4. Built-in defaults (lowest priority)

## Environment Variables

| Variable | Description |
|----------|-------------|
| `SLACK_CLI_XOXC_TOKEN` | Slack xoxc session token |
| `SLACK_CLI_XOXD_TOKEN` | Slack xoxd cookie token |
| `SLACK_CLI_USER_AGENT` | Custom User-Agent header for enterprise Slack |

## Usage Examples

```bash
# Fetch a single message (and its thread if it has replies)
slack-cli read 'https://mywork.slack.com/archives/C01234/p1234567890123456'

# Fetch a message plus the next 10 messages in the channel
slack-cli read --after 10 'https://mywork.slack.com/archives/C01234/p1234567890123456'

# Fetch a message plus 2 hours of follow-up messages
slack-cli read --after 2H 'https://mywork.slack.com/archives/C01234/p1234567890123456'

# Pipe output to an AI agent
slack-cli read 'https://mywork.slack.com/archives/C01234/p1234567890123456' | ai-tool

# Enable debug logging to stderr
slack-cli --log-level DEBUG read 'https://mywork.slack.com/archives/C01234/p1234567890123456'
```
