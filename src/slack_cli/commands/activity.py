"""Activity subcommand — list mentions and DMs from a time window.

Mimics Slack's "Activity" section: channel/thread mentions plus new
direct messages, each with a link usable by `slack-cli read`.
"""

import logging
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from urllib.parse import urlparse

from slack_cli.api import SlackAPI, SlackAPIError
from slack_cli.cache import DEFAULT_CACHE_DIR, DEFAULT_TTL, load_cache, resolve_user
from slack_cli.mrkdwn import convert as convert_mrkdwn

logger = logging.getLogger(__name__)

DEFAULT_SINCE = "24H"
SNIPPET_LEN = 100


def run(args, config):
    """Fetch mentions and DMs in the --since window and print a readable list."""
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

    since_seconds = _parse_since(args.since)
    now = datetime.now(timezone.utc)
    since_ts = now.timestamp() - since_seconds

    api = SlackAPI(xoxc, xoxd, user_agent=config.get("user_agent"))

    cache_ttl = config.get("cache_ttl", DEFAULT_TTL)
    users_cache_path = DEFAULT_CACHE_DIR / "users.json"
    users_cache = load_cache(users_cache_path, ttl=cache_ttl)

    try:
        auth = api.call("auth.test")
        my_user_id = auth.get("user_id", "")
        host = urlparse(auth.get("url", "")).netloc or "slack.com"

        mentions = _fetch_mentions(api, since_ts)
        dms = _fetch_dms(api, my_user_id, since_ts)
    except SlackAPIError as e:
        _handle_api_error(e)

    user_map = {}
    if my_user_id:
        user_map[my_user_id] = resolve_user(api, my_user_id, users_cache, users_cache_path)
    for m in mentions:
        uid = m.get("user")
        if uid and uid not in user_map:
            user_map[uid] = resolve_user(api, uid, users_cache, users_cache_path)
    for dm in dms:
        for uid in dm["other_users"]:
            if uid not in user_map:
                user_map[uid] = resolve_user(api, uid, users_cache, users_cache_path)
        for m in re.finditer(r"<@(U[A-Z0-9]+)>", dm["messages"][-1].get("text") or ""):
            uid = m.group(1)
            if uid not in user_map:
                user_map[uid] = resolve_user(api, uid, users_cache, users_cache_path)

    sys.stdout.write(_format_activity(mentions, dms, user_map, host, since_ts, now, args.since))


def _parse_since(value):
    """Parse a --since duration (e.g., 30M, 24H) into seconds."""
    m = re.match(r"^(\d+)([MH])$", value)
    if not m:
        print(
            f"Error: Invalid --since value '{value}'. Use a duration (e.g., 8H, 24H).",
            file=sys.stderr,
        )
        sys.exit(1)
    amount = int(m.group(1))
    return amount * 60 if m.group(2) == "M" else amount * 3600


def _fetch_mentions(api, since_ts):
    """Return search matches where I was mentioned (channels and threads) since since_ts.

    Slack ignores server-side time filters on this token, so filtering is
    client-side. DM mentions are skipped — DMs have their own section.
    """
    matches = []
    page = 1
    while True:
        resp = api.call(
            "search.messages", {"query": "@me", "count": 200, "page": page}
        )
        batch = resp.get("messages", {}).get("matches", [])
        for m in batch:
            try:
                ts = float(m.get("ts", "0"))
            except ValueError:
                continue
            if ts < since_ts:
                continue
            channel = m.get("channel", {})
            if channel.get("is_im") or channel.get("is_mpim"):
                continue
            matches.append(m)
        if len(batch) < 200:
            break
        page += 1
    return matches


def _fetch_dms(api, my_user_id, since_ts):
    """Return DMs/group DMs whose latest message is from someone else since since_ts.

    Uses conversations.info per DM (exposes `latest` and `unread_count`,
    which im.list/mpim.list do not — their `updated` field tracks metadata
    changes, not messages). Info calls run in a small thread pool.
    """
    convs = []
    for method, key in (("im.list", "ims"), ("mpim.list", "groups")):
        convs.extend(api.call_paginated(method, {"limit": 200}, key))
    convs = [c for c in convs if not c.get("is_archived")]
    total = len(convs)

    def check(conv):
        try:
            return api.call("conversations.info", {"channel": conv["id"]})
        except SlackAPIError as e:
            logger.warning("conversations.info failed for %s: %s", conv["id"], e.error)
            return None

    dms = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        for i, resp in enumerate(pool.map(check, convs), 1):
            if i % 200 == 0 or i == total:
                print(f"Scanning DMs: {i}/{total}", file=sys.stderr)
            if resp is None:
                continue
            info = resp.get("channel", {})
            conv = convs[i - 1]
            latest = info.get("latest") or {}
            try:
                latest_ts = float(latest.get("ts", "0"))
            except ValueError:
                continue
            if latest_ts < since_ts:
                continue
            if not latest.get("user") or latest["user"] == my_user_id:
                continue
            if conv.get("is_im"):
                other_users = [
                    u for u in [conv.get("user")] if u and u != my_user_id
                ]
            else:
                other_users = [
                    u for u in conv.get("members", []) if u != my_user_id
                ]
            if not other_users:
                continue
            hist = api.call(
                "conversations.history",
                {"channel": conv["id"], "oldest": str(since_ts), "limit": 100},
            )
            msgs = [
                m
                for m in hist.get("messages", [])
                if m.get("user") != my_user_id
                and (not m.get("subtype") or m.get("subtype") == "file_share")
            ]
            if not msgs:
                continue
            dms.append(
                {
                    "conv": conv,
                    "other_users": other_users,
                    "messages": msgs,
                    "unread": info.get("unread_count_display", 0),
                }
            )
    return dms


def _snippet(text, user_map):
    """First non-empty line of converted text, truncated to SNIPPET_LEN chars."""
    converted = convert_mrkdwn(text or "", user_map=user_map)
    for line in converted.splitlines():
        line = line.strip()
        if line:
            return line[:SNIPPET_LEN] + ("…" if len(line) > SNIPPET_LEN else "")
    return ""


def _format_activity(mentions, dms, user_map, host, since_ts, now, since_label):
    """Build the output listing of mentions and DMs."""
    since_dt = datetime.fromtimestamp(since_ts, tz=timezone.utc)
    lines = [f"# Slack activity since {since_dt.strftime('%Y-%m-%d %H:%M UTC')}"]
    lines.append("")

    if not mentions and not dms:
        lines.append(f"Nothing new in the last {since_label}.")
        return "\n".join(lines) + "\n"

    if mentions:
        mentions.sort(key=lambda m: float(m["ts"]), reverse=True)
        lines.append(f"## Mentions ({len(mentions)})")
        lines.append("")
        for i, m in enumerate(mentions, 1):
            channel = m.get("channel", {})
            chan_label = (
                f"#{channel['name']}" if channel.get("name") else channel.get("id", "?")
            )
            author = user_map.get(m.get("user"), m.get("username", "unknown"))
            dt = datetime.fromtimestamp(float(m["ts"]), tz=timezone.utc)
            thread = " [thread]" if "thread_ts" in m.get("permalink", "") else ""
            lines.append(f"{i}. {chan_label} · @{author} · {dt.strftime('%Y-%m-%d %H:%M UTC')}{thread}")
            lines.append(f"   {m.get('permalink', '')}")
            snip = _snippet(m.get("text"), user_map)
            if snip:
                lines.append(f'   "{snip}"')
        lines.append("")

    if dms:
        dms.sort(key=lambda d: float(d["messages"][-1]["ts"]), reverse=True)
        lines.append(f"## Direct messages ({len(dms)})")
        lines.append("")
        for i, dm in enumerate(dms, 1):
            conv = dm["conv"]
            if conv.get("is_im"):
                name = user_map.get(dm["other_users"][0], dm["other_users"][0])
                label = f"DM @{name}"
            else:
                label = f"DM #{conv.get('name', conv['id'])}"
            last = dm["messages"][-1]
            dt = datetime.fromtimestamp(float(last["ts"]), tz=timezone.utc)
            p_ts = str(last["ts"]).replace(".", "")
            url = f"https://{host}/archives/{conv['id']}/p{p_ts}"
            n = len(dm["messages"])
            unread = dm.get("unread", 0)
            unread_str = f" · {unread} unread" if unread else ""
            lines.append(
                f"{i}. {label} · {n} new message{'s' if n != 1 else ''}{unread_str} · "
                f"last {dt.strftime('%Y-%m-%d %H:%M UTC')}"
            )
            lines.append(f"   {url}")
            snip = _snippet(last.get("text"), user_map)
            if snip:
                lines.append(f'   "{snip}"')
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
