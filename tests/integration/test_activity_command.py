import argparse
from unittest.mock import MagicMock, patch

import pytest

from slack_cli.commands.activity import run

HOST = "test.slack.com"
ME = "UME"

AUTH_OK = {"ok": True, "user_id": ME, "url": f"https://{HOST}"}


def _make_config(**overrides):
    cfg = {
        "xoxc_token": "xoxc-test",
        "xoxd_token": "xoxd-test",
        "user_agent": None,
        "cache_ttl": 86400,
    }
    cfg.update(overrides)
    return cfg


def _make_args(csv=False):
    return argparse.Namespace(csv=csv)


def _mock_post(responses):
    """Mock requests.post; returns (side_effect, calls) with calls = [(url, data)]."""
    calls = []

    def side_effect(url, headers=None, data=None, timeout=None):
        calls.append((url, data))
        resp = MagicMock()
        resp.status_code = 200
        resp.raise_for_status = MagicMock()
        resp.json.return_value = responses.pop(0) if responses else {"ok": True}
        return resp

    return side_effect, calls


def _feed(items, next_cursor=None):
    meta = {"response_metadata": {"next_cursor": next_cursor}} if next_cursor else {}
    return {"ok": True, "items": items, **meta}


def _mention_item(channel, ts, author, thread_ts=None):
    msg = {"ts": ts, "channel": channel, "author_user_id": author}
    if thread_ts:
        msg["thread_ts"] = thread_ts
    return {
        "is_unread": True,
        "feed_ts": ts,
        "item": {"type": "at_user", "message": msg},
    }


def _thread_item(channel, latest_ts, thread_ts, unread):
    return {
        "is_unread": True,
        "feed_ts": latest_ts,
        "item": {
            "type": "thread_v2",
            "bundle_info": {
                "payload": {
                    "thread_entry": {
                        "channel_id": channel,
                        "thread_ts": thread_ts,
                        "latest_ts": latest_ts,
                        "unread_msg_count": unread,
                    }
                }
            },
        },
    }


def _dm_item(channel, ts, group=False):
    key = "mpdm_entry" if group else "dm_entry"
    return {
        "is_unread": True,
        "feed_ts": ts,
        "item": {
            "type": "mpdm" if group else "dm",
            "bundle_info": {
                "payload": {key: {"latest_message": {"ts": ts, "channel": channel}}}
            },
        },
    }


PRELOADED_CACHE = {
    "users": {
        "UALICE": "Alice",
        "UBOB": "Bob",
        "UCAROL": "Carol",
        "UDAVE": "Dave",
        "UERIN": "Erin",
    },
    "channels": {"C111": "eng"},
    "dms": {
        "D222": {"members": ["UCAROL"], "is_im": True},
        "G333": {"members": ["UDAVE", "UERIN"], "is_im": False},
    },
}


class TestActivityCommand:
    @patch("slack_cli.commands.activity.load_cache", return_value=PRELOADED_CACHE)
    @patch("slack_cli.commands.activity.save_cache")
    @patch("requests.post")
    def test_full_output(self, mock_post, mock_save, mock_load, capsys):
        side_effect, calls = _mock_post(
            [
                AUTH_OK,
                _feed(
                    [
                        _mention_item("C111", "1718972600.000000", "UBOB"),
                        _mention_item(
                            "C111",
                            "1718972500.000000",
                            "UALICE",
                            thread_ts="1718972400.000000",
                        ),
                        _thread_item(
                            "C111", "1718972700.000000", "1718972400.000000", 3
                        ),
                        _thread_item(
                            "D222", "1718972800.000000", "1718972300.000000", 1
                        ),
                        _dm_item("D222", "1718972900.000000"),
                        _dm_item("G333", "1718973000.000000", group=True),
                        {
                            "is_unread": True,
                            "feed_ts": "1718973100.000000",
                            "item": {"type": "message_reaction"},
                        },
                    ]
                ),
            ]
        )
        mock_post.side_effect = side_effect

        run(_make_args(), _make_config())

        out = capsys.readouterr().out
        assert "# Slack unread activity" in out
        assert "## Mentions (2)" in out
        assert "1. #eng · @Bob · 2024-06-21 12:23 UTC" in out
        assert f"https://{HOST}/archives/C111/p1718972600000000" in out
        assert "2. #eng · @Alice · 2024-06-21 12:21 UTC [thread]" in out
        assert (
            f"https://{HOST}/archives/C111/p1718972500000000"
            "?thread_ts=1718972400000000" in out
        )
        assert "## Threads (2)" in out
        assert "1. #eng · 3 unread · last 2024-06-21 12:25 UTC" in out
        assert (
            f"https://{HOST}/archives/C111/p1718972700000000"
            "?thread_ts=1718972400000000" in out
        )
        assert "2. DM Carol · 1 unread · last 2024-06-21 12:26 UTC" in out
        assert "## Direct messages (2)" in out
        assert "1. DM Carol · last 2024-06-21 12:28 UTC" in out
        assert f"https://{HOST}/archives/D222/p1718972900000000" in out
        assert "2. Group DM Dave, Erin · last 2024-06-21 12:30 UTC" in out
        assert "message_reaction" not in out

        # Feed request uses unread-only server-side filter
        feed_calls = [d for u, d in calls if "activity.feed" in u]
        assert len(feed_calls) == 1
        assert feed_calls[0]["unread_only"] == "true"
        assert feed_calls[0]["mode"] == "chrono_v1"
        assert feed_calls[0]["token"] == "xoxc-test"

    @patch("slack_cli.commands.activity.load_cache", return_value=PRELOADED_CACHE)
    @patch("slack_cli.commands.activity.save_cache")
    @patch("requests.post")
    def test_empty_feed(self, mock_post, mock_save, mock_load, capsys):
        mock_post.side_effect, _ = _mock_post([AUTH_OK, _feed([])])

        run(_make_args(), _make_config())

        out = capsys.readouterr().out
        assert "Nothing unread" in out
        assert "## Mentions" not in out

    @patch("slack_cli.commands.activity.load_cache", return_value=PRELOADED_CACHE)
    @patch("slack_cli.commands.activity.save_cache")
    @patch("requests.post")
    def test_pagination_follows_cursor(self, mock_post, mock_save, mock_load, capsys):
        side_effect, calls = _mock_post(
            [
                AUTH_OK,
                _feed([_mention_item("C111", "1718972600.000000", "UBOB")], "cursor-1"),
                _feed([_mention_item("C111", "1718972500.000000", "UALICE")]),
            ]
        )
        mock_post.side_effect = side_effect

        run(_make_args(), _make_config())

        out = capsys.readouterr().out
        assert "## Mentions (2)" in out
        feed_calls = [(u, d) for u, d in calls if "activity.feed" in u]
        assert len(feed_calls) == 2
        assert feed_calls[0][1].get("cursor") is None
        assert feed_calls[1][1]["cursor"] == "cursor-1"

    @patch("slack_cli.commands.activity.load_cache", return_value=PRELOADED_CACHE)
    @patch("slack_cli.commands.activity.save_cache")
    @patch("requests.post")
    def test_csv_prints_urls_only(self, mock_post, mock_save, mock_load, capsys):
        mock_post.side_effect, _ = _mock_post(
            [
                AUTH_OK,
                _feed(
                    [
                        _mention_item(
                            "C111",
                            "1718972500.000000",
                            "UALICE",
                            thread_ts="1718972400.000000",
                        ),
                        _thread_item(
                            "C111", "1718972700.000000", "1718972400.000000", 3
                        ),
                        _dm_item("D222", "1718972900.000000"),
                    ]
                ),
            ]
        )

        run(_make_args(csv=True), _make_config())

        out = capsys.readouterr().out
        assert out == (
            f"https://{HOST}/archives/C111/p1718972500000000"
            "?thread_ts=1718972400000000\n"
            f"https://{HOST}/archives/C111/p1718972700000000"
            "?thread_ts=1718972400000000\n"
            f"https://{HOST}/archives/D222/p1718972900000000\n"
        )

    @patch("slack_cli.commands.activity.load_cache", return_value=PRELOADED_CACHE)
    @patch("slack_cli.commands.activity.save_cache")
    @patch("requests.post")
    def test_csv_empty_prints_nothing(self, mock_post, mock_save, mock_load, capsys):
        mock_post.side_effect, _ = _mock_post([AUTH_OK, _feed([])])

        run(_make_args(csv=True), _make_config())

        assert capsys.readouterr().out == ""

    @patch("slack_cli.commands.activity.load_cache", return_value=None)
    @patch("slack_cli.commands.activity.save_cache")
    @patch("requests.post")
    def test_resolves_names_from_api(self, mock_post, mock_save, mock_load, capsys):
        mock_post.side_effect, _ = _mock_post(
            [
                AUTH_OK,
                _feed(
                    [
                        _mention_item("C111", "1718972500.000000", "UALICE"),
                        _dm_item("D222", "1718972900.000000"),
                    ]
                ),
                {
                    "ok": True,
                    "user": {
                        "id": "UALICE",
                        "name": "alice",
                        "profile": {"display_name": "Alice"},
                    },
                },
                {"ok": True, "channel": {"id": "C111", "name": "eng"}},
                {
                    "ok": True,
                    "channel": {"id": "D222", "is_im": True, "user": "UCAROL"},
                },
                {
                    "ok": True,
                    "user": {
                        "id": "UCAROL",
                        "name": "carol",
                        "profile": {"display_name": "Carol"},
                    },
                },
            ]
        )

        run(_make_args(), _make_config())

        out = capsys.readouterr().out
        assert "#eng · @Alice" in out
        assert "DM Carol" in out

    @patch("requests.post")
    def test_missing_tokens_exits(self, mock_post, capsys):
        with pytest.raises(SystemExit) as e:
            run(_make_args(), _make_config(xoxc_token=None, xoxd_token=None))
        assert e.value.code == 2
        err = capsys.readouterr().err
        assert "SLACK_CLI_XOXC_TOKEN" in err
        assert "SLACK_CLI_XOXD_TOKEN" in err

    @patch("slack_cli.commands.activity.load_cache", return_value=PRELOADED_CACHE)
    @patch("requests.post")
    def test_api_error_exits(self, mock_post, mock_load, capsys):
        mock_post.side_effect, _ = _mock_post(
            [AUTH_OK, {"ok": False, "error": "invalid_auth"}]
        )
        with pytest.raises(SystemExit) as e:
            run(_make_args(), _make_config())
        assert e.value.code == 2
        assert "Authentication failed" in capsys.readouterr().err

    @patch("slack_cli.commands.activity.load_cache", return_value=PRELOADED_CACHE)
    @patch("slack_cli.commands.activity.save_cache")
    @patch("requests.post")
    def test_unknown_types_skipped(self, mock_post, mock_save, mock_load, capsys):
        mock_post.side_effect, _ = _mock_post(
            [
                AUTH_OK,
                _feed(
                    [
                        {
                            "is_unread": True,
                            "feed_ts": "1718973100.000000",
                            "item": {"type": "message_reaction"},
                        },
                        {
                            "is_unread": True,
                            "feed_ts": "1718973200.000000",
                            "item": {"type": "internal_channel_invite"},
                        },
                    ]
                ),
            ]
        )

        run(_make_args(), _make_config())

        out = capsys.readouterr().out
        assert "Nothing unread" in out
