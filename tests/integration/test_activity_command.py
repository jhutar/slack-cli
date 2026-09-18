import argparse
import time
from unittest.mock import MagicMock, patch

import pytest

from slack_cli.commands.activity import run


def _make_config():
    return {
        "xoxc_token": "xoxc-test",
        "xoxd_token": "xoxd-test",
        "user_agent": None,
        "cache_ttl": 86400,
    }


def _make_args(since="24H"):
    return argparse.Namespace(since=since)


def _slack_ok(data):
    return {"ok": True, **data}


def _ts(seconds_ago):
    return str(int(time.time()) - seconds_ago) + ".000000"


def _mock_post(responses):
    call_count = {"n": 0}

    def side_effect(*args, **kwargs):
        resp = MagicMock()
        resp.status_code = 200
        resp.raise_for_status = MagicMock()

        if call_count["n"] < len(responses):
            body = responses[call_count["n"]]
        else:
            body = {"ok": True, "messages": {}, "ims": [], "groups": []}
        call_count["n"] += 1
        resp.json.return_value = body
        return resp

    return side_effect


def _auth():
    return _slack_ok({"user_id": "UME", "user": "me", "url": "https://test.slack.com/"})


def _search(matches):
    return _slack_ok({"messages": {"total": len(matches), "matches": matches}})


def _im(ims):
    return _slack_ok({"ims": ims})


def _mpim(groups):
    return _slack_ok({"groups": groups})


def _history(messages):
    return _slack_ok({"messages": messages})


def _user_info(name, display=""):
    return _slack_ok(
        {
            "user": {
                "name": name,
                "profile": {"display_name": display, "real_name": display or name},
            }
        }
    )


class TestMentions:
    @patch("slack_cli.cache.load_cache", return_value=None)
    @patch("slack_cli.cache.save_cache")
    @patch("requests.post")
    def test_mentions_listed(self, mock_post, mock_save, mock_load, capsys):
        new = {
            "user": "U123",
            "username": "alice",
            "ts": _ts(3600),
            "text": "Please review <@UME>",
            "channel": {
                "id": "C0123",
                "is_im": False,
                "is_mpim": False,
                "name": "team-dcm",
            },
            "permalink": "https://test.slack.com/archives/C0123/p100?thread_ts=99.000000",
        }
        old = {
            "user": "U123",
            "username": "alice",
            "ts": _ts(200000),
            "text": "old mention should be filtered out",
            "channel": {"id": "C0123", "is_im": False, "is_mpim": False, "name": "team-dcm"},
            "permalink": "https://test.slack.com/archives/C0123/p50",
        }
        dm_mention = {
            "user": "U123",
            "username": "alice",
            "ts": _ts(1800),
            "text": "dm mention goes to DM section",
            "channel": {"id": "D0123", "is_im": True, "is_mpim": False},
            "permalink": "https://test.slack.com/archives/D0123/p60",
        }
        mock_post.side_effect = _mock_post(
            [
                _auth(),
                _search([new, old, dm_mention]),
                _im([]),
                _mpim([]),
                _user_info("jhutar", "Jan"),
                _user_info("alice", "Alice"),
            ]
        )

        run(_make_args(), _make_config())

        out = capsys.readouterr().out
        assert "#team-dcm" in out
        assert "@Alice" in out
        assert "[thread]" in out
        assert "Please review @Jan" in out
        assert "old mention should be filtered out" not in out
        assert "dm mention goes to DM section" not in out

    @patch("slack_cli.cache.load_cache", return_value=None)
    @patch("slack_cli.cache.save_cache")
    @patch("requests.post")
    def test_no_activity(self, mock_post, mock_save, mock_load, capsys):
        mock_post.side_effect = _mock_post(
            [
                _auth(),
                _search([]),
                _im([]),
                _mpim([]),
                _user_info("jhutar", "Jan"),
            ]
        )

        run(_make_args(), _make_config())

        out = capsys.readouterr().out
        assert "Nothing new" in out


def _info(latest_ts, latest_user, unread=0):
    return _slack_ok(
        {
            "channel": {
                "latest": {"ts": latest_ts, "user": latest_user, "text": "latest"},
                "unread_count_display": unread,
            }
        }
    )


class TestDMs:
    @patch("slack_cli.cache.load_cache", return_value=None)
    @patch("slack_cli.cache.save_cache")
    @patch("requests.post")
    def test_dm_new_messages(self, mock_post, mock_save, mock_load, capsys):
        t1, t2 = _ts(700), _ts(600)
        mock_post.side_effect = _mock_post(
            [
                _auth(),
                _search([]),
                _im(
                    [
                        {
                            "id": "D0123",
                            "is_im": True,
                            "user": "U123",
                            "updated": int(time.time()) * 1000 - 600000,
                        }
                    ]
                ),
                _mpim([]),
                _info(t2, "U123", unread=1),
                _history(
                    [
                        {"user": "UME", "text": "my own message", "ts": t1},
                        {"user": "U123", "text": "hello from bob", "ts": t2},
                    ]
                ),
                _user_info("jhutar", "Jan"),
                _user_info("bob", "Bob"),
            ]
        )

        run(_make_args(), _make_config())

        out = capsys.readouterr().out
        assert "DM @Bob" in out
        assert "hello from bob" in out
        assert "my own message" not in out
        assert "1 new message" in out
        assert "1 unread" in out
        assert "/archives/D0123/p" in out

    @patch("slack_cli.cache.load_cache", return_value=None)
    @patch("slack_cli.cache.save_cache")
    @patch("requests.post")
    def test_dm_latest_outside_window_skipped(self, mock_post, mock_save, mock_load, capsys):
        mock_post.side_effect = _mock_post(
            [
                _auth(),
                _search([]),
                _im(
                    [
                        {
                            "id": "D0123",
                            "is_im": True,
                            "user": "U123",
                            "updated": int(time.time()) * 1000 - 200000000,
                        }
                    ]
                ),
                _mpim([]),
                _info(_ts(200000), "U123"),
                _user_info("jhutar", "Jan"),
            ]
        )

        run(_make_args(), _make_config())

        out = capsys.readouterr().out
        assert "Nothing new" in out

    @patch("slack_cli.cache.load_cache", return_value=None)
    @patch("slack_cli.cache.save_cache")
    @patch("requests.post")
    def test_dm_latest_from_self_skipped(self, mock_post, mock_save, mock_load, capsys):
        mock_post.side_effect = _mock_post(
            [
                _auth(),
                _search([]),
                _im(
                    [
                        {
                            "id": "D0123",
                            "is_im": True,
                            "user": "U123",
                        }
                    ]
                ),
                _mpim([]),
                _info(_ts(600), "UME"),
                _user_info("jhutar", "Jan"),
            ]
        )

        run(_make_args(), _make_config())

        out = capsys.readouterr().out
        assert "Nothing new" in out

    @patch("slack_cli.cache.load_cache", return_value=None)
    @patch("slack_cli.cache.save_cache")
    @patch("requests.post")
    def test_group_dm(self, mock_post, mock_save, mock_load, capsys):
        mock_post.side_effect = _mock_post(
            [
                _auth(),
                _search([]),
                _im([]),
                _mpim(
                    [
                        {
                            "id": "C0GRP",
                            "is_im": False,
                            "name": "grp",
                            "members": ["UME", "U123"],
                            "updated": int(time.time()) * 1000 - 600000,
                        }
                    ]
                ),
                _info(_ts(600), "U123"),
                _history(
                    [
                        {
                            "user": "U123",
                            "text": "hi <@UME> and others",
                            "ts": _ts(600),
                        }
                    ]
                ),
                _user_info("jhutar", "Jan"),
                _user_info("bob", "Bob"),
            ]
        )

        run(_make_args(), _make_config())

        out = capsys.readouterr().out
        assert "DM #grp" in out
        assert "hi @Jan and others" in out


class TestErrors:
    def test_missing_tokens(self, capsys):
        config = _make_config()
        config["xoxc_token"] = None
        config["xoxd_token"] = None
        with pytest.raises(SystemExit) as exc:
            run(_make_args(), config)
        assert exc.value.code == 2

    def test_invalid_since(self, capsys):
        with pytest.raises(SystemExit) as exc:
            run(_make_args(since="yesterday"), _make_config())
        assert exc.value.code == 1
        err = capsys.readouterr().err
        assert "--since" in err
