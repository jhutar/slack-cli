import json
from datetime import datetime, timezone
from unittest.mock import MagicMock

from slack_cli.cache import load_cache, resolve_user, save_cache


def test_load_valid_cache(tmp_path):
    cache_file = tmp_path / "users.json"
    data = {
        "_meta": {"updated_at": datetime.now(timezone.utc).isoformat()},
        "users": {"U123": "alice"},
    }
    cache_file.write_text(json.dumps(data))
    result = load_cache(str(cache_file), ttl=86400)
    assert result is not None
    assert result["users"]["U123"] == "alice"


def test_load_expired_cache(tmp_path):
    cache_file = tmp_path / "users.json"
    data = {
        "_meta": {"updated_at": "2020-01-01T00:00:00+00:00"},
        "users": {"U123": "alice"},
    }
    cache_file.write_text(json.dumps(data))
    result = load_cache(str(cache_file), ttl=86400)
    assert result is None


def test_save_and_reload(tmp_path):
    cache_file = tmp_path / "users.json"
    data = {"users": {"U123": "alice"}}
    save_cache(str(cache_file), data)

    result = load_cache(str(cache_file), ttl=86400)
    assert result is not None
    assert result["users"]["U123"] == "alice"
    assert "_meta" in result


def test_resolve_user_cache_hit(tmp_path):
    cache_file = tmp_path / "users.json"
    cache_data = {"users": {"U123": "alice"}}
    api = MagicMock()

    name = resolve_user(api, "U123", cache_data, str(cache_file))
    assert name == "alice"
    api.call.assert_not_called()


def test_resolve_user_cache_miss(tmp_path):
    cache_file = tmp_path / "users.json"
    api = MagicMock()
    api.call.return_value = {
        "ok": True,
        "user": {
            "name": "bob",
            "profile": {"display_name": "Bob Smith", "real_name": "Robert Smith"},
        },
    }

    name = resolve_user(api, "U456", None, str(cache_file))
    assert name == "Bob Smith"
    api.call.assert_called_once_with("users.info", {"user": "U456"})
