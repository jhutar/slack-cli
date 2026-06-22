# Feature Specification: Extract Tokens from Slack Desktop App

**Feature Branch**: `002-extract-desktop-tokens`

**Created**: 2026-06-22

**Status**: Draft

**Input**: User description: "Add functionality to extract tokens from Slack desktop app that could be used to populate or update config file. App is installed as Flatpak with data in /home/jhutar/.var/app/com.slack.Slack."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Extract tokens from Flatpak Slack and update config (Priority: P1)

A user has the Slack desktop app installed as a Flatpak and wants to automatically extract their authentication tokens (xoxc + xoxd cookie) and write them to the slack-cli config file, so they can use slack-cli without manually copying tokens from a browser.

**Why this priority**: This is the core purpose of the feature — enabling a zero-browser-involvement authentication path for Flatpak Slack users. Without this, users must resort to the manual browser-based flow described in the README.

**Independent Test**: Can be fully tested by running the new command with a Flatpak Slack installation present, and verifying the config file is written with valid tokens that successfully authenticate against the Slack API.

**Acceptance Scenarios**:

1. **Given** the Slack desktop app (Flatpak) is closed and its local storage contains valid tokens, **When** the user runs the extract command, **Then** tokens for all workspaces are discovered, the user selects a workspace, and the config file is written with the xoxc token and xoxd cookie for that workspace.
2. **Given** the config file already exists with tokens for a different workspace, **When** the user runs the extract command, **Then** the existing config is preserved and updated with the new tokens (auth section is replaced, other sections remain intact).
3. **Given** the Slack app is running and the LevelDB database is locked, **When** the user runs the extract command, **Then** the tool reports a clear error message telling the user to quit Slack first.

---

### User Story 2 - Extract tokens from standard Linux Slack install (Priority: P2)

A user has the Slack desktop app installed via the standard (non-Flatpak) method (`~/.config/Slack/`) and wants to extract tokens the same way.

**Why this priority**: Supports the traditional Linux installation path. Same functionality as P1 but for the conventional data directory.

**Independent Test**: Can be tested by running the extract command on a system with a standard Slack installation at `~/.config/Slack/` and verifying correct token extraction and config writing.

**Acceptance Scenarios**:

1. **Given** a standard Linux Slack install with data at `~/.config/Slack/Local Storage/leveldb`, **When** the user runs the extract command, **Then** tokens are extracted and the config file is updated identically to the Flatpak flow.
2. **Given** neither Flatpak nor standard Slack data directories exist, **When** the user runs the extract command, **Then** the tool prints a clear error explaining that no Slack installation was found and lists the paths it searched.

---

### User Story 3 - List available workspaces without writing config (Priority: P3)

A user wants to see which workspaces are available in their Slack app without modifying any configuration.

**Why this priority**: Useful for discovery and debugging, but the core value is in actually writing the config (P1/P2).

**Independent Test**: Can be tested by running the command in list-only mode and verifying all workspaces from the Slack app are displayed with their names and URLs.

**Acceptance Scenarios**:

1. **Given** the Slack desktop app is closed and has multiple workspaces configured, **When** the user runs the extract command with a list-only option, **Then** all workspace names and URLs are printed to stdout without modifying any files.

---

### Edge Cases

- What happens when the LevelDB database exists but contains no `localConfig_v2` key (corrupted or empty Slack data)?
- What happens when the cookie store is not accessible or the cookie decryption fails?
- What happens when the user has both a Flatpak and a standard Slack installation?
- What happens when a workspace token is present in LevelDB but the xoxd cookie has expired?

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST extract xoxc tokens from the Slack desktop app's LevelDB local storage.
- **FR-002**: System MUST extract the xoxd cookie (the `d` cookie) from the Slack desktop app's cookie store.
- **FR-003**: System MUST support the Flatpak Slack data path (`~/.var/app/com.slack.Slack/config/Slack/`).
- **FR-004**: System MUST support the standard Linux Slack data path (`~/.config/Slack/`).
- **FR-005**: System MUST auto-detect which Slack installation path is available, preferring the one that exists.
- **FR-006**: When multiple workspaces are found, system MUST present the user with a list and let them choose which workspace to configure.
- **FR-007**: System MUST write the selected workspace's xoxc token and the xoxd cookie to the config file using the existing `write_config` mechanism.
- **FR-008**: System MUST verify extracted tokens by calling the Slack API (`auth.test`) before writing the config, just as the existing `login` command does.
- **FR-009**: System MUST provide a list-only mode that displays discovered workspaces without modifying files.
- **FR-010**: System MUST fail with a clear, actionable error message when the Slack app's database is locked (app is running), no Slack installation is found, or the database contents are unrecognizable.
- **FR-011**: When both Flatpak and standard installations exist, system MUST prefer the Flatpak path first and fall back to the standard path only if the Flatpak path does not exist.

### Key Entities

- **Workspace**: A Slack workspace identified by its URL, with an associated name and xoxc token.
- **Cookie**: The `d` cookie used for Slack API authentication, shared across all workspaces.
- **Config File**: The TOML configuration file at `~/.config/slack-cli/config.toml` containing auth tokens and other settings.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: User can populate a valid config file from their Slack desktop app in under 30 seconds, without opening a browser or manually copying any values.
- **SC-002**: Extracted tokens successfully authenticate against the Slack API on first use in 95%+ of cases where the Slack app has a valid session.
- **SC-003**: Error messages for all failure conditions (app locked, no install found, expired session) are actionable — each tells the user what to do next.
- **SC-004**: The command works identically for both Flatpak and standard Linux Slack installations.

## Assumptions

- The Slack desktop app stores workspace tokens in a LevelDB database at a known, consistent path within its data directory.
- The `localConfig_v2` key structure used by the existing `slacktokens.py` library remains the format used by current Slack desktop versions.
- The user is on Linux (macOS support for this feature is out of scope for this specification, though the underlying `slacktokens.py` already handles macOS paths).
- The `d` cookie extraction requires either the Slack app to be closed or a read-only approach to the cookie store.
- The existing `write_config` function in `slack_cli/config.py` is sufficient for persisting extracted tokens.
- The `leveldb` and `pycookiecheat` Python packages (used by `slacktokens.py`) are acceptable dependencies for this feature.
