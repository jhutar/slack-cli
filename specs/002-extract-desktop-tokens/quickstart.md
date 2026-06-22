# Quickstart Validation Guide: Extract Tokens from Slack Desktop App

## Prerequisites

- Slack desktop app installed (Flatpak or standard Linux)
- Slack app has been opened and logged into at least one workspace
- Slack app is **closed** (LevelDB requires exclusive access)
- GNOME Keyring is unlocked (for cookie decryption)
- Network access available (for token verification)

## Install dependencies

```bash
pip install -e .
```

After implementation, `pyproject.toml` will include `plyvel`, `secretstorage`, and `cryptography` as dependencies.

## Validation Scenarios

### Scenario 1: List workspaces (read-only)

```bash
slack-cli extract --list
```

**Expected**: Prints workspace names and URLs found in the Slack app's local storage. No files are modified.

### Scenario 2: Extract and write config (single workspace)

```bash
slack-cli extract
```

**Expected**: Auto-selects the workspace (if only one), verifies authentication, writes tokens to `~/.config/slack-cli/config.toml`, and prints success message.

### Scenario 3: Extract and write config (multiple workspaces)

```bash
slack-cli extract
```

**Expected**: Lists all workspaces with numbers, prompts user to select one, verifies, and writes config.

### Scenario 4: Verify extracted tokens work

```bash
slack-cli extract
slack-cli read 'https://yourworkspace.slack.com/archives/C01234/p1234567890123456'
```

**Expected**: After extracting tokens, the `read` command successfully fetches and displays the message content.

### Scenario 5: Error — Slack is running

```bash
# With Slack app open:
slack-cli extract
```

**Expected**: Error message on stderr: `Error: Slack's database is locked. Quit the Slack app and try again.` Exit code 1.

### Scenario 6: Error — No Slack installation

```bash
# On a system without Slack desktop:
slack-cli extract
```

**Expected**: Error message on stderr listing the paths that were searched. Exit code 1.

## Automated Test Validation

```bash
make test
```

Unit tests should cover:
- `_parse_local_config` with sample LevelDB data
- Path detection logic (Flatpak vs standard)
- Cookie decryption with known test vectors
- Workspace selection logic (single auto-select, multiple prompt)
- Error handling for all failure modes

See [cli-extract.md](contracts/cli-extract.md) for the full CLI contract and exit codes.
See [data-model.md](data-model.md) for entity definitions and data flow.
