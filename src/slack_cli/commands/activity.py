"""Activity subcommand — list unread items from Slack's activity feed.

Uses the workspace /api/activity.feed endpoint (same source as Slack's
Activity panel) instead of search + per-DM conversation scans. Lists
mentions, active threads, and DMs/group DMs needing a response, each
with an archives permalink usable by `slack-cli read`.
"""

import logging
import sys

from slack_cli.api import SlackAPI, SlackAPIError
from slack_cli.cache import resolve_user
from slack_cli.commands._shared import (
    attach_label,
    fmt_ts,
    handle_api_error,
    link,
    names_cache,
    require_tokens,
    resolve_dm,
    workspace,
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
    xoxc, xoxd = require_tokens(config)
    api = SlackAPI(xoxc, xoxd, user_agent=config.get("user_agent"))
    cache, cache_path = names_cache(config)

    try:
        host, my_id = workspace(api)
        items = _fetch_feed(api, host)
    except SlackAPIError as e:
        handle_api_error(e)

    mentions, threads, dms = _classify(items)
    for m in mentions:
        m["author"] = resolve_user(api, m.pop("author_id"), cache, cache_path)
    for d in mentions + threads:
        attach_label(api, d, my_id, cache, cache_path)
    for dm in dms:
        # DM and group DM both resolve to participant names, not #channel.
        resolve_dm(api, dm, my_id, cache, cache_path)

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


def _links_only(mentions, threads, dms, host):
    """One URL per line, no header — for machine processing."""
    lines = [link(host, m["channel_id"], m["ts"], m["thread_ts"]) for m in mentions]
    lines += [
        link(host, t["channel_id"], t["latest_ts"], t["thread_ts"]) for t in threads
    ]
    lines += [link(host, dm["channel_id"], dm["ts"]) for dm in dms]
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
                f"{i}. {m['label']} · @{m['author']} · {fmt_ts(m['ts'])}{thread}"
            )
            lines.append(f"   {link(host, m['channel_id'], m['ts'], m['thread_ts'])}")
        lines.append("")

    if threads:
        lines.append(f"## Threads ({len(threads)})")
        lines.append("")
        for i, t in enumerate(threads, 1):
            lines.append(
                f"{i}. {t['label']} · {t['unread_count']} unread · "
                f"last {fmt_ts(t['latest_ts'])}"
            )
            lines.append(
                f"   {link(host, t['channel_id'], t['latest_ts'], t['thread_ts'])}"
            )
        lines.append("")

    if dms:
        lines.append(f"## Direct messages ({len(dms)})")
        lines.append("")
        for i, dm in enumerate(dms, 1):
            lines.append(f"{i}. {dm['label']} · last {fmt_ts(dm['ts'])}")
            lines.append(f"   {link(host, dm['channel_id'], dm['ts'])}")
        lines.append("")

    return "\n".join(lines).rstrip("\n") + "\n"
