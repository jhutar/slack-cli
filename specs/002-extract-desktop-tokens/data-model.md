# Data Model: Extract Tokens from Slack Desktop App

## Entities

### SlackInstallation

Represents a detected Slack desktop app installation on the local filesystem.

| Field      | Type   | Description                                              |
|------------|--------|----------------------------------------------------------|
| base_path  | Path   | Root data directory (e.g., `~/.var/app/com.slack.Slack/config/Slack/`) |
| leveldb_path | Path | Full path to `Local Storage/leveldb` subdirectory        |
| cookies_path | Path | Full path to `Cookies` SQLite database                   |
| source     | str    | Installation type: `"flatpak"` or `"standard"`           |

### WorkspaceToken

Represents a single workspace's authentication token extracted from LevelDB.

| Field | Type | Description                                            |
|-------|------|--------------------------------------------------------|
| url   | str  | Workspace URL (e.g., `https://mywork.slack.com`)       |
| name  | str  | Human-readable workspace name                          |
| token | str  | xoxc personal token (starts with `xoxc-`)              |

### ExtractedCredentials

The complete set of credentials extracted from one Slack installation.

| Field      | Type               | Description                               |
|------------|--------------------|-------------------------------------------|
| workspaces | list[WorkspaceToken] | All workspace tokens found in LevelDB    |
| cookie     | str                | Decrypted `d` cookie value (starts with `xoxd-`) |

## Relationships

- A `SlackInstallation` contains one `Cookies` database and one `leveldb` store.
- A `leveldb` store contains zero or more `WorkspaceToken` entries (one per workspace).
- A `Cookies` database contains exactly one `d` cookie, shared across all workspaces.
- The user selects one `WorkspaceToken` from the list; that token + the `cookie` are written to the config file.

## State Transitions

```
[detect installation] → SlackInstallation found
    → [extract tokens from LevelDB] → list[WorkspaceToken]
    → [decrypt cookie from Cookies DB] → cookie string
    → [user selects workspace] → single WorkspaceToken
    → [verify via auth.test] → success/failure
    → [write config] → config file updated
```

## Data Sources

- **LevelDB** (`Local Storage/leveldb`): Contains `localConfig_v2` key with JSON-encoded team data including tokens. Read via `plyvel`. Requires Slack app to be closed (LevelDB is single-process).
- **Cookies SQLite** (`Cookies`): Standard Chromium cookie database. The `d` cookie is in the `cookies` table with `host_key='.slack.com'`, `name='d'`. Value is `v11`-encrypted (AES-128-CBC).
- **GNOME Keyring**: Holds the "Slack Safe Storage" password used to derive the AES key for cookie decryption.
