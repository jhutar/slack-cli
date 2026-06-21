# Quickstart: Slack Link Reader

## Prerequisites

- Python 3.11+
- Slack xoxc and xoxd session tokens (from an authenticated browser
  session)
- `pip` or `uv` for installing dependencies

## Setup

### 1. Install

```bash
cd slack-cli
pip install -e .
```

### 2. Configure Authentication

Option A — Environment variables:
```bash
export SLACK_CLI_XOXC_TOKEN="xoxc-..."
export SLACK_CLI_XOXD_TOKEN="xoxd-..."
# Required for enterprise Slack workspaces:
export SLACK_CLI_USER_AGENT="Mozilla/5.0 (X11; Linux x86_64; rv:148.0) Gecko/20100101 Firefox/148.0"
```

Option B — Config file at `~/.config/slack-cli/config.toml`:
```toml
[auth]
xoxc_token = "xoxc-..."
xoxd_token = "xoxd-..."
user_agent = "Mozilla/5.0 (X11; Linux x86_64; rv:148.0) Gecko/20100101 Firefox/148.0"
```

### 3. Verify Authentication

```bash
slack-cli read 'https://yourworkspace.slack.com/archives/C01234567/p1234567890123456'
```

If tokens are valid, you should see the message content as Markdown on
stdout. If tokens are missing or expired, you'll see a clear error on
stderr.

## Validation Scenarios

### Scenario 1: Single Message

```bash
slack-cli read '<link-to-a-channel-message>'
```

**Expected**: Stdout shows the message with author, timestamp, and
content in Markdown format.

### Scenario 2: Thread

```bash
slack-cli read '<link-to-a-message-with-thread-replies>'
```

**Expected**: Stdout shows the parent message followed by all thread
replies in chronological order with sub-numbering (1.1, 1.2, ...).

### Scenario 3: Follow-up Messages

```bash
slack-cli read --after 5 '<link-to-a-channel-message>'
```

**Expected**: Stdout shows the linked message plus the next 5 messages
in the channel. Any messages with threads include their replies inline.

### Scenario 4: Duration-based Follow-up

```bash
slack-cli read --after 1H '<link-to-a-channel-message>'
```

**Expected**: Stdout shows the linked message plus all messages posted
in the next hour.

### Scenario 5: DM

```bash
slack-cli read '<link-to-a-dm-message>'
```

**Expected**: Stdout shows the DM content with author and timestamp.

### Scenario 6: Pipe to Another Tool

```bash
slack-cli read '<link>' | wc -l
```

**Expected**: Output is clean Markdown that can be piped without errors.

### Scenario 7: Error Cases

```bash
# Missing token
unset SLACK_CLI_XOXC_TOKEN
slack-cli read '<link>'
# Expected: stderr shows error naming the missing variable, exit code 2

# Invalid link
slack-cli read 'https://not-a-slack-link.com/foo'
# Expected: stderr shows link format error, exit code 1

# Debug logging
slack-cli --log-level DEBUG read '<link>'
# Expected: stderr shows debug-level API call details
```
