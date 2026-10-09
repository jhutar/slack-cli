"""Mine subcommand — list discussions you participated in over a date window.

Searches messages authored by you via search.messages (user:<name>,
username or display name — the modifier matches loosely, so results
are filtered by exact user id) and groups them into discussions:
replies in threads collapse to one entry per thread (link to the
thread root), top-level messages in channels or DMs get a permalink
to the message itself.
"""

import logging
import sys
import time
from datetime import datetime, timezone
from urllib.parse import urlparse

from slack_cli.api import SlackAPI, SlackAPIError
from slack_cli.cache import (
    DEFAULT_CACHE_DIR,
    DEFAULT_TTL,
    load_cache,
    resolve_channel,
)
from slack_cli.commands.activity import _resolve_dm

logger = logging.getLogger(__name__)

# Search returns at most 200 results per page; cap total pages as a
# safety net so a very wide window can't loop forever.
SEARCH_COUNT = 200
MAX_PAGES = 25


def run(args, config):
    """Fetch your messages for the window and print grouped discussions."""
    xoxc = config.get("xoxc_token")
    xoxd = config.get("xoxd_token")
    missing = []
    if not xoxc:
        missing.append("SLACK_CLI_XOXC_TOKEN")
    if not xoxd:
        missing.append("SLACK_CLI_XOXD_TOKEN")
    if missing:
        print(
            f"Error: {' and '.join(missing)} not set. "
            f"Set in environment or in ~/.config/slack-cli/config.toml",
            file=sys.stderr,
        )
        sys.exit(2)

    if args.days < 1:
        print("Error: --days must be at least 1", file=sys.stderr)
        sys.exit(1)

    api = SlackAPI(xoxc, xoxd, user_agent=config.get("user_agent"))

    cache_ttl = config.get("cache_ttl", DEFAULT_TTL)
    names_cache_path = DEFAULT_CACHE_DIR / "names.json"
    names_cache = load_cache(names_cache_path, ttl=cache_ttl) or {}

    try:
        auth = api.call("auth.test")
        host = urlparse(auth.get("url", "")).netloc or "slack.com"
        my_user_id = auth.get("user_id", "")
        username = _my_search_name(api, my_user_id)
        if not username:
            print(
                "Error: could not determine your Slack name for search",
                file=sys.stderr,
            )
            sys.exit(3)

        cutoff = time.time() - args.days * 86400
        messages = _fetch_my_messages(api, username, my_user_id, cutoff)
    except SlackAPIError as e:
        _handle_api_error(e)

    threads, comments = _group_discussions(messages)

    for d in threads + comments:
        cid = d["channel_id"]
        if cid.startswith("D"):
            _resolve_dm(api, d, my_user_id, names_cache, names_cache_path)
        else:
            d["label"] = f"#{resolve_channel(api, cid, names_cache, names_cache_path)}"

    threads.sort(key=lambda d: d["latest_ts"], reverse=True)
    comments.sort(key=lambda d: d["latest_ts"], reverse=True)

    if args.csv:
        all_discussions = sorted(
            threads + comments, key=lambda d: d["latest_ts"], reverse=True
        )
        sys.stdout.write(
            "\n".join(_discussion_link(host, d) for d in all_discussions)
            + ("\n" if all_discussions else "")
        )
    else:
        sys.stdout.write(_format(threads, comments, host, args.days))


def _my_search_name(api, user_id):
    """Look up a name to query search with (username, else display name).

    The user: search modifier matches loosely on this workspace, so
    results are filtered by exact user id in _fetch_my_messages.
    """
    try:
        profile = api.call("users.profile.get", {"user": user_id})
        p = profile.get("profile") or {}
        return p.get("username") or p.get("display_name") or ""
    except SlackAPIError as e:
        logger.warning("users.profile.get failed: %s", e)
        return ""


def _fetch_my_messages(api, username, my_user_id, cutoff):
    """Fetch messages authored by you, newest first, down to the cutoff."""
    params = {
        "query": f"user:{username}",
        "count": str(SEARCH_COUNT),
        "sort": "ts",
        "sort_dir": "desc",
    }
    messages = []
    for _ in range(MAX_PAGES):
        resp = api.call("search.messages", params)
        raw = (resp.get("messages") or {}).get("matches", [])
        batch = [
            m
            # DM messages come back as type "im", channels as "message".
            for m in raw
            if m.get("type") in ("message", "im")
            and m.get("user") == my_user_id
            and float(m.get("ts", 0)) >= cutoff
        ]
        messages.extend(batch)
        if raw and float(raw[-1].get("ts", 0)) < cutoff:
            break
        cursor = (resp.get("response_metadata") or {}).get("next_cursor", "")
        if not cursor:
            break
        params["cursor"] = cursor
    return messages


def _group_discussions(messages):
    """Split messages into threads (one entry per thread) and comments.

    A reply (thread_ts set and != own ts) folds into its thread with a
    link to the thread root. A top-level message is its own discussion.
    """
    threads = {}
    comments = []
    for m in messages:
        ts = float(m["ts"])
        cid = m.get("channel")
        cid = cid.get("id") if isinstance(cid, dict) else cid
        thread_ts = m.get("thread_ts")
        if thread_ts and thread_ts != m["ts"]:
            key = (cid, thread_ts)
            entry = threads.setdefault(
                key,
                {
                    "channel_id": cid,
                    "thread_ts": thread_ts,
                    "latest_ts": 0.0,
                    "replies": 0,
                },
            )
            entry["latest_ts"] = max(entry["latest_ts"], ts)
            entry["replies"] += 1
        else:
            comments.append({"channel_id": cid, "ts": m["ts"], "latest_ts": ts})
    return list(threads.values()), comments


def _discussion_link(host, d):
    """Permalink for a discussion entry (thread root link or message link)."""
    if "thread_ts" in d:
        # Link to the thread root with the thread view param so Slack
        # opens the thread directly.
        root = str(d["thread_ts"]).replace(".", "")
        return f"https://{host}/archives/{d['channel_id']}/p{root}?thread_ts={root}"
    return f"https://{host}/archives/{d['channel_id']}/p{str(d['ts']).replace('.', '')}"


def _fmt_ts(ts):
    """Format a Slack ts as 'YYYY-MM-DD HH:MM UTC'."""
    return datetime.fromtimestamp(float(ts), tz=timezone.utc).strftime(
        "%Y-%m-%d %H:%M UTC"
    )


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
                f"{i}. {t['label']} · you, last {_fmt_ts(t['latest_ts'])}{extra}"
            )
            lines.append(f"   {_discussion_link(host, t)}")
        lines.append("")

    if comments:
        lines.append(f"## Your messages in channels and DMs ({len(comments)})")
        lines.append("")
        for i, c in enumerate(comments, 1):
            lines.append(f"{i}. {c['label']} · {_fmt_ts(c['ts'])}")
            lines.append(f"   {_discussion_link(host, c)}")
        lines.append("")

    return "\n".join(lines).rstrip("\n") + "\n"


def _handle_api_error(e):
    """Print a friendly message for known Slack API errors and exit."""
    error = e.error
    messages = {
        "invalid_auth": "Error: Authentication failed. Check your xoxc/xoxd tokens.",
        "token_revoked": "Error: Token has been revoked. Obtain new session tokens.",
        "ratelimited": "Error: Rate limited by Slack API. Try again later.",
        "account_inactive": (
            "Error: Account inactive or session invalidated. "
            "Check your User-Agent configuration (SLACK_CLI_USER_AGENT)."
        ),
    }
    msg = messages.get(error, f"Error: Slack API error: {error}")
    print(msg, file=sys.stderr)
    sys.exit(2 if error in messages else 3)
