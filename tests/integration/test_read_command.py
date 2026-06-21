import argparse
import json
from io import StringIO
from unittest.mock import MagicMock, patch

import pytest

from slack_cli.commands.read import run


def _make_config():
    return {
        "xoxc_token": "xoxc-test",
        "xoxd_token": "xoxd-test",
        "user_agent": None,
        "cache_ttl": 86400,
    }


def _make_args(link, after=None):
    return argparse.Namespace(slack_link=link, after=after)


def _slack_ok(data):
    return {"ok": True, **data}


def _mock_post(responses):
    call_count = {"n": 0}

    def side_effect(*args, **kwargs):
        resp = MagicMock()
        resp.status_code = 200
        resp.raise_for_status = MagicMock()

        data_sent = kwargs.get("data", {})
        method = args[0].split("/api/")[1] if "/api/" in args[0] else ""

        if call_count["n"] < len(responses):
            body = responses[call_count["n"]]
        else:
            body = {"ok": True, "messages": [], "user": {}, "channel": {}}
        call_count["n"] += 1
        resp.json.return_value = body
        return resp

    return side_effect


class TestChannelMessage:
    @patch("slack_cli.cache.load_cache", return_value=None)
    @patch("slack_cli.cache.save_cache")
    @patch("requests.post")
    def test_single_message(self, mock_post, mock_save, mock_load, capsys):
        mock_post.side_effect = _mock_post([
            _slack_ok({
                "messages": [{
                    "user": "U123",
                    "text": "Hello world",
                    "ts": "1718972400.000000",
                    "reply_count": 0,
                }]
            }),
            _slack_ok({
                "user": {"name": "alice", "profile": {"display_name": "Alice", "real_name": "Alice S"}},
            }),
        ])

        link = "https://test.slack.com/archives/C01234567/p1718972400000000"
        run(_make_args(link), _make_config())

        out = capsys.readouterr().out
        assert "@Alice" in out
        assert "Hello world" in out

    @patch("slack_cli.cache.load_cache", return_value=None)
    @patch("slack_cli.cache.save_cache")
    @patch("requests.post")
    def test_message_with_thread(self, mock_post, mock_save, mock_load, capsys):
        mock_post.side_effect = _mock_post([
            _slack_ok({
                "messages": [{
                    "user": "U123",
                    "text": "Parent",
                    "ts": "1718972400.000000",
                    "reply_count": 2,
                }]
            }),
            _slack_ok({
                "messages": [
                    {"user": "U123", "text": "Parent", "ts": "1718972400.000000"},
                    {"user": "U456", "text": "Reply 1", "ts": "1718972401.000000"},
                    {"user": "U789", "text": "Reply 2", "ts": "1718972402.000000"},
                ]
            }),
            _slack_ok({"user": {"name": "alice", "profile": {"display_name": "Alice", "real_name": ""}}}),
            _slack_ok({"user": {"name": "bob", "profile": {"display_name": "Bob", "real_name": ""}}}),
            _slack_ok({"user": {"name": "carol", "profile": {"display_name": "Carol", "real_name": ""}}}),
        ])

        link = "https://test.slack.com/archives/C01234567/p1718972400000000"
        run(_make_args(link), _make_config())

        out = capsys.readouterr().out
        assert "Parent" in out
        assert "Reply 1" in out
        assert "Reply 2" in out


class TestThreadLink:
    @patch("slack_cli.cache.load_cache", return_value=None)
    @patch("slack_cli.cache.save_cache")
    @patch("requests.post")
    def test_thread_link(self, mock_post, mock_save, mock_load, capsys):
        mock_post.side_effect = _mock_post([
            _slack_ok({
                "messages": [
                    {"user": "U123", "text": "Parent msg", "ts": "1718972400.000000"},
                    {"user": "U456", "text": "Thread reply", "ts": "1718972401.000000"},
                ],
                "response_metadata": {},
            }),
            _slack_ok({"user": {"name": "alice", "profile": {"display_name": "Alice", "real_name": ""}}}),
            _slack_ok({"user": {"name": "bob", "profile": {"display_name": "Bob", "real_name": ""}}}),
        ])

        link = (
            "https://test.slack.com/archives/C01234567/p1718972400000000"
            "?thread_ts=1718972400.000000&cid=C01234567"
        )
        run(_make_args(link), _make_config())

        out = capsys.readouterr().out
        assert "Parent msg" in out
        assert "Thread reply" in out


class TestReplyLink:
    @patch("slack_cli.cache.load_cache", return_value=None)
    @patch("slack_cli.cache.save_cache")
    @patch("requests.post")
    def test_reply_link(self, mock_post, mock_save, mock_load, capsys):
        mock_post.side_effect = _mock_post([
            _slack_ok({
                "messages": [{
                    "user": "U456",
                    "text": "Just this reply",
                    "ts": "1718972401.000000",
                }]
            }),
            _slack_ok({"user": {"name": "bob", "profile": {"display_name": "Bob", "real_name": ""}}}),
        ])

        link = (
            "https://test.slack.com/archives/C01234567/p1718972401000000"
            "?thread_ts=1718972400.000000&cid=C01234567"
        )
        run(_make_args(link), _make_config())

        out = capsys.readouterr().out
        assert "Just this reply" in out
        assert "@Bob" in out


class TestMissingTokens:
    def test_missing_xoxc(self, capsys):
        config = _make_config()
        config["xoxc_token"] = None
        link = "https://test.slack.com/archives/C01234567/p1718972400000000"
        with pytest.raises(SystemExit) as exc:
            run(_make_args(link), config)
        assert exc.value.code == 2

    def test_missing_both(self, capsys):
        config = _make_config()
        config["xoxc_token"] = None
        config["xoxd_token"] = None
        link = "https://test.slack.com/archives/C01234567/p1718972400000000"
        with pytest.raises(SystemExit) as exc:
            run(_make_args(link), config)
        assert exc.value.code == 2


class TestInvalidLink:
    def test_invalid_link(self, capsys):
        link = "https://not-slack.com/foo"
        with pytest.raises(SystemExit) as exc:
            run(_make_args(link), _make_config())
        assert exc.value.code == 1
