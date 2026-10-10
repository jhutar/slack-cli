"""Mine subcommand — list your Slack activity over a date window.

Searches messages authored by you via search.messages (from:<name>,
username or display name — the modifier matches loosely, so results
are filtered by exact user id). The user: modifier is stale on
enterprise workspaces and is not used.

Default output is expanded: one entry per message. With --collapsed,
thread replies fold into one entry per thread (link to the thread
root) and your top-level messages fold into one entry per channel,
DM, or group DM (link to your earliest message there).
"""

import csv
import logging
import sys
import time
from datetime import datetime, timezone

from slack_cli.api import SlackAPI, SlackAPIError
from slack_cli.commands._shared import (
    attach_label,
    fmt_ts,
    handle_api_error,
    link,
    names_cache,
    require_tokens,
    resolve_channel,
    resolve_user,
    workspace,
)

logger = logging.getLogger(__name__)

# Search returns at most 200 results per page; cap total pages as a
# safety net so a very wide window can't loop forever.
SEARCH_COUNT = 200
MAX_PAGES = 25


def run(args, config):
    """Fetch your messages for the window and print them flat or grouped."""
    if args.days < 1:
        print("Error: --days must be at least 1", file=sys.stderr)
        sys.exit(1)

    xoxc, xoxd = require_tokens(config)
    api = SlackAPI(xoxc, xoxd, user_agent=config.get("user_agent"))
    cache, cache_path = names_cache(config)

    try:
        host, my_id = workspace(api)
        username = my_search_name(api, my_id)
        if not username:
            print(
                "Error: could not determine your Slack name for search",
                file=sys.stderr,
            )
            sys.exit(3)
        messages = fetch_my_messages(api, username, my_id, args.days)
        enrich_thread_info(api, messages)
    except SlackAPIError as e:
        handle_api_error(e)

    entries = group_collapsed(messages) if args.collapsed else expand(messages)
    for d in entries:
        attach_label(api, d, my_id, cache, cache_path)
        if d.get("kind") == "dm" and d.get("group"):
            d["kind"] = "group_dm"

    # One sort; display sections keep relative order.
    key = "latest_ts" if args.collapsed else "ts"
    ordered = sorted(entries, key=lambda d: float(d[key]), reverse=True)

    if args.csv:
        _write_csv(api, host, ordered, cache, cache_path)
    elif args.collapsed:
        threads = [d for d in ordered if d["kind"] == "thread"]
        rest = [d for d in ordered if d["kind"] != "thread"]
        sys.stdout.write(_format_collapsed(threads, rest, host, args.days))
    else:
        sys.stdout.write(_format_expanded(ordered, host, args.days))


def _is_dm_channel(cid):
    """True for 1:1 DM (D) and group DM/MPIM (G) channel ids."""
    return cid.startswith(("D", "G"))


def expand(messages):
    """Build one flat entry per message (expanded mode).

    Tags each message with its kind (thread replies count as
    "thread"), from_val, and to_val (both the message's own ts).
    """
    for m in messages:
        cid = _channel_id(m)
        m["channel_id"] = cid
        if _is_reply(m):
            m["kind"] = "thread"
        elif _is_dm_channel(cid):
            m["kind"] = "dm"
        else:
            m["kind"] = "channel"
        m["from_val"] = float(m["ts"])
        m["to_val"] = float(m["ts"])
    return messages


def group_collapsed(messages):
    """Group your messages into one entry per thread and per conversation.

    Replies fold into their thread (link to the root). Top-level
    messages fold into one entry per DM/group DM/channel; a channel
    entry excludes thread roots you also replied in, since the thread
    entry already links to them.
    """
    threads = {}
    chats = {}
    roots = {(_channel_id(m), m["thread_ts"]) for m in messages if _is_reply(m)}
    for m in messages:
        cid = _channel_id(m)
        m["channel_id"] = cid
        if _is_reply(m):
            entry = threads.setdefault(
                (cid, m["thread_ts"]),
                {
                    "kind": "thread",
                    "channel_id": cid,
                    "thread_ts": m["thread_ts"],
                    "latest_ts": 0.0,
                    "replies": 0,
                },
            )
            entry["latest_ts"] = max(entry["latest_ts"], float(m["ts"]))
            entry["replies"] += 1
        elif _is_dm_channel(cid) or (cid, m["ts"]) not in roots:
            entry = chats.get(cid)
            if entry is None:
                entry = chats[cid] = _new_chat(cid, m)
            else:
                _extend_chat(entry, m)
    for t in threads.values():
        t["from_val"] = float(t["thread_ts"])
        t["to_val"] = t["latest_ts"]
    for c in chats.values():
        c["from_val"] = c["first_val"]
        c["to_val"] = c["latest_ts"]
    return list(threads.values()) + list(chats.values())


def _new_chat(cid, m):
    """Fresh collapsed entry for a channel/DM/group DM conversation."""
    return {
        "kind": "dm" if _is_dm_channel(cid) else "channel",
        "channel_id": cid,
        "first_ts": m["ts"],
        "first_val": float(m["ts"]),
        "latest_ts": float(m["ts"]),
        "count": 1,
    }


def _extend_chat(entry, m):
    """Fold one more of your messages into a collapsed conversation entry."""
    v = float(m["ts"])
    if v < entry["first_val"]:
        entry["first_val"], entry["first_ts"] = v, m["ts"]
    entry["latest_ts"] = max(entry["latest_ts"], v)
    entry["count"] += 1


def my_search_name(api, user_id):
    """Look up a name to query search with (username, else display name).

    The from: search modifier matches loosely on this workspace, so
    results are filtered by exact user id in fetch_my_messages.
    """
    try:
        profile = api.call("users.profile.get", {"user": user_id})
        p = profile.get("profile") or {}
        return p.get("username") or p.get("display_name") or ""
    except SlackAPIError as e:
        logger.warning("users.profile.get failed: %s", e)
        return ""


def fetch_my_messages(api, username, my_user_id, days):
    """Fetch messages authored by you, newest first, within the window."""
    cutoff = time.time() - days * 86400
    params = {
        "query": f"from:{username}",
        "count": str(SEARCH_COUNT),
        "sort": "ts",
        "sort_dir": "desc",
    }
    messages = []
    for _ in range(MAX_PAGES):
        resp = api.call("search.messages", params)
        raw = (resp.get("messages") or {}).get("matches", [])
        messages.extend(m for m in raw if _mine(m, my_user_id, cutoff))
        if not raw or float(raw[-1].get("ts", 0)) < cutoff:
            break
        cursor = (resp.get("response_metadata") or {}).get("next_cursor", "")
        if not cursor:
            break
        params["cursor"] = cursor
    return messages


def _mine(m, my_user_id, cutoff):
    """True if m is a channel/DM/group DM message by me within the window.

    Channels come back as type "message", 1:1 DMs as "im", group DMs
    as "mpim".
    """
    return (
        m.get("type") in ("message", "im", "mpim")
        and m.get("user") == my_user_id
        and float(m.get("ts", 0)) >= cutoff
    )


def _channel_id(m):
    """Extract the channel id from a search match (string or object)."""
    cid = m.get("channel")
    return cid.get("id") if isinstance(cid, dict) else cid


def _is_reply(m):
    """True if m is a reply to another message (thread_ts set, != own ts)."""
    return m.get("thread_ts") and m["thread_ts"] != m["ts"]


def enrich_thread_info(api, messages):
    """Fill thread_ts for messages where search returned none.

    search.messages omits thread_ts on this workspace, so look each
    message up individually. Failures degrade to top-level (comment).
    """
    for m in messages:
        if not m.get("thread_ts"):
            m["thread_ts"] = _thread_ts_of(api, _channel_id(m), m["ts"])


def _thread_ts_of(api, cid, ts):
    """Find thread_ts for one message; None if top-level or lookup fails.

    Tries conversations.history (single-message window), falls back to
    conversations.replies if the message is not in the channel's main
    history.
    """
    try:
        resp = api.call(
            "conversations.history",
            {
                "channel": cid,
                "oldest": ts,
                "latest": ts,
                "inclusive": "true",
                "limit": "1",
            },
        )
        for h in resp.get("messages", []):
            if h.get("ts") == ts and h.get("thread_ts"):
                return h["thread_ts"]
        resp = api.call(
            "conversations.replies",
            {"channel": cid, "ts": ts, "limit": "1"},
        )
        for h in resp.get("messages", []):
            if h.get("thread_ts"):
                return h["thread_ts"]
    except SlackAPIError as e:
        logger.warning("thread lookup failed for %s in %s: %s", ts, cid, e)
    return None


def entry_link(host, d):
    """Permalink for an entry (thread root link or message link).

    Collapsed thread entries link to the root with the thread view
    param so Slack opens the thread directly. Collapsed conversations
    link to your earliest message; individual messages link to
    themselves (thread replies included — no thread param).
    """
    if d["kind"] == "thread" and "ts" not in d:
        root = d["thread_ts"]
        return link(host, d["channel_id"], root, root)
    ts = d.get("ts") or d.get("first_ts")
    return link(host, d["channel_id"], ts)


def _from_where(api, d, cache, cache_path):
    """CSV from_where field: #channel, #channel@thread_ts, or DM names."""
    if d["channel_id"].startswith(("D", "G")):
        names = [resolve_user(api, u, cache, cache_path) for u in d["members"]]
        return ", ".join(names)
    chan = f"#{resolve_channel(api, d['channel_id'], cache, cache_path)}"
    if d["kind"] == "thread":
        return f"{chan}@{d['thread_ts']}"
    return chan


def iso_utc(ts):
    """Format a Slack ts as ISO 8601 UTC with second precision."""
    return datetime.fromtimestamp(float(ts), tz=timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )


def _write_csv(api, host, ordered, cache, cache_path):
    """Print the CSV table: header row plus one row per entry."""
    w = csv.writer(sys.stdout, lineterminator="\n")
    w.writerow(["link", "source_type", "from_where", "from_time", "to_time"])
    for d in ordered:
        w.writerow(
            [
                entry_link(host, d),
                d["kind"],
                _from_where(api, d, cache, cache_path),
                iso_utc(d["from_val"]),
                iso_utc(d["to_val"]),
            ]
        )


def _heading(days):
    """Top line: '# Your Slack activity — last N days'."""
    return f"# Your Slack activity — last {days} day{'s' if days != 1 else ''}"


def _format_expanded(ordered, host, days):
    """Build the flat listing: one entry per message, newest first."""
    lines = [_heading(days), "", f"## Your messages ({len(ordered)})", ""]
    if not ordered:
        lines.append("No messages found in this window.")
        return "\n".join(lines).rstrip("\n") + "\n"
    for i, m in enumerate(ordered, 1):
        lines.append(f"{i}. {m['label']} · {fmt_ts(float(m['ts']))}")
        lines.append(f"   {entry_link(host, m)}")
    return "\n".join(lines).rstrip("\n") + "\n"


def _format_collapsed(threads, rest, host, days):
    """Build the grouped listing: thread entries, then conversation entries."""
    lines = [_heading(days), ""]
    if not (threads or rest):
        lines.append("No messages found in this window.")
        return "\n".join(lines).rstrip("\n") + "\n"

    if threads:
        lines.append(f"## Threads you participated in ({len(threads)})")
        lines.append("")
        for i, t in enumerate(threads, 1):
            extra = (
                f" · {t['replies']} repl{'y' if t['replies'] == 1 else 'ies'} by you"
                if t["replies"] > 1
                else ""
            )
            lines.append(
                f"{i}. {t['label']} · you, last {fmt_ts(t['latest_ts'])}{extra}"
            )
            lines.append(f"   {entry_link(host, t)}")
        lines.append("")

    if rest:
        lines.append(f"## Your messages in channels and DMs ({len(rest)})")
        lines.append("")
        for i, c in enumerate(rest, 1):
            if c["count"] > 1:
                mid = f"you, first {fmt_ts(c['first_val'])} · {c['count']} by you"
            else:
                mid = fmt_ts(c["first_val"])
            lines.append(f"{i}. {c['label']} · {mid}")
            lines.append(f"   {entry_link(host, c)}")
        lines.append("")

    return "\n".join(lines).rstrip("\n") + "\n"
