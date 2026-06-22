# CLI Contract: `slack-cli extract`

## Synopsis

```
slack-cli extract [--list] [--config PATH]
```

## Arguments

| Argument    | Type   | Required | Default                             | Description                                |
|-------------|--------|----------|--------------------------------------|--------------------------------------------|
| `--list`    | flag   | No       | false                                | List workspaces without writing config     |
| `--config`  | PATH   | No       | `~/.config/slack-cli/config.toml`    | Path to config file (inherited from global)|

The `--config` flag is inherited from the top-level `slack-cli` parser.

## Behavior

### Default mode (no `--list`)

1. Detect Slack installation (Flatpak first, then standard).
2. Extract workspace tokens from LevelDB.
3. Decrypt the `d` cookie from the Cookies database.
4. If one workspace: auto-select. If multiple: prompt user to choose.
5. Verify selected token + cookie via Slack API `auth.test`.
6. Write token and cookie to config file.
7. Print success message with workspace name and config path.

### List mode (`--list`)

1. Detect Slack installation.
2. Extract workspace tokens from LevelDB.
3. Print workspace names and URLs to stdout.
4. Exit without modifying any files.

## Output

### Success (default mode)

```
Found Slack installation (flatpak).
Extracted 2 workspace(s).
  1. My Company (https://mycompany.slack.com)
  2. Side Project (https://sideproject.slack.com)
Select workspace [1]: 1
Verifying authentication...
Logged in as @jhutar in My Company.
Config written to /home/jhutar/.config/slack-cli/config.toml
```

### Success (list mode)

```
Found Slack installation (flatpak).
  1. My Company (https://mycompany.slack.com)
  2. Side Project (https://sideproject.slack.com)
```

### Single workspace (auto-select, no prompt)

```
Found Slack installation (flatpak).
Extracted 1 workspace: My Company.
Verifying authentication...
Logged in as @jhutar in My Company.
Config written to /home/jhutar/.config/slack-cli/config.toml
```

## Exit Codes

| Code | Meaning                                                  |
|------|----------------------------------------------------------|
| 0    | Success                                                  |
| 1    | No Slack installation found                              |
| 1    | LevelDB locked (Slack is running)                        |
| 1    | LevelDB contains no recognizable token data              |
| 1    | Cookie decryption failed                                 |
| 2    | Authentication verification failed (invalid/expired tokens) |
| 2    | Network unavailable during verification                  |

## Error Messages (stderr)

All errors follow the pattern: what failed, why, what to do next.

- `Error: No Slack installation found. Searched: ~/.var/app/com.slack.Slack/config/Slack/, ~/.config/Slack/`
- `Error: Slack's database is locked. Quit the Slack app and try again.`
- `Error: No workspace tokens found in Slack's local storage. The Slack app may need to be opened at least once.`
- `Error: Could not decrypt the authentication cookie. Ensure GNOME Keyring is unlocked.`
- `Error: Authentication failed: {detail}. The tokens may have expired — try opening Slack to refresh them.`
