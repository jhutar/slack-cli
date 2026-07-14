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
uv sync
```

Or for development:

```bash
make bootstrap
```

## Authentication

The tool uses Slack session tokens (xoxc + xoxd) from your browser.
These are **not** OAuth app tokens — no Slack app registration required.

### Extract from desktop app (experimental)

If you have the Slack desktop app installed (Flatpak or standard Linux),
you can extract tokens directly — no browser needed:

```bash
# Extract tokens and write config (Slack app must be closed)
slack-cli extract

# List available workspaces without modifying config
slack-cli extract --list
```

The command auto-detects your Slack installation, extracts workspace
tokens and the session cookie, verifies authentication, and writes
everything to `~/.config/slack-cli/config.toml`.

**Requirements**: `libleveldb-dev` system package, GNOME Keyring unlocked.

### Quick login (experimental)

You only need the `d` cookie from your browser — the tool fetches the
xoxc token automatically:

1. Open Slack in your browser and log in
2. Open Developer Tools (F12) → Network → select any request → Cookies
3. Copy the `d` cookie value (starts with `xoxd-`)
4. Run:

```bash
slack-cli login mywork.slack.com --xoxd-token "xoxd-..."
```

Or omit `--xoxd-token` to be prompted interactively. The command
fetches the xoxc token, verifies authentication, and writes both
tokens to `~/.config/slack-cli/config.toml`.

### Manual configuration

To get the tokens from your browser:

1. Open Slack in your browser and log in
2. Open Developer Tools (F12) → Network → select any request → Cookies
3. Copy the `d` cookie value (starts with `xoxd-`)
4. Go to the Console tab and run:
   ```js
   JSON.parse(localStorage.getItem('localConfig_v2')).teams[Object.keys(JSON.parse(localStorage.getItem('localConfig_v2')).teams)[0]].token
   ```
5. Copy the `xoxc-` token from the output

Then configure the tokens using one of the options below.

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

# Debug logging to stderr
slack-cli --log-level DEBUG read 'https://mywork.slack.com/archives/C01234/p1234567890123456'
```

## Related Projects and Resources

- [Retrieving and Using Slack Cookies for Authentication](https://www.papermtn.co.uk/retrieving-and-using-slack-cookies-for-authentication/) — Blog post explaining how to extract Slack's `d` cookie from a browser to obtain a user session token.
- [slack-mcp-server](https://github.com/korotovsky/slack-mcp-server) — An MCP server enabling AI assistants to interact with Slack workspaces via messages, search, and DMs.
- [slacker](https://github.com/shanemcd/slacker) — A CLI tool that extracts Slack browser session credentials to automate Slack API calls.
- [slack-token-extractor](https://github.com/maorfr/slack-token-extractor) — A toolkit for extracting Slack xoxc/xoxd tokens via browser extensions or Playwright automation.
- [slacktokens](https://github.com/hraftery/slacktokens) — A Python library that extracts personal Slack API tokens and cookies from the Slack desktop app.

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
