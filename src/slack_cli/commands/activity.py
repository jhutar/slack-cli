"""Activity subcommand — list unread items from Slack's activity feed.

Uses the workspace /api/activity.feed endpoint (same source as Slack's
Activity panel) instead of search + per-DM conversation scans. Lists
mentions, active threads, and DMs/group DMs needing a response, each
with an archives permalink usable by `slack-cli read`.
"""

import logging
import sys
from datetime import datetime, timezone
from urllib.parse import urlparse

from slack_cli.api import SlackAPI, SlackAPIError
from slack_cli.cache import (
    DEFAULT_CACHE_DIR,
    DEFAULT_TTL,
    load_cache,
    resolve_channel,
    resolve_user,
    save_cache,
)

logger = logging.getLogger(__name__)

# Feed item types needing a response; invites, list noise, reactions excluded.
FEED_TYPES = ",".join(
    (
        "at_user",
        "at_user_group",
        "at_channel",
        "at_everyone",
        "keyword",
        "unjoined_channel_mention",
        "thread_v2",
        "dm",
        "mpdm",
    )
)
MENTION_TYPES = {
    "at_user",
    "at_user_group",
    "at_channel",
    "at_everyone",
    "keyword",
    "unjoined_channel_mention",
}
# Server rejects limit above 50.
FEED_LIMIT = 50
MAX_PAGES = 10


def run(args, config):
    """Fetch unread activity feed items and print them grouped by type."""
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

    api = SlackAPI(xoxc, xoxd, user_agent=config.get("user_agent"))

    cache_ttl = config.get("cache_ttl", DEFAULT_TTL)
    names_cache_path = DEFAULT_CACHE_DIR / "names.json"
    names_cache = load_cache(names_cache_path, ttl=cache_ttl) or {}

    try:
        auth = api.call("auth.test")
        host = urlparse(auth.get("url", "")).netloc or "slack.com"
        my_user_id = auth.get("user_id", "")
        items = _fetch_feed(api, host)
    except SlackAPIError as e:
        _handle_api_error(e)

    mentions, threads, dms = _classify(items)

    for m in mentions:
        m["author"] = resolve_user(
            api, m.pop("author_id"), names_cache, names_cache_path
        )
        if m["channel_id"].startswith("D"):
            _resolve_dm(api, m, my_user_id, names_cache, names_cache_path)
        else:
            m["label"] = (
                f"#{resolve_channel(api, m['channel_id'], names_cache, names_cache_path)}"
            )
    for t in threads:
        if t["channel_id"].startswith("D"):
            _resolve_dm(api, t, my_user_id, names_cache, names_cache_path)
        else:
            t["label"] = (
                f"#{resolve_channel(api, t['channel_id'], names_cache, names_cache_path)}"
            )
    for dm in dms:
        _resolve_dm(api, dm, my_user_id, names_cache, names_cache_path)

    sys.stdout.write(
        _links_only(mentions, threads, dms, host)
        if args.csv
        else _format(mentions, threads, dms, host)
    )


def _fetch_feed(api, host):
    """Fetch unread activity feed items (newest first), up to MAX_PAGES pages."""
    params = {
        "mode": "chrono_v1",
        "types": FEED_TYPES,
        "limit": str(FEED_LIMIT),
        "archive_only": "false",
        "unread_only": "true",
        "priority_only": "false",
    }
    items = []
    for _ in range(MAX_PAGES):
        resp = api.call_workspace(host, "activity.feed", params)
        batch = resp.get("items", [])
        items.extend(batch)
        cursor = resp.get("response_metadata", {}).get("next_cursor", "")
        if not cursor:
            break
        params["cursor"] = cursor
    return items


def _classify(items):
    """Split feed items into mentions, threads, and DMs. Unknown types skipped."""
    mentions, threads, dms = [], [], []
    for entry in items:
        item = entry.get("item", {})
        itype = item.get("type")
        if itype in MENTION_TYPES:
            msg = item.get("message", {})
            mentions.append(
                {
                    "channel_id": msg.get("channel", ""),
                    "ts": msg.get("ts", "0"),
                    "thread_ts": msg.get("thread_ts"),
                    "author_id": msg.get("author_user_id", ""),
                }
            )
        elif itype == "thread_v2":
            te = (item.get("bundle_info", {}).get("payload", {}) or {}).get(
                "thread_entry", {}
            )
            threads.append(
                {
                    "channel_id": te.get("channel_id", ""),
                    "thread_ts": te.get("thread_ts", "0"),
                    "latest_ts": te.get("latest_ts", "0"),
                    "unread_count": te.get("unread_msg_count", 0),
                }
            )
        elif itype in ("dm", "mpdm"):
            payload = item.get("bundle_info", {}).get("payload", {}) or {}
            lm = payload.get(f"{itype}_entry", {}).get("latest_message", {})
            dms.append(
                {
                    "channel_id": lm.get("channel", ""),
                    "ts": lm.get("ts", "0"),
                    "group": itype == "mpdm",
                }
            )
        else:
            logger.warning("Skipping activity feed item of type %s", itype)
    return mentions, threads, dms


def _resolve_dm(api, item, my_user_id, names_cache, names_cache_path):
    """Fill item['label'] with the other participant(s) of a DM/group DM."""
    cid = item["channel_id"]
    dms = names_cache.get("dms", {})
    info = dms.get(cid)
    if not isinstance(info, dict):
        try:
            ch = api.call("conversations.info", {"channel": cid}).get("channel", {})
        except SlackAPIError as e:
            logger.warning("conversations.info failed for %s: %s", cid, e)
            ch = {}
        if ch.get("is_im"):
            members = [ch.get("user")]
        else:
            members = [u for u in ch.get("members", []) if u and u != my_user_id]
        info = {
            "members": [u for u in members if u],
            "is_im": bool(ch.get("is_im")),
        }
        dms[cid] = info
        names_cache["dms"] = dms
        save_cache(names_cache_path, names_cache)
    others = info["members"]
    group = item.get("group", not info["is_im"])
    if group:
        names = ", ".join(
            resolve_user(api, u, names_cache, names_cache_path) for u in others
        )
        item["label"] = f"Group DM {names}" if names else "Group DM"
    else:
        name = (
            resolve_user(api, others[0], names_cache, names_cache_path)
            if others
            else "?"
        )
        item["label"] = f"DM {name}"


def _link(host, channel_id, ts, thread_ts=None):
    """Build an archives permalink accepted by `slack-cli read`."""
    url = f"https://{host}/archives/{channel_id}/p{str(ts).replace('.', '')}"
    if thread_ts:
        url += f"?thread_ts={str(thread_ts).replace('.', '')}"
    return url


def _fmt_ts(ts):
    """Format a Slack ts as 'YYYY-MM-DD HH:MM UTC'."""
    return datetime.fromtimestamp(float(ts), tz=timezone.utc).strftime(
        "%Y-%m-%d %H:%M UTC"
    )


def _links_only(mentions, threads, dms, host):
    """One URL per line, no header — for machine processing."""
    lines = [_link(host, m["channel_id"], m["ts"], m["thread_ts"]) for m in mentions]
    lines += [
        _link(host, t["channel_id"], t["latest_ts"], t["thread_ts"]) for t in threads
    ]
    lines += [_link(host, dm["channel_id"], dm["ts"]) for dm in dms]
    return "\n".join(lines) + ("\n" if lines else "")


def _format(mentions, threads, dms, host):
    """Build the output listing of unread activity."""
    lines = ["# Slack unread activity", ""]
    if not (mentions or threads or dms):
        return "\n".join(lines + ["Nothing unread — you're all caught up."]) + "\n"

    if mentions:
        lines.append(f"## Mentions ({len(mentions)})")
        lines.append("")
        for i, m in enumerate(mentions, 1):
            thread = " [thread]" if m["thread_ts"] else ""
            lines.append(
                f"{i}. {m['label']} · @{m['author']} · {_fmt_ts(m['ts'])}{thread}"
            )
            lines.append(f"   {_link(host, m['channel_id'], m['ts'], m['thread_ts'])}")
        lines.append("")

    if threads:
        lines.append(f"## Threads ({len(threads)})")
        lines.append("")
        for i, t in enumerate(threads, 1):
            lines.append(
                f"{i}. {t['label']} · {t['unread_count']} unread · "
                f"last {_fmt_ts(t['latest_ts'])}"
            )
            lines.append(
                f"   {_link(host, t['channel_id'], t['latest_ts'], t['thread_ts'])}"
            )
        lines.append("")

    if dms:
        lines.append(f"## Direct messages ({len(dms)})")
        lines.append("")
        for i, dm in enumerate(dms, 1):
            lines.append(f"{i}. {dm['label']} · last {_fmt_ts(dm['ts'])}")
            lines.append(f"   {_link(host, dm['channel_id'], dm['ts'])}")
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
