"""Mark-read subcommand — clear items from Slack's activity feed.

Matches each permalink against the current unread activity feed, then calls
the undocumented activity.markRead workspace endpoint with the server's item
key, marking the feed item read up to the permalink's timestamp. Marks are
server-side and irreversible, and clear the item from Slack's Activity tab.
"""

import sys

from slack_cli.api import SlackAPI, SlackAPIError
from slack_cli.commands._shared import handle_api_error, require_tokens, workspace
from slack_cli.commands.activity import MENTION_TYPES, _fetch_feed
from slack_cli.link import parse_slack_link


def run(args, config):
    """Mark each permalink in args.slack_links as read in the activity feed."""
    xoxc, xoxd = require_tokens(config)
    api = SlackAPI(xoxc, xoxd, user_agent=config.get("user_agent"))

    links = []
    for url in args.slack_links:
        try:
            links.append(parse_slack_link(url))
        except ValueError as e:
            print(f"Error: {url}: {e}", file=sys.stderr)
            sys.exit(1)

    try:
        host, _ = workspace(api)
        entries = _fetch_feed(api, host)
    except SlackAPIError as e:
        handle_api_error(e)

    index = _index(entries)
    failed = False
    for url, parsed in zip(args.slack_links, links):
        entry = _match(index, parsed)
        if entry is None:
            print(
                f"Warning: not in unread activity feed, skipping: {url}",
                file=sys.stderr,
            )
            continue
        params = {
            "type": entry["type"],
            "key": entry["key"],
            "feed_ts": parsed.message_ts,
        }
        if entry["type"] in ("dm", "mpdm"):
            params["ts"] = parsed.message_ts
        try:
            api.call_workspace(host, "activity.markRead", params)
        except SlackAPIError as e:
            print(f"Error: failed to mark {url}: {e.error}", file=sys.stderr)
            failed = True
            continue
        print(f"marked read: {entry['type']} {entry['key']}")
    if failed:
        sys.exit(1)


def _index(entries):
    """Index feed entries for permalink lookup.

    Returns (dm_index, thread_index, mention_index): channel -> entry for
    DMs, (channel, thread_ts) -> entry for threads, and (channel, ts) ->
    entry for mentions. Entries missing a usable key or coordinates are
    left out (a permalink matching them reports as not unread).
    """
    dm_index, thread_index, mention_index = {}, {}, {}
    for entry in entries:
        item = entry.get("item", {})
        itype = item.get("type")
        key = entry.get("key")
        if itype in ("dm", "mpdm"):
            payload = item.get("bundle_info", {}).get("payload", {}) or {}
            lm = payload.get(f"{itype}_entry", {}).get("latest_message", {})
            channel = lm.get("channel", "")
            if channel:
                dm_index[channel] = {"type": itype, "key": key or f"{itype}-{channel}"}
        elif itype == "thread_v2":
            payload = item.get("bundle_info", {}).get("payload", {}) or {}
            te = payload.get("thread_entry", {})
            channel, thread_ts = te.get("channel_id", ""), te.get("thread_ts", "")
            if channel and thread_ts and key:
                thread_index[(channel, thread_ts)] = {"type": itype, "key": key}
        elif itype in MENTION_TYPES:
            if itype == "unjoined_channel_mention":
                payload = item.get("unjoined_channel_mention_payload", {}) or {}
                channel, ts = (
                    payload.get("channel_id", ""),
                    payload.get("message_ts", ""),
                )
            else:
                msg = item.get("message", {})
                channel, ts = msg.get("channel", ""), msg.get("ts", "")
            if channel and ts and key:
                mention_index[(channel, ts)] = {"type": itype, "key": key}
    return dm_index, thread_index, mention_index


def _match(index, parsed):
    """Return the feed entry a parsed permalink refers to, or None.

    A channel link with a thread_ts can be either a mention inside a
    thread or a thread feed item; the exact (channel, ts) mention match
    wins so a reply permalink marks the mention, not the whole thread.
    """
    dm_index, thread_index, mention_index = index
    if parsed.channel_id.startswith(("D", "G")):
        return dm_index.get(parsed.channel_id)
    if parsed.thread_ts:
        hit = mention_index.get((parsed.channel_id, parsed.message_ts))
        if hit:
            return hit
        return thread_index.get((parsed.channel_id, parsed.thread_ts))
    return mention_index.get((parsed.channel_id, parsed.message_ts))
