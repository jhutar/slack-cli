import argparse
from unittest.mock import MagicMock, patch

import pytest

from slack_cli.commands.write import run

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


def _make_args(target, message=None, file=None):
    return argparse.Namespace(target=target, message=message, file=file)


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


def _post_calls(calls):
    return [d for u, d in calls if "chat.postMessage" in u]


def _sent_text(calls):
    return _post_calls(calls)[0]["text"]


POST_OK = {"ok": True, "ts": "1718972500.000100", "channel": "C123"}
PERMALINK = {
    "ok": True,
    "permalink": f"https://{HOST}/archives/C123/p1718972500000100",
}
USERS_LIST = {
    "ok": True,
    "members": [
        {"id": "UALICE", "profile": {"display_name": "alice"}},
        {"id": "UBOB", "profile": {"display_name": "Bob Doe"}},
    ],
}
CHANNELS_LIST = {
    "ok": True,
    "channels": [{"id": "C9", "name": "general"}],
}


def _mention_entry(channel, ts, author, thread_ts=None):
    msg = {"ts": ts, "channel": channel, "author_user_id": author}
    key = f"at_user-{channel}-{ts}"
    if thread_ts:
        msg["thread_ts"] = thread_ts
        key += f"-{thread_ts}"
    return {
        "is_unread": True,
        "feed_ts": ts,
        "key": key,
        "item": {"type": "at_user", "message": msg},
    }


class TestWriteCommand:
    @patch("requests.post")
    def test_send_to_channel_id(self, mock_post, capsys):
        side_effect, calls = _mock_post([POST_OK, PERMALINK])
        mock_post.side_effect = side_effect

        run(_make_args("C123", "**bold** message"), _make_config())

        out = capsys.readouterr().out
        assert PERMALINK["permalink"] in out
        assert _sent_text(calls) == "*bold* message"
        posted = _post_calls(calls)[0]
        assert posted["channel"] == "C123"
        assert "thread_ts" not in posted
        assert posted["token"] == "xoxc-test"

    @patch("requests.post")
    def test_reply_link_starts_new_thread(self, mock_post, capsys):
        side_effect, calls = _mock_post([POST_OK, PERMALINK])
        mock_post.side_effect = side_effect

        run(
            _make_args(f"https://{HOST}/archives/C123/p1718972500000000", "new thread"),
            _make_config(),
        )

        posted = _post_calls(calls)[0]
        assert posted["channel"] == "C123"
        assert posted["thread_ts"] == "1718972500.000000"

    @patch("requests.post")
    def test_reply_into_existing_thread(self, mock_post, capsys):
        side_effect, calls = _mock_post([POST_OK, PERMALINK])
        mock_post.side_effect = side_effect

        run(
            _make_args(
                f"https://{HOST}/archives/C123/p1718972600000000"
                "?thread_ts=1718972500000000",
                "thread reply",
            ),
            _make_config(),
        )

        posted = _post_calls(calls)[0]
        assert posted["thread_ts"] == "1718972500.000000"

    @patch("requests.post")
    def test_send_to_user_id_opens_dm(self, mock_post, capsys):
        side_effect, calls = _mock_post(
            [
                {"ok": True, "channel": {"id": "D777", "is_im": True}},
                {"ok": True, "ts": "1718972500.000100", "channel": "D777"},
                PERMALINK,
            ]
        )
        mock_post.side_effect = side_effect

        run(_make_args("UALICE", "dm hello"), _make_config())

        posted = _post_calls(calls)[0]
        assert posted["channel"] == "D777"
        assert posted["text"] == "dm hello"
        opened = [d for u, d in calls if "conversations.open" in u][0]
        assert opened["users"] == "UALICE"

    @patch("sys.stdin", new=MagicMock())
    @patch("requests.post")
    def test_stdin_input(self, mock_post, capsys):
        import sys

        sys.stdin.isatty.return_value = False
        sys.stdin.read.return_value = "from *stdin*"
        side_effect, calls = _mock_post([POST_OK, PERMALINK])
        mock_post.side_effect = side_effect

        run(_make_args("C123"), _make_config())

        assert _sent_text(calls) == "from _stdin_"

    @patch("requests.post")
    def test_file_input(self, mock_post, capsys, tmp_path):
        path = tmp_path / "msg.md"
        path.write_text("# Heading\n\nbody")
        side_effect, calls = _mock_post([POST_OK, PERMALINK])
        mock_post.side_effect = side_effect

        run(_make_args("C123", file=str(path)), _make_config())

        assert _sent_text(calls) == "*Heading*\n\nbody"

    @patch("slack_cli.commands.write.DEFAULT_CACHE_DIR")
    @patch("requests.post")
    def test_user_mention_resolved(self, mock_post, cache_dir, capsys, tmp_path):
        cache_dir.__truediv__ = lambda self, name: tmp_path / name
        side_effect, calls = _mock_post([USERS_LIST, CHANNELS_LIST, POST_OK, PERMALINK])
        mock_post.side_effect = side_effect

        run(_make_args("C123", "hi @alice and @Bob Doe"), _make_config())

        assert _sent_text(calls) == "hi <@UALICE> and <@UBOB>"

    @patch("slack_cli.commands.write.DEFAULT_CACHE_DIR")
    @patch("requests.post")
    def test_special_mentions(self, mock_post, cache_dir, capsys, tmp_path):
        cache_dir.__truediv__ = lambda self, name: tmp_path / name
        side_effect, calls = _mock_post([POST_OK, PERMALINK])
        mock_post.side_effect = side_effect

        run(_make_args("C123", "yo @channel and @here"), _make_config())

        assert _sent_text(calls) == "yo <!channel> and <!here>"

    @patch("slack_cli.commands.write.DEFAULT_CACHE_DIR")
    @patch("requests.post")
    def test_channel_mention_resolved(self, mock_post, cache_dir, capsys, tmp_path):
        cache_dir.__truediv__ = lambda self, name: tmp_path / name
        side_effect, calls = _mock_post([USERS_LIST, CHANNELS_LIST, POST_OK, PERMALINK])
        mock_post.side_effect = side_effect

        run(_make_args("C123", "see #general"), _make_config())

        assert _sent_text(calls) == "see <#C9>"

    @patch("slack_cli.commands.write.DEFAULT_CACHE_DIR")
    @patch("requests.post")
    def test_mention_in_code_block_not_resolved(
        self, mock_post, cache_dir, capsys, tmp_path
    ):
        cache_dir.__truediv__ = lambda self, name: tmp_path / name
        side_effect, calls = _mock_post([POST_OK, PERMALINK])
        mock_post.side_effect = side_effect

        run(_make_args("C123", "run `@alice.sh` now"), _make_config())

        assert _sent_text(calls) == "run `@alice.sh` now"

    @patch("slack_cli.commands.write.DEFAULT_CACHE_DIR")
    @patch("requests.post")
    def test_heading_not_treated_as_channel_mention(
        self, mock_post, cache_dir, capsys, tmp_path
    ):
        cache_dir.__truediv__ = lambda self, name: tmp_path / name
        side_effect, calls = _mock_post([POST_OK, PERMALINK])
        mock_post.side_effect = side_effect

        run(_make_args("C123", "# Heading"), _make_config())

        assert _sent_text(calls) == "*Heading*"

    @patch("slack_cli.commands.write.DEFAULT_CACHE_DIR")
    @patch("requests.post")
    def test_unknown_mention_fails_loud(self, mock_post, cache_dir, capsys, tmp_path):
        cache_dir.__truediv__ = lambda self, name: tmp_path / name
        side_effect, calls = _mock_post([USERS_LIST, CHANNELS_LIST])
        mock_post.side_effect = side_effect

        with pytest.raises(SystemExit) as e:
            run(_make_args("C123", "hi @alce"), _make_config())
        assert e.value.code == 1
        captured = capsys.readouterr()
        assert "unknown user mention '@alce'" in captured.err
        assert "Did you mean: @alice" in captured.err
        assert _post_calls(calls) == []

    @patch("slack_cli.commands.write.DEFAULT_CACHE_DIR")
    @patch("requests.post")
    def test_ambiguous_mention_fails_loud(self, mock_post, cache_dir, capsys, tmp_path):
        cache_dir.__truediv__ = lambda self, name: tmp_path / name
        users = {
            "ok": True,
            "members": [
                {"id": "U1", "profile": {"display_name": "alice"}},
                {"id": "U2", "profile": {"display_name": "alice"}},
            ],
        }
        side_effect, calls = _mock_post([users, CHANNELS_LIST])
        mock_post.side_effect = side_effect

        with pytest.raises(SystemExit) as e:
            run(_make_args("C123", "hi @alice"), _make_config())
        assert e.value.code == 1
        assert "ambiguous" in capsys.readouterr().err
        assert _post_calls(calls) == []

    @patch("slack_cli.commands.write.DEFAULT_CACHE_DIR")
    @patch("requests.post")
    def test_email_not_treated_as_mention(self, mock_post, cache_dir, capsys, tmp_path):
        cache_dir.__truediv__ = lambda self, name: tmp_path / name
        side_effect, calls = _mock_post([POST_OK, PERMALINK])
        mock_post.side_effect = side_effect

        run(_make_args("C123", "mail me at bob@example.com"), _make_config())

        assert _sent_text(calls) == "mail me at bob@example.com"

    @patch("slack_cli.commands.write.DEFAULT_CACHE_DIR")
    @patch("requests.post")
    def test_mention_resolution_reuses_users_cache(
        self, mock_post, cache_dir, capsys, tmp_path
    ):
        from slack_cli.cache import save_cache

        cache_dir.__truediv__ = lambda self, name: tmp_path / name
        save_cache(tmp_path / "users.json", {"users": {"UALICE": "alice"}})
        side_effect, calls = _mock_post([POST_OK, PERMALINK])
        mock_post.side_effect = side_effect

        run(_make_args("C123", "hi @alice"), _make_config())

        assert _sent_text(calls) == "hi <@UALICE>"
        assert not [u for u, _ in calls if "users.list" in u]

    @patch("slack_cli.commands.write.DEFAULT_CACHE_DIR")
    @patch("requests.post")
    def test_reply_marks_parent_read(self, mock_post, cache_dir, capsys, tmp_path):
        cache_dir.__truediv__ = lambda self, name: tmp_path / name
        feed = {
            "ok": True,
            "items": [
                _mention_entry(
                    "C111",
                    "1718972500.000000",
                    "UALICE",
                    thread_ts="1718972400.000000",
                )
            ],
        }
        side_effect, calls = _mock_post(
            [POST_OK, PERMALINK, AUTH_OK, feed, {"ok": True}]
        )
        mock_post.side_effect = side_effect

        run(
            _make_args(
                f"https://{HOST}/archives/C111/p1718972500000000"
                "?thread_ts=1718972400000000",
                "reply",
            ),
            _make_config(),
        )

        marked = [d for u, d in calls if "activity.markRead" in u]
        assert marked == [
            {
                "token": "xoxc-test",
                "type": "at_user",
                "key": "at_user-C111-1718972500.000000-1718972400.000000",
                "feed_ts": "1718972500.000000",
            }
        ]

    @patch("slack_cli.commands.write.DEFAULT_CACHE_DIR")
    @patch("requests.post")
    def test_reply_parent_not_in_feed_warns(
        self, mock_post, cache_dir, capsys, tmp_path
    ):
        cache_dir.__truediv__ = lambda self, name: tmp_path / name
        side_effect, calls = _mock_post(
            [POST_OK, PERMALINK, AUTH_OK, {"ok": True, "items": []}]
        )
        mock_post.side_effect = side_effect

        run(
            _make_args(f"https://{HOST}/archives/C111/p1718972500000000", "reply"),
            _make_config(),
        )

        captured = capsys.readouterr()
        assert PERMALINK["permalink"] in captured.out
        assert "not in unread activity feed" in captured.err
        assert not [u for u, _ in calls if "activity.markRead" in u]

    @patch("requests.post")
    def test_invalid_target_exits_1(self, mock_post, capsys):
        with pytest.raises(SystemExit) as e:
            run(_make_args("not-a-target", "msg"), _make_config())
        assert e.value.code == 1
        assert "invalid target" in capsys.readouterr().err

    @patch("sys.stdin", new=MagicMock())
    @patch("requests.post")
    def test_empty_message_exits_1(self, mock_post, capsys):
        import sys

        sys.stdin.isatty.return_value = False
        sys.stdin.read.return_value = "   "
        with pytest.raises(SystemExit) as e:
            run(_make_args("C123"), _make_config())
        assert e.value.code == 1
        assert "empty" in capsys.readouterr().err

    @patch("requests.post")
    def test_missing_tokens_exits_2(self, mock_post, capsys):
        with pytest.raises(SystemExit) as e:
            run(
                _make_args("C123", "msg"),
                _make_config(xoxc_token=None, xoxd_token=None),
            )
        assert e.value.code == 2

    @patch("requests.post")
    def test_send_api_error_exits_3(self, mock_post, capsys):
        side_effect, _ = _mock_post([{"ok": False, "error": "channel_not_found"}])
        mock_post.side_effect = side_effect

        with pytest.raises(SystemExit) as e:
            run(_make_args("C999", "msg"), _make_config())
        assert e.value.code == 3
        assert "not found" in capsys.readouterr().err
