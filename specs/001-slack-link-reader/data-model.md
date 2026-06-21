# Data Model: Slack Link Reader

## Entities

### SlackLink

Parsed representation of a Slack URL.

| Field | Type | Description |
|-------|------|-------------|
| workspace | str | Workspace subdomain (e.g., "mycompany") |
| channel_id | str | Channel/DM ID (e.g., "C01234567", "D01234567") |
| message_ts | str | Message timestamp in Slack format "1234567890.123456" |
| thread_ts | str or None | Thread timestamp if link points to a thread |
| is_thread | bool | Whether this link is a thread link |
| is_reply | bool | Whether this link points to a specific reply in a thread (thread_ts differs from message_ts) |

**Source format**: `https://<workspace>.slack.com/archives/<channel_id>/p<timestamp>[?thread_ts=<ts>&cid=<channel_id>]`

**Timestamp conversion**: The `p` prefix is removed and a dot is inserted
before the last 6 digits. `p1234567890123456` → `1234567890.123456`.

### Message

A single Slack message with resolved metadata.

| Field | Type | Description |
|-------|------|-------------|
| text | str | Message text in mrkdwn format (raw from API) |
| user_id | str | Author's Slack user ID |
| user_name | str | Author's resolved display name |
| ts | str | Message timestamp (Slack format) |
| datetime | datetime | Parsed timestamp as datetime object |
| thread_ts | str or None | Thread parent timestamp (if message is in a thread) |
| reply_count | int | Number of thread replies (0 if no thread) |
| replies | list[Message] | Thread replies (populated when thread is fetched) |
| files | list[FileRef] | Attached files metadata |

### FileRef

Minimal file attachment metadata.

| Field | Type | Description |
|-------|------|-------------|
| name | str | Filename |
| filetype | str | File type/extension |
| url | str or None | Download URL (may require auth) |

### UserInfo

Cached user information.

| Field | Type | Description |
|-------|------|-------------|
| user_id | str | Slack user ID |
| display_name | str | Display name (falls back to real_name, then username) |

### ChannelInfo

Cached channel information.

| Field | Type | Description |
|-------|------|-------------|
| channel_id | str | Channel ID |
| name | str | Channel name (without # prefix) |
| is_im | bool | Whether this is a 1:1 DM |
| is_mpim | bool | Whether this is a group DM |

## Relationships

```
SlackLink ──parses-to──> channel_id + message_ts
                              │
                              ▼
                     conversations.history
                     conversations.replies
                              │
                              ▼
                        list[Message]
                              │
                    ┌─────────┴─────────┐
                    ▼                   ▼
              user_id refs        channel refs
              <@U123>              <#C123|name>
                    │                   │
                    ▼                   ▼
              users.info         conversations.info
                    │                   │
                    ▼                   ▼
              UserInfo            ChannelInfo
              (cached)            (cached)
```

## Cache File Formats

### users.json

```json
{
  "_meta": {
    "updated_at": "2026-06-21T14:30:00Z"
  },
  "users": {
    "U01234567": "Alice Smith",
    "U98765432": "Bob Jones"
  }
}
```

### channels.json

```json
{
  "_meta": {
    "updated_at": "2026-06-21T14:30:00Z"
  },
  "channels": {
    "C01234567": "general",
    "C98765432": "engineering"
  }
}
```

## Validation Rules

- `channel_id` MUST match pattern `^[CDGW][A-Z0-9]+$`
- `message_ts` MUST match pattern `^\d+\.\d{6}$`
- `thread_ts` when present MUST match same pattern as `message_ts`
- `workspace` MUST be a non-empty alphanumeric string (may contain hyphens)
- Cache TTL is 24 hours by default; expired cache is refreshed on next use
- Missing cache entries are fetched on demand and added to cache
