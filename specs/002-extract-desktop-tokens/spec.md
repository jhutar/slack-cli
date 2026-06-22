# Feature Specification: Extract Tokens from Slack Desktop App

**Feature Branch**: `002-extract-desktop-tokens`

**Created**: 2026-06-22

**Status**: Draft

**Input**: User description: "Add functionality to extract tokens from Slack desktop app that could be used to populate or update config file. App is installed as Flatpak with data in /home/jhutar/.var/app/com.slack.Slack."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Login via browser cookie (Priority: P1) *(already implemented)*

A user has access to Slack in their browser and wants to configure slack-cli by providing only the `d` cookie (xoxd token) and a workspace URL. The tool automatically fetches the xoxc token, verifies authentication, and writes both tokens to the config file.

**Why this priority**: This is the simplest authentication path — it requires only one value from the browser and handles everything else automatically.

**Independent Test**: Can be fully tested by running `slack-cli login mywork.slack.com --xoxd-token "xoxd-..."` and verifying the config file is written with valid tokens that authenticate against the Slack API.

**Acceptance Scenarios**:

1. **Given** a valid xoxd token and workspace URL, **When** the user runs the login command, **Then** the xoxc token is fetched automatically, authentication is verified, and both tokens are written to the config file.
2. **Given** no xoxd token is provided on the command line, **When** the user runs the login command, **Then** the tool prompts interactively for the xoxd token.
3. **Given** an expired or invalid xoxd token, **When** the user runs the login command, **Then** the tool reports a clear error that the token may be expired.
4. **Given** a workspace URL without the `.slack.com` suffix, **When** the user runs the login command, **Then** the tool appends `.slack.com` automatically.
5. **Given** the config file already exists with other settings, **When** the user runs the login command, **Then** the auth section is updated while preserving other sections (logging, cache).

---

### User Story 2 - Extract tokens from Flatpak Slack and update config (Priority: P1)

A user has the Slack desktop app installed as a Flatpak and wants to automatically extract their authentication tokens (xoxc + xoxd cookie) and write them to the slack-cli config file, so they can use slack-cli without manually copying tokens from a browser.

**Why this priority**: This is the core purpose of the feature — enabling a zero-browser-involvement authentication path for Flatpak Slack users. Without this, users must resort to the manual browser-based flow described in the README.

**Independent Test**: Can be fully tested by running the new command with a Flatpak Slack installation present, and verifying the config file is written with valid tokens that successfully authenticate against the Slack API.

**Acceptance Scenarios**:

1. **Given** the Slack desktop app (Flatpak) is closed and its local storage contains valid tokens, **When** the user runs the `slack-cli extract` command, **Then** tokens for all workspaces are discovered, the user selects a workspace, and the config file is written with the xoxc token and xoxd cookie for that workspace.
2. **Given** the config file already exists with tokens for a different workspace, **When** the user runs the `slack-cli extract` command, **Then** the existing config is preserved and updated with the new tokens (auth section is replaced, other sections remain intact).
3. **Given** the Slack app is running and the LevelDB database is locked, **When** the user runs the `slack-cli extract` command, **Then** the tool reports a clear error message telling the user to quit Slack first.

---

### User Story 3 - Extract tokens from standard Linux Slack install (Priority: P2)

A user has the Slack desktop app installed via the standard (non-Flatpak) method (`~/.config/Slack/`) and wants to extract tokens the same way.

**Why this priority**: Supports the traditional Linux installation path. Same functionality as P1 but for the conventional data directory.

**Independent Test**: Can be tested by running the `slack-cli extract` command on a system with a standard Slack installation at `~/.config/Slack/` and verifying correct token extraction and config writing.

**Acceptance Scenarios**:

1. **Given** a standard Linux Slack install with data at `~/.config/Slack/Local Storage/leveldb`, **When** the user runs the `slack-cli extract` command, **Then** tokens are extracted and the config file is updated identically to the Flatpak flow.
2. **Given** neither Flatpak nor standard Slack data directories exist, **When** the user runs the `slack-cli extract` command, **Then** the tool prints a clear error explaining that no Slack installation was found and lists the paths it searched.

---

### User Story 4 - List available workspaces without writing config (Priority: P3)

A user wants to see which workspaces are available in their Slack app without modifying any configuration.

**Why this priority**: Useful for discovery and debugging, but the core value is in actually writing the config (P1/P2).

**Independent Test**: Can be tested by running the command in list-only mode and verifying all workspaces from the Slack app are displayed with their names and URLs.

**Acceptance Scenarios**:

1. **Given** the Slack desktop app is closed and has multiple workspaces configured, **When** the user runs the `slack-cli extract` command with a list-only option, **Then** all workspace names and URLs are printed to stdout without modifying any files.

---

### Edge Cases

- What happens when the LevelDB database exists but contains no `localConfig_v2` key (corrupted or empty Slack data)?
- What happens when the cookie store is not accessible or the cookie decryption fails?
- What happens when the user has both a Flatpak and a standard Slack installation?
- What happens when a workspace token is present in LevelDB but the xoxd cookie has expired?

## Requirements *(mandatory)*

### Functional Requirements

#### Browser cookie login *(already implemented)*

- **FR-001**: System MUST accept a workspace URL and xoxd token (via command-line argument or interactive prompt) and automatically fetch the corresponding xoxc token.
- **FR-002**: System MUST verify the fetched tokens against the Slack API before writing to config.
- **FR-003**: System MUST write both tokens to the config file, preserving existing non-auth sections.
- **FR-004**: System MUST normalize workspace URLs by appending `.slack.com` if not already present.

#### Desktop app token extraction

- **FR-005**: System MUST extract xoxc tokens from the Slack desktop app's LevelDB local storage.
- **FR-006**: System MUST extract the xoxd cookie (the `d` cookie) from the Slack desktop app's cookie store.
- **FR-007**: System MUST support the Flatpak Slack data path (`~/.var/app/com.slack.Slack/config/Slack/`).
- **FR-008**: System MUST support the standard Linux Slack data path (`~/.config/Slack/`).
- **FR-009**: System MUST auto-detect which Slack installation path is available, preferring the Flatpak path first and falling back to the standard path only if the Flatpak path does not exist.
- **FR-010**: When multiple workspaces are found, system MUST present the user with a list and let them choose which workspace to configure. When exactly one workspace is found, system MUST select it automatically without prompting.
- **FR-011**: System MUST write the selected workspace's xoxc token and the xoxd cookie to the config file using the existing `write_config` mechanism.
- **FR-012**: System MUST verify extracted tokens by calling the Slack API (`auth.test`) before writing the config. Verification is mandatory — if the network is unavailable, the command MUST fail with an actionable error rather than writing unverified tokens.
- **FR-013**: System MUST provide a list-only mode that displays discovered workspaces without modifying files.
- **FR-014**: System MUST fail with a clear, actionable error message when the Slack app's database is locked (app is running), no Slack installation is found, or the database contents are unrecognizable.

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

## Clarifications

### Session 2026-06-22

- Q: Should the desktop app token extraction be a new subcommand or extend the existing `login` command? → A: New subcommand `slack-cli extract`, separate from `login`.
- Q: When only one workspace is found, should the tool auto-select it or still prompt? → A: Auto-select and skip the prompt when exactly one workspace is found.
- Q: Should token verification via `auth.test` be mandatory or skippable when offline? → A: Mandatory — always verify, fail if network is unavailable.

## Assumptions

- The Slack desktop app stores workspace tokens in a LevelDB database at a known, consistent path within its data directory.
- The `localConfig_v2` key structure used by the existing `slacktokens.py` library remains the format used by current Slack desktop versions.
- The user is on Linux (macOS support for this feature is out of scope for this specification, though the underlying `slacktokens.py` already handles macOS paths).
- The `d` cookie extraction requires either the Slack app to be closed or a read-only approach to the cookie store.
- The existing `write_config` function in `slack_cli/config.py` is sufficient for persisting extracted tokens.
- The `leveldb` and `pycookiecheat` Python packages (used by `slacktokens.py`) are acceptable dependencies for this feature.
