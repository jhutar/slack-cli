# slack-cli

CLI tool that translates Slack links into readable Markdown on stdout.
Paste a Slack message link, get the conversation content — ready to pipe
to an AI agent or another tool.

## Features

- Fetch a single message (with its thread if it has replies)
- Fetch an entire thread by link
- Fetch follow-up messages by count (`--after 5`) or duration (`--after 2H`)
- DM and group DM support
- Converts Slack's mrkdwn format to standard Markdown
- Resolves user mentions and channel references to display names

## Setup

Requires Python 3.11+.

```bash
pip install -e .
```

Or for development:

```bash
make bootstrap
```

## Authentication

The tool uses Slack session tokens (xoxc + xoxd) from your browser.
These are **not** OAuth app tokens — no Slack app registration required.

### Getting your tokens

1. Open Slack in your browser and log in
2. Open Developer Tools (F12) → Network → select some request → Cookies
3. Copy the `d` cookie value — this is your **xoxd** token (starts with `xoxd-`)
4. Open Developer Tools (F12) → Console and run: `JSON.parse(localStorage.getItem('localConfig_v2')).teams[Object.keys(JSON.parse(localStorage.getItem('localConfig_v2')).teams)[0]].token`
5. The output is your **xoxc** token (starts with `xoxc-`)

### Configuration

**Option A** — Environment variables:

```bash
export SLACK_CLI_XOXC_TOKEN="xoxc-..."
export SLACK_CLI_XOXD_TOKEN="xoxd-..."
# Required for enterprise Slack workspaces:
export SLACK_CLI_USER_AGENT="Mozilla/5.0 (X11; Linux x86_64; rv:148.0) Gecko/20100101 Firefox/148.0"
```

**Option B** — Config file at `~/.config/slack-cli/config.toml`:

```toml
[auth]
xoxc_token = "xoxc-..."
xoxd_token = "xoxd-..."
user_agent = "Mozilla/5.0 (X11; Linux x86_64; rv:148.0) Gecko/20100101 Firefox/148.0"

[logging]
level = "WARNING"

[cache]
ttl = 86400
```

Environment variables override config file values.

## Usage

```bash
# Fetch a single message (includes thread if it has replies)
slack-cli read 'https://mywork.slack.com/archives/C01234/p1234567890123456'

# Fetch a message plus the next 10 messages
slack-cli read --after 10 'https://mywork.slack.com/archives/C01234/p1234567890123456'

# Fetch a message plus 2 hours of follow-up
slack-cli read --after 2H 'https://mywork.slack.com/archives/C01234/p1234567890123456'

# Pipe to an AI agent
slack-cli read 'https://mywork.slack.com/archives/C01234/p1234567890123456' | ai-tool

# Debug logging to stderr
slack-cli --log-level DEBUG read 'https://mywork.slack.com/archives/C01234/p1234567890123456'
```

## Development

```bash
# Install tooling (uv, pre-commit hooks)
make bootstrap

# Run tests
make test

# Run linters on staged changes
make check

# Run linters on all files
make check-all
```
