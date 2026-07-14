import logging
import re
import sys
from datetime import datetime, timezone

from slack_cli.api import SlackAPI, SlackAPIError
from slack_cli.cache import (
    DEFAULT_CACHE_DIR,
    DEFAULT_TTL,
    load_cache,
    resolve_channel,
    resolve_user,
)
from slack_cli.formatter import format_messages
from slack_cli.link import parse_slack_link
from slack_cli.mrkdwn import convert as convert_mrkdwn

logger = logging.getLogger(__name__)


def run(args, config):
    try:
        link = parse_slack_link(args.slack_link)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

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
    users_cache_path = DEFAULT_CACHE_DIR / "users.json"
    channels_cache_path = DEFAULT_CACHE_DIR / "channels.json"
    users_cache = load_cache(users_cache_path, ttl=cache_ttl)
    channels_cache = load_cache(channels_cache_path, ttl=cache_ttl)

    try:
        raw_messages = _fetch_messages(api, link, args)
    except SlackAPIError as e:
        _handle_api_error(e, link)

    user_map = {}
    channel_map = {}
    messages = []
    for raw in raw_messages:
        user_id = raw.get("user", "")
        if user_id and user_id not in user_map:
            user_map[user_id] = resolve_user(
                api, user_id, users_cache, users_cache_path
            )

        replies = []
        for reply_raw in raw.get("_replies", []):
            reply_user_id = reply_raw.get("user", "")
            if reply_user_id and reply_user_id not in user_map:
                user_map[reply_user_id] = resolve_user(
                    api, reply_user_id, users_cache, users_cache_path
                )
            replies.append(
                _build_message(
                    reply_raw,
                    user_map,
                    channel_map,
                    api,
                    channels_cache,
                    channels_cache_path,
                )
            )

        msg = _build_message(
            raw, user_map, channel_map, api, channels_cache, channels_cache_path
        )
        msg["replies"] = replies
        messages.append(msg)

    output = format_messages(messages)
    sys.stdout.write(output)


def _parse_after(value):
    if value is None:
        return None
    m = re.match(r"^(\d+)([MH])$", value)
    if m:
        amount = int(m.group(1))
        unit = m.group(2)
        seconds = amount * 60 if unit == "M" else amount * 3600
        return {"type": "duration", "seconds": seconds}
    try:
        count = int(value)
        if count <= 0:
            raise ValueError
        return {"type": "count", "count": count}
    except ValueError:
        print(
            f"Error: Invalid --after value '{value}'. "
            f"Use a positive integer or duration (e.g., 30M, 2H).",
            file=sys.stderr,
        )
        sys.exit(1)


def _fetch_messages(api, link, args):
    after = _parse_after(getattr(args, "after", None))

    if after and link.is_thread:
        print(
            "Error: --after is only supported for channel messages, not thread links.",
            file=sys.stderr,
        )
        sys.exit(1)

    if link.is_thread and link.is_reply:
        resp = api.call(
            "conversations.history",
            {
                "channel": link.channel_id,
                "oldest": link.message_ts,
                "latest": link.message_ts,
                "inclusive": "true",
                "limit": "1",
            },
        )
        msgs = resp.get("messages", [])
        if not msgs:
            print("Error: Message not found.", file=sys.stderr)
            sys.exit(3)
        return msgs

    if link.is_thread:
        thread_ts = link.thread_ts or link.message_ts
        msgs = api.call_paginated(
            "conversations.replies",
            {"channel": link.channel_id, "ts": thread_ts, "limit": "200"},
            "messages",
        )
        if not msgs:
            print("Error: Thread not found.", file=sys.stderr)
            sys.exit(3)
        parent = msgs[0]
        parent["_replies"] = msgs[1:]
        return [parent]

    resp = api.call(
        "conversations.history",
        {
            "channel": link.channel_id,
            "oldest": link.message_ts,
            "latest": link.message_ts,
            "inclusive": "true",
            "limit": "1",
        },
    )
    msgs = resp.get("messages", [])
    if not msgs:
        logger.debug("Message not in channel history, trying as thread reply")
        try:
            reply_msgs = api.call_paginated(
                "conversations.replies",
                {"channel": link.channel_id, "ts": link.message_ts, "limit": "200"},
                "messages",
            )
        except SlackAPIError:
            reply_msgs = []
        if reply_msgs:
            thread_ts = reply_msgs[0].get("thread_ts")
            if thread_ts and thread_ts != link.message_ts:
                logger.debug("Found thread parent %s, fetching full thread", thread_ts)
                reply_msgs = api.call_paginated(
                    "conversations.replies",
                    {"channel": link.channel_id, "ts": thread_ts, "limit": "200"},
                    "messages",
                )
            parent = reply_msgs[0]
            parent["_replies"] = reply_msgs[1:]
            return [parent]
        print("Error: Message not found.", file=sys.stderr)
        sys.exit(3)

    msg = msgs[0]
    if int(msg.get("reply_count", 0)) > 0:
        thread_msgs = api.call_paginated(
            "conversations.replies",
            {"channel": link.channel_id, "ts": msg["ts"], "limit": "200"},
            "messages",
        )
        if thread_msgs:
            msg["_replies"] = thread_msgs[1:]

    if not after:
        return [msg]

    params = {
        "channel": link.channel_id,
        "oldest": link.message_ts,
        "inclusive": "true",
        "limit": "200",
    }

    if after["type"] == "duration":
        latest_ts = float(link.message_ts) + after["seconds"]
        params["latest"] = str(latest_ts)

    wanted = after["count"] + 1 if after["type"] == "count" else None

    follow_ups = []
    while True:
        resp = api.call("conversations.history", params)
        batch = resp.get("messages", [])
        follow_ups.extend(batch)

        if wanted and len(follow_ups) >= wanted:
            follow_ups = follow_ups[:wanted]
            break

        cursor = resp.get("response_metadata", {}).get("next_cursor", "")
        if not cursor:
            break
        params["cursor"] = cursor

    follow_ups.sort(key=lambda m: float(m.get("ts", "0")))

    for fu in follow_ups:
        if int(fu.get("reply_count", 0)) > 0:
            thread_msgs = api.call_paginated(
                "conversations.replies",
                {"channel": link.channel_id, "ts": fu["ts"], "limit": "200"},
                "messages",
            )
            if thread_msgs:
                fu["_replies"] = thread_msgs[1:]

    return follow_ups


def _build_message(
    raw, user_map, channel_map, api, channels_cache, channels_cache_path
):
    user_id = raw.get("user", "unknown")
    user_name = user_map.get(user_id, user_id)

    text = raw.get("text", "")
    _collect_channel_refs(text, channel_map, api, channels_cache, channels_cache_path)
    converted_text = convert_mrkdwn(text, user_map=user_map, channel_map=channel_map)

    ts = raw.get("ts", "0")
    dt = datetime.fromtimestamp(float(ts), tz=timezone.utc)

    files = []
    for f in raw.get("files", []):
        files.append(
            {
                "name": f.get("name", f.get("title", "unknown")),
                "filetype": f.get("filetype", ""),
                "url": f.get("url_private", None),
            }
        )

    return {
        "text": converted_text,
        "user_id": user_id,
        "user_name": user_name,
        "ts": ts,
        "datetime": dt,
        "files": files,
    }


def _collect_channel_refs(text, channel_map, api, channels_cache, channels_cache_path):
    for m in re.finditer(r"<#([CDGW][A-Z0-9]+)(?:\|([^>]*))?>", text):
        cid = m.group(1)
        name = m.group(2)
        if cid not in channel_map:
            if name:
                channel_map[cid] = name
            else:
                channel_map[cid] = resolve_channel(
                    api, cid, channels_cache, channels_cache_path
                )


def _handle_api_error(e, link):
    error = e.error
    if error == "channel_not_found":
        msg = f"Error: Channel {link.channel_id} not found."
        if link.channel_id.startswith(("D", "G")):
            msg += " This appears to be a DM — the token may lack access."
    elif error == "not_in_channel":
        msg = f"Error: Access denied to channel {link.channel_id}. The token may lack permission."
        if link.channel_id.startswith(("D", "G")):
            msg += " This appears to be a DM — the token may lack access."
    elif error == "message_not_found":
        msg = "Error: Message not found. It may have been deleted."
    elif error == "invalid_auth":
        msg = "Error: Authentication failed. Check your xoxc/xoxd tokens."
    elif error == "token_revoked":
        msg = "Error: Token has been revoked. Obtain new session tokens."
    elif error == "ratelimited":
        msg = "Error: Rate limited by Slack API. Try again later."
    elif error == "account_inactive":
        msg = (
            "Error: Account inactive or session invalidated. "
            "Check your User-Agent configuration (SLACK_CLI_USER_AGENT)."
        )
    else:
        msg = f"Error: Slack API error: {error}"

    print(msg, file=sys.stderr)
    if error in ("invalid_auth", "token_revoked", "account_inactive"):
        sys.exit(2)
    else:
        sys.exit(3)
