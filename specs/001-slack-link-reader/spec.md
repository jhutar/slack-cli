# Feature Specification: Slack Link Reader

**Feature Branch**: `001-slack-link-reader`

**Created**: 2026-06-21

**Status**: Draft

**Input**: User description: "CLI tool to translate Slack links to readable message content on stdout"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Fetch a single channel message by link (Priority: P1)

A user or AI agent has a Slack message link and wants to see the content
of that message as readable Markdown on stdout. They copy the link from
Slack (right-click → "Copy link") and pass it to the CLI tool.

**Why this priority**: This is the most basic operation — resolving a
single Slack link to its content. All other stories build on this
capability.

**Independent Test**: Run the tool with a valid Slack message link and
verify that stdout contains the message author, timestamp, and content
formatted as Markdown.

**Acceptance Scenarios**:

1. **Given** a valid Slack channel message link, **When** the user runs
   the tool with that link, **Then** stdout contains the message with
   author display name, date/time, and content in Markdown format.
2. **Given** a valid Slack channel message link, **When** the message
   contains code blocks, links, bold, and italic text, **Then** the
   output preserves code blocks and links in standard Markdown syntax,
   and renders bold/italic in standard Markdown.
3. **Given** a valid Slack channel message link to a message that
   mentions other users (e.g. `<@U12345>`), **When** the user runs the
   tool, **Then** mentions are resolved to display names in the output.
4. **Given** an invalid or malformed Slack link, **When** the user runs
   the tool, **Then** the tool exits with a non-zero exit code and
   prints a clear error message to stderr explaining the link format
   is not recognized.

---

### User Story 2 - Fetch a thread by link (Priority: P1)

A user has a link to a Slack thread (or a message that started a thread)
and wants to see the entire thread conversation.

**Why this priority**: Thread reading is equally fundamental — many Slack
conversations happen in threads, and the user explicitly needs this.

**Independent Test**: Run the tool with a Slack thread link and verify
that stdout contains all thread replies in chronological order with
proper numbering.

**Acceptance Scenarios**:

1. **Given** a Slack link that points to a thread (URL contains
   `thread_ts` parameter), **When** the user runs the tool, **Then**
   stdout contains all messages in that thread in chronological order.
2. **Given** a Slack link to a message that has thread replies, **When**
   the user runs the tool, **Then** stdout contains the parent message
   followed by all replies.
3. **Given** a thread with 50 replies, **When** the user runs the tool,
   **Then** all 50 replies are included in the output (pagination is
   handled automatically).

---

### User Story 3 - Fetch follow-up messages after a link (Priority: P2)

A user wants to see not just the linked message but also the N messages
that came after it in the channel, or all messages within a time window
after it. If any of those messages have threads, the thread content is
included inline.

**Why this priority**: This enables capturing a conversation segment,
which is the primary use case for feeding context to an AI agent.

**Independent Test**: Run the tool with a message link and a
`--after` flag (count or duration) and verify the correct number of
follow-up messages appear with threads inlined.

**Acceptance Scenarios**:

1. **Given** a channel message link and `--after 5`, **When** the user
   runs the tool, **Then** stdout contains the linked message plus the
   next 5 messages in that channel, in chronological order.
2. **Given** a channel message link and `--after 2H`, **When** the user
   runs the tool, **Then** stdout contains the linked message plus all
   messages posted in the next 2 hours in that channel.
3. **Given** a channel message link and `--after 30M`, **When** the user
   runs the tool, **Then** stdout contains the linked message plus all
   messages posted in the next 30 minutes.
4. **Given** follow-up messages where message 3 has a thread, **When**
   the tool renders the output, **Then** the thread replies appear
   inline as sub-messages (e.g., 3.1, 3.2, 3.3) before message 4
   continues.
5. **Given** a channel message link and `--after 5`, **When** fewer than
   5 follow-up messages exist, **Then** the tool outputs all available
   messages and does not error.
6. **Given** `--after` is used with a thread link, **When** the user
   runs the tool, **Then** the tool outputs an error to stderr
   explaining that `--after` only applies to channel messages.

---

### User Story 4 - Fetch a direct message (DM) by link (Priority: P2)

A user has a link to a direct message (1:1 or group DM) and wants to
read it via the CLI.

**Why this priority**: DMs are a common source of context that users
want to feed to AI agents. The Slack API treats DMs as conversations,
so this shares most infrastructure with channel messages.

**Independent Test**: Run the tool with a DM link and verify the message
content appears on stdout.

**Acceptance Scenarios**:

1. **Given** a valid Slack DM link, **When** the user runs the tool,
   **Then** stdout contains the DM content with author and timestamp.
2. **Given** a DM link with `--after N`, **When** the user runs the
   tool, **Then** the follow-up messages from the DM conversation are
   included.
3. **Given** a DM link that the authenticated user does not have access
   to, **When** the user runs the tool, **Then** the tool exits with a
   non-zero code and a clear error message on stderr.

---

### Edge Cases

- What happens when the xoxc or xoxd token is missing or expired? The
  tool MUST fail immediately with a message naming the specific
  environment variable(s) that need to be set.
- What happens when the session tokens are invalidated (e.g., enterprise
  Slack logs out the session due to wrong User-Agent)? The tool reports
  the authentication failure and suggests checking the User-Agent
  configuration.
- What happens when the message has been deleted? The tool reports the
  message is not found or inaccessible.
- What happens when the channel is private and the token lacks access?
  The tool reports an access error with the specific channel.
- What happens when a message contains only attachments/files with no
  text? The tool outputs a placeholder indicating an attachment with
  the filename if available.
- What happens when Slack API rate limits are hit? The tool retries
  with appropriate backoff or fails with a clear rate-limit message.
- What happens with very long threads (hundreds of replies)? The tool
  paginates through the API automatically and outputs all messages.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The tool MUST accept a Slack message link as a positional
  argument.
- **FR-002**: The tool MUST parse Slack links in the format
  `https://<workspace>.slack.com/archives/<channel_id>/p<timestamp>`
  and extract the workspace, channel ID, and message timestamp.
- **FR-003**: The tool MUST detect thread links (containing `thread_ts`
  query parameter) and fetch the full thread.
- **FR-004**: The tool MUST support an `--after` option that accepts
  either a positive integer (number of messages) or a duration string
  (e.g., `30M`, `2H`) to fetch follow-up messages.
- **FR-005**: The tool MUST convert Slack's mrkdwn format to standard
  Markdown, preserving at minimum: code blocks (inline and fenced),
  links, bold, italic, and strikethrough.
- **FR-006**: The tool MUST resolve user mentions (`<@U...>`) to
  display names in the output.
- **FR-007**: The tool MUST resolve channel references (`<#C...>`) to
  channel names in the output.
- **FR-008**: The tool MUST output messages to stdout in Markdown format
  with author, date/time, and content for each message.
- **FR-009**: The tool MUST output errors and diagnostics to stderr.
- **FR-010**: The tool MUST exit with code 0 on success and non-zero on
  failure.
- **FR-011**: The tool MUST handle Slack API pagination transparently
  when fetching threads or follow-up messages.
- **FR-012**: The tool MUST authenticate using a pair of Slack
  session-based tokens: an `xoxc` token (client token) and an `xoxd`
  token (cookie token), both read from environment variables.
- **FR-012a**: The tool MUST support a configurable User-Agent header
  via environment variable, required for enterprise Slack workspaces
  that reject non-browser API requests and invalidate sessions.
- **FR-012b**: The tool MUST fail immediately with a clear error if
  either the xoxc or xoxd token is missing, explaining which
  environment variables need to be set.
- **FR-013**: The tool MUST support DM links (channel IDs starting with
  `D` for 1:1 DMs and `G` for group DMs) using the same interface.
- **FR-014**: When fetching follow-up channel messages that contain
  threads, the tool MUST inline the thread replies as sub-messages
  (numbered N.1, N.2, etc.) maintaining chronological context.
- **FR-015**: The CLI MUST include a `--help` flag that documents all
  options and shows usage examples.
- **FR-016**: The CLI command structure MUST use subcommands (e.g.,
  `slack-cli read <link>`) to allow future extension with write
  operations without breaking the interface.

### Key Entities

- **Message**: The core unit — has an author, timestamp, text content,
  and optionally belongs to a thread. May contain mentions, links, code
  blocks, and attachments.
- **Thread**: An ordered sequence of messages that are replies to a
  parent message. Identified by the parent message's timestamp.
- **Channel**: A Slack channel, DM, or group DM identified by its ID.
  The tool does not manage channels but needs to resolve channel names
  for display.
- **User**: A Slack workspace member identified by user ID. The tool
  resolves user IDs to display names for output.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Users can retrieve the content of any accessible Slack
  message by providing its link, in a single command invocation.
- **SC-002**: Output is valid Markdown that renders correctly when
  passed to any standard Markdown viewer or processor.
- **SC-003**: Thread conversations are fully captured with no missing
  replies, regardless of thread length.
- **SC-004**: The output of a channel segment (using `--after`) can be
  directly piped to another CLI tool or used as input to an AI agent
  without manual editing or reformatting.
- **SC-005**: The tool provides clear, actionable feedback for every
  failure condition — the user never sees a raw stack trace or
  cryptic error.
- **SC-006**: A new user can install, configure authentication, and
  successfully fetch their first message within 5 minutes by following
  the `--help` output.

## Assumptions

- The user has valid Slack session tokens (xoxc + xoxd pair) obtained
  from an authenticated browser session. These are session-based
  browser tokens, not OAuth tokens — they provide user-level access
  without going through the OAuth app registration flow.
- The Slack workspace uses standard link formats as documented by
  Slack's API.
- Slack's mrkdwn formatting is the internal message format returned
  by the API (confirmed by research — Slack does not use HTML or
  standard Markdown internally).
- Enterprise Slack workspaces may require a browser-like User-Agent
  header to avoid session invalidation. The tool supports configuring
  this via environment variable.
- The tool is intended for use on Linux/macOS from a terminal. Windows
  support is not a goal for this iteration.
- Rate limiting from the Slack API is handled with reasonable retry
  behavior, but the tool is not designed for bulk export of thousands
  of messages.
- The `--after` duration format supports minutes (`M`) and hours (`H`)
  as the most practical units for conversation segments. Days or
  seconds are not supported in this iteration.
