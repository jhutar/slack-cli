"""Mine subcommand — list discussions you participated in over a date window.

Searches messages authored by you via search.messages (from:<name>,
username or display name — the modifier matches loosely, so results
are filtered by exact user id). The user: modifier is stale on
enterprise workspaces and is not used.

Groups results into discussions: replies in threads collapse to one
entry per thread (link to the thread root), top-level messages in
channels or DMs get a permalink to the message itself.
"""

import logging
import sys
import time

from slack_cli.api import SlackAPI, SlackAPIError
from slack_cli.commands._shared import (
    attach_label,
    fmt_ts,
    handle_api_error,
    link,
    names_cache,
    require_tokens,
    workspace,
)

logger = logging.getLogger(__name__)

# Search returns at most 200 results per page; cap total pages as a
# safety net so a very wide window can't loop forever.
SEARCH_COUNT = 200
MAX_PAGES = 25


def run(args, config):
    """Fetch your messages for the window and print grouped discussions."""
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

    threads, comments = group_discussions(messages)
    for d in threads + comments:
        attach_label(api, d, my_id, cache, cache_path)

    # One sort; display sections keep relative order.
    ordered = sorted(threads + comments, key=lambda d: d["latest_ts"], reverse=True)
    threads = [d for d in ordered if "thread_ts" in d]
    comments = [d for d in ordered if "thread_ts" not in d]

    if args.csv:
        sys.stdout.write(
            "\n".join(discussion_link(host, d) for d in ordered)
            + ("\n" if ordered else "")
        )
    else:
        sys.stdout.write(_format(threads, comments, host, args.days))


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
    """True if m is a channel/DM message by me within the window.

    DM messages come back as type "im", channels as "message".
    """
    return (
        m.get("type") in ("message", "im")
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


def group_discussions(messages):
    """Split messages into threads (one entry per thread) and comments.

    A reply folds into its thread with a link to the thread root. A
    top-level message is its own discussion, except when it is the
    root of a thread you also replied in — the thread entry already
    links to it.
    """
    threads = {}
    roots = {(_channel_id(m), m["thread_ts"]) for m in messages if _is_reply(m)}
    comments = []
    for m in messages:
        cid = _channel_id(m)
        if _is_reply(m):
            key = (cid, m["thread_ts"])
            entry = threads.setdefault(
                key,
                {
                    "channel_id": cid,
                    "thread_ts": m["thread_ts"],
                    "latest_ts": 0.0,
                    "replies": 0,
                },
            )
            entry["latest_ts"] = max(entry["latest_ts"], float(m["ts"]))
            entry["replies"] += 1
        elif (cid, m["ts"]) not in roots:
            comments.append(
                {"channel_id": cid, "ts": m["ts"], "latest_ts": float(m["ts"])}
            )
    return list(threads.values()), comments


def discussion_link(host, d):
    """Permalink for a discussion entry (thread root link or message link).

    Threads link to the root with the thread view param so Slack opens
    the thread directly.
    """
    if "thread_ts" in d:
        root = d["thread_ts"]
        return link(host, d["channel_id"], root, root)
    return link(host, d["channel_id"], d["ts"])


def _format(threads, comments, host, days):
    """Build the output listing of your discussions."""
    lines = [f"# Your Slack activity — last {days} day{'s' if days != 1 else ''}", ""]
    if not (threads or comments):
        return "\n".join(lines + ["No messages found in this window."]) + "\n"

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
            lines.append(f"   {discussion_link(host, t)}")
        lines.append("")

    if comments:
        lines.append(f"## Your messages in channels and DMs ({len(comments)})")
        lines.append("")
        for i, c in enumerate(comments, 1):
            lines.append(f"{i}. {c['label']} · {fmt_ts(c['ts'])}")
            lines.append(f"   {discussion_link(host, c)}")
        lines.append("")

    return "\n".join(lines).rstrip("\n") + "\n"
