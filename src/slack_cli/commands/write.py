"""Write subcommand — send markdown-formatted messages to Slack.

Target is a Slack message link (replies into that thread, or starts a new
thread from the linked message), a bare channel/DM/group ID (new top-level
message), or a user ID (resolves the DM via conversations.open). Input
markdown is converted to Slack mrkdwn; @name/#channel mentions outside code
blocks are resolved to Slack refs, failing loud on unknown or ambiguous
names. On success the new message's permalink is printed. Replying to a
link also marks the corresponding activity-feed item read (best effort).
"""

import difflib
import re
import sys
from pathlib import Path

from slack_cli.api import SlackAPI, SlackAPIError
from slack_cli.cache import (
    DEFAULT_CACHE_DIR,
    DEFAULT_TTL,
    load_cache,
    save_cache,
)
from slack_cli.commands._shared import handle_api_error, require_tokens, workspace
from slack_cli.commands.activity import _fetch_feed
from slack_cli.commands.mark_read import _index, _match
from slack_cli.link import parse_slack_link
from slack_cli.mrkdwn import _split_code_blocks, to_mrkdwn

CHANNEL_ID_RE = re.compile(r"^[CDG][A-Z0-9]+$")
USER_ID_RE = re.compile(r"^U[A-Z0-9]+$")
TOKEN_RE = re.compile(r"[\w.-]+")

# @word -> Slack special mention ref.
SPECIAL_MENTIONS = {
    "channel": "<!channel>",
    "here": "<!here>",
    "everyone": "<!everyone>",
}


def run(args, config):
    """Send a markdown message and print the new message's permalink."""
    xoxc, xoxd = require_tokens(config)
    api = SlackAPI(xoxc, xoxd, user_agent=config.get("user_agent"))

    link, channel_id, thread_ts = _resolve_target(api, args.target)

    text = _read_body(args)
    if not text.strip():
        print("Error: message is empty.", file=sys.stderr)
        sys.exit(1)

    text = _resolve_mentions(api, config, text)
    text = to_mrkdwn(text)

    params = {"channel": channel_id, "text": text}
    if thread_ts:
        params["thread_ts"] = thread_ts
    try:
        resp = api.call("chat.postMessage", params)
    except SlackAPIError as e:
        _handle_send_error(e, channel_id)
    ts = resp.get("ts")
    if not ts:
        print(f"Error: chat.postMessage returned no ts: {resp}", file=sys.stderr)
        sys.exit(3)

    try:
        permalink = api.call(
            "chat.getPermalink", {"channel": channel_id, "message_ts": ts}
        ).get("permalink", "")
    except SlackAPIError as e:
        handle_api_error(e)
    if permalink:
        print(permalink)

    if link is not None:
        _mark_parent_read(api, link)


def _resolve_target(api, target):
    """Return (link, channel_id, thread_ts) for a link or channel/user ID.

    A link always means a reply: into the existing thread when thread_ts is
    present, otherwise a new thread rooted at the linked message. Returns
    link=None for bare channel and user ID targets.
    """
    try:
        link = parse_slack_link(target)
    except ValueError:
        link = None
    if link is not None:
        thread_ts = link.thread_ts if link.is_thread else link.message_ts
        return link, link.channel_id, thread_ts

    if CHANNEL_ID_RE.match(target):
        return None, target, None

    if USER_ID_RE.match(target):
        try:
            resp = api.call(
                "conversations.open", {"users": target, "return_im": "true"}
            )
        except SlackAPIError as e:
            handle_api_error(e)
        channel_id = resp.get("channel", {}).get("id")
        if not channel_id:
            print(f"Error: could not open a DM with {target}.", file=sys.stderr)
            sys.exit(3)
        return None, channel_id, None

    print(
        f"Error: invalid target '{target}'. Expected a Slack message link, "
        "a channel/DM/group ID (C.../D.../G...) or a user ID (U...).",
        file=sys.stderr,
    )
    sys.exit(1)


def _read_body(args):
    """Return message text from the positional arg, --file, or stdin."""
    if args.message:
        return args.message
    if args.file:
        try:
            return Path(args.file).read_text()
        except OSError as e:
            print(f"Error: cannot read {args.file}: {e}", file=sys.stderr)
            sys.exit(1)
    if not sys.stdin.isatty():
        return sys.stdin.read()
    print(
        "Error: no message. Pass text as an argument, --file PATH, or pipe "
        "it via stdin.",
        file=sys.stderr,
    )
    sys.exit(1)


def _resolve_mentions(api, config, text):
    """Resolve @user/#channel mentions to Slack refs outside code blocks.

    Uses the users/channels caches first; on unresolved mentions syncs via
    users.list / conversations.list and retries once before failing.
    """
    ttl = config.get("cache_ttl", DEFAULT_TTL)
    users_cache, users_path = _load_cache_file("users.json", ttl)
    channels_cache, channels_path = _load_cache_file("channels.json", ttl)
    user_idx = _reverse_index(users_cache.get("users", {}))
    channel_idx = _reverse_index(channels_cache.get("channels", {}))

    parts = _split_code_blocks(text)
    out = []
    for part, is_code in parts:
        if is_code:
            out.append(part)
            continue
        segment, unresolved = _resolve_segment(part, user_idx, channel_idx)
        if unresolved:
            user_idx = _reverse_index(_sync_users(api, users_cache, users_path))
            channel_idx = _reverse_index(
                _sync_channels(api, channels_cache, channels_path)
            )
            segment, unresolved = _resolve_segment(part, user_idx, channel_idx)
            if unresolved:
                _fail_unresolved(unresolved, user_idx, channel_idx)
        out.append(segment)
    return "".join(out)


def _load_cache_file(name, ttl):
    """Return (cache_dict, path) for a cache file under DEFAULT_CACHE_DIR."""
    path = DEFAULT_CACHE_DIR / name
    return load_cache(path, ttl=ttl) or {}, path


def _reverse_index(id_to_name):
    """Return lowercase name -> [ids] map from an id -> name dict."""
    idx = {}
    for _id, name in id_to_name.items():
        idx.setdefault(name.lower(), []).append(_id)
    return idx


def _sync_users(api, cache, path):
    """Refresh the users cache from users.list; return the id -> name dict."""
    members = api.call_paginated("users.list", {"limit": "200"}, "members")
    users = cache.setdefault("users", {})
    for m in members:
        uid = m.get("id")
        if not uid or m.get("deleted"):
            continue
        profile = m.get("profile", {})
        name = profile.get("display_name") or profile.get("real_name") or m.get("name")
        if name:
            users[uid] = name
    save_cache(path, cache)
    return users


def _sync_channels(api, cache, path):
    """Refresh the channels cache from conversations.list; return id -> name."""
    channels = api.call_paginated(
        "conversations.list",
        {"limit": "200", "types": "public_channel,private_channel"},
        "channels",
    )
    mapping = cache.setdefault("channels", {})
    for ch in channels:
        cid, name = ch.get("id"), ch.get("name")
        if cid and name:
            mapping[cid] = name
    save_cache(path, cache)
    return mapping


def _resolve_segment(text, user_idx, channel_idx):
    """Resolve mentions in one non-code segment.

    Returns (new_text, unresolved) where unresolved is a list of
    (kind, token, reason) tuples for mentions that could not be resolved.
    """
    out = []
    unresolved = []
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if ch in "@#" and not _is_mention_start(text, i):
            out.append(ch)
            i += 1
            continue
        if ch == "@":
            ref, consumed, token, reason = _match_mention(
                text, i, user_idx, SPECIAL_MENTIONS, "user"
            )
        elif ch == "#":
            ref, consumed, token, reason = _match_mention(
                text, i, channel_idx, {}, "channel"
            )
        else:
            out.append(ch)
            i += 1
            continue
        if ref is not None or token is None:
            out.append(ref if ref is not None else ch)
            i += consumed
        else:
            unresolved.append(("user" if ch == "@" else "channel", token, reason))
            out.append(text[i : i + consumed])
            i += consumed
    return "".join(out), unresolved


def _is_mention_start(text, i):
    """True when the @/# at position i plausibly starts a mention.

    Rejects positions glued to a word, dot, slash or another #/@ (emails,
    URLs, markdown headings), and requires a letter to follow.
    """
    if i > 0 and (text[i - 1].isalnum() or text[i - 1] in "._/#@"):
        return False
    return i + 1 < len(text) and text[i + 1].isalpha()


def _match_mention(text, i, idx, specials, kind):
    """Try to match a mention at text[i] ('@' or '#').

    Returns (ref, consumed, token, reason): ref is the Slack ref on success
    (token/reason None); on failure token is the raw word after the sigil
    and reason is 'unknown' or 'ambiguous'; (None, 1, None, None) means the
    sigil is literal text, not a mention.
    """
    rest = text[i + 1 :]
    token_m = TOKEN_RE.match(rest)
    token = token_m.group(0) if token_m else ""

    for word, ref in specials.items():
        if rest[: len(word)].lower() == word and not _is_word_at(rest, len(word)):
            return ref, 1 + len(word), None, None

    # Longest name first so '@John Doe' matches the full name, not '@John'.
    for name in sorted(idx, key=len, reverse=True):
        if rest[: len(name)].lower() == name and not _is_word_at(rest, len(name)):
            ids = idx[name]
            if len(ids) == 1:
                ref = f"<@{ids[0]}>" if kind == "user" else f"<#{ids[0]}>"
                return ref, 1 + len(name), None, None
            return None, 1 + len(token), token, "ambiguous"

    if token:
        return None, 1 + len(token), token, "unknown"
    return None, 1, None, None


def _is_word_at(text, pos):
    """True when text[pos] continues a word (mentions need a boundary there)."""
    return pos < len(text) and (text[pos].isalnum() or text[pos] in "_-")


def _fail_unresolved(unresolved, user_idx, channel_idx):
    """Print loud errors for unresolved mentions and exit 1."""
    lines = []
    for kind, token, reason in unresolved:
        idx = user_idx if kind == "user" else channel_idx
        sigil = "@" if kind == "user" else "#"
        close = difflib.get_close_matches(token.lower(), list(idx), n=3)
        hint = f" Did you mean: {', '.join(sigil + c for c in close)}?" if close else ""
        if reason == "ambiguous":
            lines.append(
                f"Error: ambiguous {kind} mention '{sigil}{token}' — "
                f"multiple matches share this name.{hint}"
            )
        else:
            lines.append(
                f"Error: unknown {kind} mention '{sigil}{token}'.{hint} "
                "Wrap it in backticks to send it literally."
            )
    print("\n".join(lines), file=sys.stderr)
    sys.exit(1)


def _handle_send_error(e, channel_id):
    """Print friendly message for a chat.postMessage failure and exit."""
    if e.error == "channel_not_found":
        print(
            f"Error: Channel {channel_id} not found. Check the ID or link.",
            file=sys.stderr,
        )
        sys.exit(3)
    if e.error == "not_in_channel":
        print(
            f"Error: Not in channel {channel_id}; cannot post there.",
            file=sys.stderr,
        )
        sys.exit(3)
    handle_api_error(e)


def _mark_parent_read(api, link):
    """Best-effort: mark the activity-feed item for the replied-to link read."""
    try:
        host, _ = workspace(api)
        entries = _fetch_feed(api, host)
    except SlackAPIError as e:
        print(f"Warning: could not fetch activity feed: {e.error}", file=sys.stderr)
        return
    entry = _match(_index(entries), link)
    if entry is None:
        print(
            "Warning: replied-to message not in unread activity feed; "
            "nothing to mark read.",
            file=sys.stderr,
        )
        return
    params = {"type": entry["type"], "key": entry["key"], "feed_ts": link.message_ts}
    if entry["type"] in ("dm", "mpdm"):
        params["ts"] = link.message_ts
    try:
        api.call_workspace(host, "activity.markRead", params)
    except SlackAPIError as e:
        print(f"Warning: failed to mark read: {e.error}", file=sys.stderr)
