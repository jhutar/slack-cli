import argparse
from unittest.mock import MagicMock, patch

import pytest

from slack_cli.commands.mark_read import run

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


def _make_args(links):
    return argparse.Namespace(slack_links=list(links))


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


def _mention_entry(channel, ts, author, thread_ts=None):
    msg = {"ts": ts, "channel": channel, "author_user_id": author}
    if thread_ts:
        msg["thread_ts"] = thread_ts
    key = f"at_user-{channel}-{ts}"
    if thread_ts:
        key += f"-{thread_ts}"
    return {
        "is_unread": True,
        "feed_ts": ts,
        "key": key,
        "item": {"type": "at_user", "message": msg},
    }


def _thread_entry(channel, latest_ts, thread_ts):
    return {
        "is_unread": True,
        "feed_ts": latest_ts,
        "key": f"thread_v2-{channel}-{thread_ts}",
        "item": {
            "type": "thread_v2",
            "bundle_info": {
                "payload": {
                    "thread_entry": {
                        "channel_id": channel,
                        "thread_ts": thread_ts,
                        "latest_ts": latest_ts,
                        "unread_msg_count": 3,
                    }
                }
            },
        },
    }


def _dm_entry(channel, ts, group=False):
    itype = "mpdm" if group else "dm"
    entry_key = "mpdm_entry" if group else "dm_entry"
    return {
        "is_unread": True,
        "feed_ts": ts,
        "key": f"{itype}-{channel}",
        "item": {
            "type": itype,
            "bundle_info": {
                "payload": {
                    entry_key: {"latest_message": {"ts": ts, "channel": channel}}
                }
            },
        },
    }


def _url(channel, ts, thread_ts=None):
    url = f"https://{HOST}/archives/{channel}/p{ts.replace('.', '')}"
    if thread_ts:
        url += f"?thread_ts={thread_ts.replace('.', '')}"
    return url


def _mark_calls(calls):
    return [d for u, d in calls if "activity.markRead" in u]


class TestMarkReadCommand:
    @patch("requests.post")
    def test_marks_mention_thread_and_dm(self, mock_post, capsys):
        side_effect, calls = _mock_post(
            [
                AUTH_OK,
                _feed(
                    [
                        _mention_entry(
                            "C111",
                            "1718972500.000000",
                            "UALICE",
                            thread_ts="1718972400.000000",
                        ),
                        _thread_entry("C222", "1718972700.000000", "1718972600.000000"),
                        _dm_entry("D333", "1718972900.000000"),
                    ]
                ),
                {"ok": True},
                {"ok": True},
                {"ok": True},
            ]
        )
        mock_post.side_effect = side_effect

        run(
            _make_args(
                [
                    _url("C111", "1718972500.000000", "1718972400.000000"),
                    _url("C222", "1718972700.000000", "1718972600.000000"),
                    _url("D333", "1718972900.000000"),
                ]
            ),
            _make_config(),
        )

        out = capsys.readouterr().out
        assert (
            "marked read: at_user at_user-C111-1718972500.000000-1718972400.000000"
            in out
        )
        assert "marked read: thread_v2 thread_v2-C222-1718972600.000000" in out
        assert "marked read: dm dm-D333" in out

        marked = _mark_calls(calls)
        assert len(marked) == 3
        assert marked[0] == {
            "token": "xoxc-test",
            "type": "at_user",
            "key": "at_user-C111-1718972500.000000-1718972400.000000",
            "feed_ts": "1718972500.000000",
        }
        assert marked[1] == {
            "token": "xoxc-test",
            "type": "thread_v2",
            "key": "thread_v2-C222-1718972600.000000",
            "feed_ts": "1718972700.000000",
        }
        assert marked[2] == {
            "token": "xoxc-test",
            "type": "dm",
            "key": "dm-D333",
            "feed_ts": "1718972900.000000",
            "ts": "1718972900.000000",
        }

    @patch("requests.post")
    def test_thread_url_ts_used_as_feed_ts_even_when_stale(self, mock_post, capsys):
        """Newer replies in feed must not bump feed_ts past the permalink's ts."""
        side_effect, calls = _mock_post(
            [
                AUTH_OK,
                _feed(
                    [_thread_entry("C222", "1718972700.000000", "1718972600.000000")]
                ),
                {"ok": True},
            ]
        )
        mock_post.side_effect = side_effect

        run(
            _make_args([_url("C222", "1718972500.000000", "1718972600.000000")]),
            _make_config(),
        )

        marked = _mark_calls(calls)
        assert len(marked) == 1
        assert marked[0]["feed_ts"] == "1718972500.000000"
        assert "marked read: thread_v2" in capsys.readouterr().out

    @patch("requests.post")
    def test_reply_permalink_marks_mention_not_thread(self, mock_post, capsys):
        """A reply permalink matching both a mention and a thread marks the mention."""
        side_effect, calls = _mock_post(
            [
                AUTH_OK,
                _feed(
                    [
                        _mention_entry(
                            "C111",
                            "1718972500.000000",
                            "UALICE",
                            thread_ts="1718972400.000000",
                        ),
                        _thread_entry("C111", "1718972700.000000", "1718972400.000000"),
                    ]
                ),
                {"ok": True},
            ]
        )
        mock_post.side_effect = side_effect

        run(
            _make_args([_url("C111", "1718972500.000000", "1718972400.000000")]),
            _make_config(),
        )

        marked = _mark_calls(calls)
        assert len(marked) == 1
        assert marked[0]["type"] == "at_user"

    @patch("requests.post")
    def test_already_read_url_warns_and_continues(self, mock_post, capsys):
        side_effect, calls = _mock_post(
            [
                AUTH_OK,
                _feed([_dm_entry("D333", "1718972900.000000")]),
                {"ok": True},
            ]
        )
        mock_post.side_effect = side_effect

        run(
            _make_args(
                [_url("C999", "1718972500.000000"), _url("D333", "1718972900.000000")]
            ),
            _make_config(),
        )

        captured = capsys.readouterr()
        assert "Warning: not in unread activity feed" in captured.err
        assert "C999" in captured.err
        assert "marked read: dm dm-D333" in captured.out
        assert len(_mark_calls(calls)) == 1

    @patch("requests.post")
    def test_malformed_url_exits_1(self, mock_post, capsys):
        with pytest.raises(SystemExit) as e:
            run(_make_args(["https://example.com/not-a-slack-link"]), _make_config())
        assert e.value.code == 1
        assert "Invalid Slack link format" in capsys.readouterr().err

    @patch("requests.post")
    def test_mark_api_error_exits_1(self, mock_post, capsys):
        side_effect, _ = _mock_post(
            [
                AUTH_OK,
                _feed([_dm_entry("D333", "1718972900.000000")]),
                {"ok": False, "error": "mark_read_failed"},
            ]
        )
        mock_post.side_effect = side_effect

        with pytest.raises(SystemExit) as e:
            run(_make_args([_url("D333", "1718972900.000000")]), _make_config())
        assert e.value.code == 1
        assert "failed to mark" in capsys.readouterr().err

    @patch("requests.post")
    def test_missing_tokens_exits(self, mock_post, capsys):
        with pytest.raises(SystemExit) as e:
            run(
                _make_args([_url("D333", "1718972900.000000")]),
                _make_config(xoxc_token=None, xoxd_token=None),
            )
        assert e.value.code == 2

    @patch("requests.post")
    def test_feed_api_error_exits(self, mock_post, capsys):
        mock_post.side_effect, _ = _mock_post(
            [AUTH_OK, {"ok": False, "error": "invalid_auth"}]
        )
        with pytest.raises(SystemExit) as e:
            run(_make_args([_url("D333", "1718972900.000000")]), _make_config())
        assert e.value.code == 2
        assert "Authentication failed" in capsys.readouterr().err

    @patch("requests.post")
    def test_entry_without_key_not_indexed(self, mock_post, capsys):
        """Mention entries lacking a key cannot be marked; treated as not unread."""
        entry = _mention_entry("C111", "1718972500.000000", "UALICE")
        entry.pop("key")
        side_effect, calls = _mock_post([AUTH_OK, _feed([entry])])
        mock_post.side_effect = side_effect

        run(_make_args([_url("C111", "1718972500.000000")]), _make_config())

        captured = capsys.readouterr()
        assert "Warning: not in unread activity feed" in captured.err
        assert _mark_calls(calls) == []

    @patch("requests.post")
    def test_group_dm_marks_mpdm(self, mock_post, capsys):
        side_effect, calls = _mock_post(
            [
                AUTH_OK,
                _feed([_dm_entry("G444", "1718972900.000000", group=True)]),
                {"ok": True},
            ]
        )
        mock_post.side_effect = side_effect

        run(_make_args([_url("G444", "1718972900.000000")]), _make_config())

        marked = _mark_calls(calls)
        assert marked[0]["type"] == "mpdm"
        assert marked[0]["key"] == "mpdm-G444"
        assert "marked read: mpdm mpdm-G444" in capsys.readouterr().out
