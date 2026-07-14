import json
import logging
import os
import tempfile
import time
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_CACHE_DIR = Path("~/.cache/slack-cli").expanduser()
DEFAULT_TTL = 86400


def load_cache(path, ttl=DEFAULT_TTL):
    path = Path(path)
    if not path.exists():
        return None

    try:
        with open(path) as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("Failed to read cache %s: %s", path, e)
        return None

    meta = data.get("_meta", {})
    updated_at = meta.get("updated_at")
    if updated_at is None:
        return None

    from datetime import datetime

    try:
        cache_time = datetime.fromisoformat(updated_at).timestamp()
    except ValueError:
        return None

    if time.time() - cache_time > ttl:
        logger.debug("Cache expired: %s", path)
        return None

    return data


def save_cache(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    from datetime import datetime, timezone

    if "_meta" not in data:
        data["_meta"] = {}
    data["_meta"]["updated_at"] = datetime.now(timezone.utc).isoformat()

    fd, tmp_path = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp_path, path)
    except Exception:
        os.unlink(tmp_path)
        raise

    logger.debug("Cache saved: %s", path)


def resolve_user(api, user_id, cache_data, cache_path):
    users = cache_data.get("users", {}) if cache_data else {}
    if user_id in users:
        return users[user_id]

    logger.debug("Cache miss for user %s, fetching from API", user_id)
    try:
        resp = api.call("users.info", {"user": user_id})
        user = resp.get("user", {})
        profile = user.get("profile", {})
        name = (
            profile.get("display_name")
            or profile.get("real_name")
            or user.get("name", user_id)
        )
    except Exception as e:
        logger.warning("Failed to resolve user %s: %s", user_id, e)
        return user_id

    if cache_data is None:
        cache_data = {"users": {}}
    cache_data.setdefault("users", {})[user_id] = name
    save_cache(cache_path, cache_data)
    return name


def resolve_channel(api, channel_id, cache_data, cache_path):
    channels = cache_data.get("channels", {}) if cache_data else {}
    if channel_id in channels:
        return channels[channel_id]

    logger.debug("Cache miss for channel %s, fetching from API", channel_id)
    try:
        resp = api.call("conversations.info", {"channel": channel_id})
        channel = resp.get("channel", {})
        name = channel.get("name", channel_id)
    except Exception as e:
        logger.warning("Failed to resolve channel %s: %s", channel_id, e)
        return channel_id

    if cache_data is None:
        cache_data = {"channels": {}}
    cache_data.setdefault("channels", {})[channel_id] = name
    save_cache(cache_path, cache_data)
    return name
