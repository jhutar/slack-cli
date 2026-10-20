# slack-cli

CLI tool that translates Slack links into readable Markdown on stdout.
Paste a Slack message link, get the conversation content — ready to pipe
to an AI agent or another tool.

## Features

- Fetch a single message (with its thread if it has replies)
- Fetch an entire thread by link
- Fetch follow-up messages by count (`--after 5`), duration (`--after 2H`) or all (`--after-all`)
- DM and group DM support
- Converts Slack's mrkdwn format to standard Markdown
- Resolves user mentions and channel references to display names
- Lists unread mentions, threads and DMs needing a response (`activity`) —
  the same feed as Slack's Activity panel

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

# Fetch a message plus everything after it (e.g., after a link from `slack-cli activity`)
slack-cli read --after-all 'https://mywork.slack.com/archives/C01234/p1234567890123456'

# Debug logging to stderr
slack-cli --log-level DEBUG read 'https://mywork.slack.com/archives/C01234/p1234567890123456'

# Morning triage: everything unread that needs a response
slack-cli activity

# Your messages from the past 14 days (one entry per message)
slack-cli mine --days 14

# Same, grouped: one link per thread and per channel/DM
slack-cli mine --days 14 --collapsed

# URLs only, one per line (for scripts)
slack-cli activity --csv

# Mark items as read (server-side, clears Slack's Activity tab)
slack-cli mark-read 'https://mywork.slack.com/archives/C01234/p1234567890123456?thread_ts=1234567890123456'
```

### Activity

`slack-cli activity` lists your unread activity, the same source as
Slack's Activity panel (one feed call instead of scanning every DM):

- **Mentions** — messages that mention you in channels (`[thread]` marks
  ones inside a thread). Each entry has a permalink you can feed straight
  to `slack-cli read`.
- **Threads** — threads with unread replies, with the unread count and a
  link to the latest reply.
- **Direct messages** — DMs and group DMs whose latest message is from
  someone else, with a link to it.

### Mark read

`slack-cli mark-read <slack-link>...` marks activity feed items as read
server-side — the same state Slack's own Activity tab uses, so items
disappear from it. Links are the permalinks printed by
`slack-cli activity` (plain or `--csv`):

- Each link is matched against the current unread activity feed; the
  matching feed item is marked read up to the link's timestamp, so
  replies newer than the link stay unread.
- Links not in the unread feed anymore (already read) produce a warning
  and are skipped; the remaining links are still processed.
- Marks are irreversible. Malformed links or Slack API failures exit
  with an error.

### Mine

`slack-cli mine` lists your activity over the past N days (`--days`,
default 7), based on messages you authored:

- **Expanded (default)** — one entry per message you posted: channel
  messages, thread replies, DMs, and group DMs, each with a permalink.
- **Collapsed (`--collapsed`)** — one entry per thread you replied in
  (link to the thread root), and one entry per channel, DM, or group DM
  for your top-level messages (link to your earliest message there).

`--csv` prints a CSV table with a header row, one row per entry
(message or collapsed group), newest first:
`link,source_type,from_where,from_time,to_time`. `source_type` is
`channel`, `thread`, `dm`, or `group_dm`; `from_where` is `#channel`,
`#channel@<thread_ts>` for threads, or the DM participant name(s);
times are ISO 8601 UTC (for groups, your first and last message).

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
