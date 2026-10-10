"""Helpers shared by the activity and mine subcommands."""

import logging
import sys
from datetime import datetime, timezone
from urllib.parse import urlparse

from slack_cli.api import SlackAPIError
from slack_cli.cache import (
    DEFAULT_CACHE_DIR,
    DEFAULT_TTL,
    load_cache,
    resolve_channel,
    resolve_user,
    save_cache,
)

logger = logging.getLogger(__name__)


def require_tokens(config):
    """Return (xoxc, xoxd) tokens or exit 2 naming the missing env vars."""
    pairs = (
        ("SLACK_CLI_XOXC_TOKEN", "xoxc_token"),
        ("SLACK_CLI_XOXD_TOKEN", "xoxd_token"),
    )
    missing = [env for env, key in pairs if not config.get(key)]
    if missing:
        print(
            f"Error: {' and '.join(missing)} not set. "
            f"Set in environment or in ~/.config/slack-cli/config.toml",
            file=sys.stderr,
        )
        sys.exit(2)
    return config["xoxc_token"], config["xoxd_token"]


def workspace(api):
    """Return (host, user_id) from auth.test for the connected workspace."""
    auth = api.call("auth.test")
    host = urlparse(auth.get("url", "")).netloc or "slack.com"
    return host, auth.get("user_id", "")


def names_cache(config):
    """Load the names cache; return (cache_dict, cache_path)."""
    path = DEFAULT_CACHE_DIR / "names.json"
    cache = load_cache(path, ttl=config.get("cache_ttl", DEFAULT_TTL)) or {}
    return cache, path


def attach_label(api, d, my_user_id, names_cache, names_cache_path):
    """Fill d['label'] — DM participant names for DMs (D/G), #channel otherwise."""
    if d["channel_id"].startswith(("D", "G")):
        resolve_dm(api, d, my_user_id, names_cache, names_cache_path)
    else:
        d["label"] = (
            f"#{resolve_channel(api, d['channel_id'], names_cache, names_cache_path)}"
        )


def resolve_dm(api, item, my_user_id, names_cache, names_cache_path):
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
    item["members"] = others
    group = item.get("group", not info["is_im"])
    item["group"] = group
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


def link(host, channel_id, ts, thread_ts=None):
    """Archives permalink accepted by `slack-cli read`; ?thread_ts= when given."""
    url = f"https://{host}/archives/{channel_id}/p{str(ts).replace('.', '')}"
    if thread_ts:
        url += f"?thread_ts={str(thread_ts).replace('.', '')}"
    return url


def fmt_ts(ts):
    """Format a Slack ts as 'YYYY-MM-DD HH:MM UTC'."""
    return datetime.fromtimestamp(float(ts), tz=timezone.utc).strftime(
        "%Y-%m-%d %H:%M UTC"
    )


# (exit code, message) for known Slack API errors.
FRIENDLY_ERRORS = {
    "invalid_auth": (2, "Error: Authentication failed. Check your xoxc/xoxd tokens."),
    "token_revoked": (2, "Error: Token has been revoked. Obtain new session tokens."),
    "ratelimited": (2, "Error: Rate limited by Slack API. Try again later."),
    "account_inactive": (
        2,
        (
            "Error: Account inactive or session invalidated. "
            "Check your User-Agent configuration (SLACK_CLI_USER_AGENT)."
        ),
    ),
}


def handle_api_error(e):
    """Print a friendly message for a Slack API error and exit."""
    code, msg = FRIENDLY_ERRORS.get(e.error, (3, f"Error: Slack API error: {e.error}"))
    print(msg, file=sys.stderr)
    sys.exit(code)
