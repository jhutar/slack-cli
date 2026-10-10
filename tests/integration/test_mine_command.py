import argparse
from unittest.mock import MagicMock, patch

from slack_cli.commands.mine import run

HOST = "test.slack.com"
ME = "UME"

AUTH_OK = {"ok": True, "user_id": ME, "url": f"https://{HOST}"}
PROFILE_OK = {"ok": True, "profile": {"username": "me"}}


def _make_config(**overrides):
    cfg = {
        "xoxc_token": "xoxc-test",
        "xoxd_token": "xoxd-test",
        "user_agent": None,
        "cache_ttl": 86400,
    }
    cfg.update(overrides)
    return cfg


def _make_args(days=7, collapsed=False, csv=False):
    return argparse.Namespace(days=days, collapsed=collapsed, csv=csv)


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


def _msg(channel, ts, mtype="message", thread_ts=None):
    m = {"type": mtype, "user": ME, "ts": ts, "channel": channel}
    if thread_ts:
        m["thread_ts"] = thread_ts
    return m


def _search(matches):
    return {"ok": True, "messages": {"total_count": len(matches), "matches": matches}}


# Search matches, newest first: group DM, two DMs, two channel
# top-levels, two thread replies.
MATCHES = [
    _msg("G333", "1791591100.000000", mtype="mpim"),
    _msg("D222", "1791591000.000000", mtype="im"),
    _msg("D222", "1791590900.000000", mtype="im"),
    _msg("C111", "1791590800.000000"),
    _msg("C111", "1791590700.000000"),
    _msg("C111", "1791590600.000000", thread_ts="1791590400.000000"),
    _msg("C111", "1791590500.000000", thread_ts="1791590400.000000"),
]


def _thread_lookups_empty(count):
    """conversations.history + conversations.replies pairs returning nothing."""
    return [{"ok": True, "messages": []}] * (count * 2)


PRELOADED_CACHE = {
    "users": {"UCAROL": "Carol", "UDAVE": "Dave", "UERIN": "Erin"},
    "channels": {"C111": "eng"},
    "dms": {
        "D222": {"members": ["UCAROL"], "is_im": True},
        "G333": {"members": ["UDAVE", "UERIN"], "is_im": False},
    },
}


def _responses(matches):
    """Full API response queue for a run() over the given search matches.

    Top-level messages (no thread_ts) each cost two lookups.
    """
    top_level = sum(1 for m in matches if not m.get("thread_ts"))
    return [
        AUTH_OK,
        PROFILE_OK,
        _search(matches),
        *_thread_lookups_empty(top_level),
    ]


class TestMineCommand:
    @patch("slack_cli.commands._shared.load_cache", return_value=PRELOADED_CACHE)
    @patch("slack_cli.commands._shared.save_cache")
    @patch("requests.post")
    def test_expanded_default(self, mock_post, mock_save, mock_load, capsys):
        mock_post.side_effect, _ = _mock_post(_responses(MATCHES))

        run(_make_args(), _make_config())

        out = capsys.readouterr().out
        assert "## Your messages (7)" in out
        assert "1. Group DM Dave, Erin · 2026-10-10 00:11 UTC" in out
        assert f"https://{HOST}/archives/G333/p1791591100000000" in out
        assert "2. DM Carol · 2026-10-10 00:10 UTC" in out
        assert f"https://{HOST}/archives/D222/p1791591000000000" in out
        # Thread replies listed flat, no thread param
        assert "4. #eng · 2026-10-10 00:06 UTC" in out
        assert f"https://{HOST}/archives/C111/p1791590800000000\n" in out
        assert "7. #eng · 2026-10-10 00:01 UTC" in out
        assert "?thread_ts" not in out
        assert "## Threads" not in out

    @patch("slack_cli.commands._shared.load_cache", return_value=PRELOADED_CACHE)
    @patch("slack_cli.commands._shared.save_cache")
    @patch("requests.post")
    def test_collapsed_display(self, mock_post, mock_save, mock_load, capsys):
        mock_post.side_effect, _ = _mock_post(_responses(MATCHES))

        run(_make_args(collapsed=True), _make_config())

        out = capsys.readouterr().out
        assert "## Threads you participated in (1)" in out
        assert "1. #eng · you, last 2026-10-10 00:03 UTC · 2 replies by you" in out
        assert (
            f"https://{HOST}/archives/C111/p1791590400000000"
            "?thread_ts=1791590400000000" in out
        )
        assert "## Your messages in channels and DMs (3)" in out
        # Single-message conversation: plain timestamp
        assert "1. Group DM Dave, Erin · 2026-10-10 00:11 UTC" in out
        assert f"https://{HOST}/archives/G333/p1791591100000000" in out
        # Multi-message conversations: first ts + count, link to earliest
        assert "2. DM Carol · you, first 2026-10-10 00:08 UTC · 2 by you" in out
        assert f"https://{HOST}/archives/D222/p1791590900000000" in out
        assert "3. #eng · you, first 2026-10-10 00:05 UTC · 2 by you" in out
        assert f"https://{HOST}/archives/C111/p1791590700000000" in out

    @patch("slack_cli.commands._shared.load_cache", return_value=PRELOADED_CACHE)
    @patch("slack_cli.commands._shared.save_cache")
    @patch("requests.post")
    def test_csv_expanded(self, mock_post, mock_save, mock_load, capsys):
        mock_post.side_effect, _ = _mock_post(_responses(MATCHES))

        run(_make_args(csv=True), _make_config())

        out = capsys.readouterr().out
        assert out == (
            "link,source_type,from_where,from_time,to_time\n"
            f"https://{HOST}/archives/G333/p1791591100000000,group_dm,"
            '"Dave, Erin",2026-10-10T00:11:40Z,2026-10-10T00:11:40Z\n'
            f"https://{HOST}/archives/D222/p1791591000000000,dm,Carol,"
            "2026-10-10T00:10:00Z,2026-10-10T00:10:00Z\n"
            f"https://{HOST}/archives/D222/p1791590900000000,dm,Carol,"
            "2026-10-10T00:08:20Z,2026-10-10T00:08:20Z\n"
            f"https://{HOST}/archives/C111/p1791590800000000,channel,#eng,"
            "2026-10-10T00:06:40Z,2026-10-10T00:06:40Z\n"
            f"https://{HOST}/archives/C111/p1791590700000000,channel,#eng,"
            "2026-10-10T00:05:00Z,2026-10-10T00:05:00Z\n"
            f"https://{HOST}/archives/C111/p1791590600000000,thread,"
            "#eng@1791590400.000000,2026-10-10T00:03:20Z,2026-10-10T00:03:20Z\n"
            f"https://{HOST}/archives/C111/p1791590500000000,thread,"
            "#eng@1791590400.000000,2026-10-10T00:01:40Z,2026-10-10T00:01:40Z\n"
        )

    @patch("slack_cli.commands._shared.load_cache", return_value=PRELOADED_CACHE)
    @patch("slack_cli.commands._shared.save_cache")
    @patch("requests.post")
    def test_csv_collapsed(self, mock_post, mock_save, mock_load, capsys):
        mock_post.side_effect, _ = _mock_post(_responses(MATCHES))

        run(_make_args(collapsed=True, csv=True), _make_config())

        out = capsys.readouterr().out
        assert out == (
            "link,source_type,from_where,from_time,to_time\n"
            f"https://{HOST}/archives/G333/p1791591100000000,group_dm,"
            '"Dave, Erin",2026-10-10T00:11:40Z,2026-10-10T00:11:40Z\n'
            f"https://{HOST}/archives/D222/p1791590900000000,dm,Carol,"
            "2026-10-10T00:08:20Z,2026-10-10T00:10:00Z\n"
            f"https://{HOST}/archives/C111/p1791590700000000,channel,#eng,"
            "2026-10-10T00:05:00Z,2026-10-10T00:06:40Z\n"
            f"https://{HOST}/archives/C111/p1791590400000000"
            "?thread_ts=1791590400000000,thread,#eng@1791590400.000000,"
            "2026-10-10T00:00:00Z,2026-10-10T00:03:20Z\n"
        )

    @patch("slack_cli.commands._shared.load_cache", return_value=PRELOADED_CACHE)
    @patch("slack_cli.commands._shared.save_cache")
    @patch("requests.post")
    def test_collapsed_thread_root_excluded_from_channel(
        self, mock_post, mock_save, mock_load, capsys
    ):
        # I started the thread and replied in it: one thread entry,
        # no channel entry (the root is not a standalone message).
        matches = [
            _msg("C111", "1791591300.000000", thread_ts="1791591200.000000"),
            _msg("C111", "1791591200.000000"),
        ]
        mock_post.side_effect, _ = _mock_post(_responses(matches))

        run(_make_args(collapsed=True), _make_config())

        out = capsys.readouterr().out
        assert "## Threads you participated in (1)" in out
        assert "1. #eng · you, last 2026-10-10 00:15 UTC" in out
        assert (
            f"https://{HOST}/archives/C111/p1791591200000000"
            "?thread_ts=1791591200000000" in out
        )
        assert "## Your messages in channels and DMs" not in out

    @patch("slack_cli.commands._shared.load_cache", return_value=PRELOADED_CACHE)
    @patch("slack_cli.commands._shared.save_cache")
    @patch("requests.post")
    def test_empty_expanded_and_csv(self, mock_post, mock_save, mock_load, capsys):
        mock_post.side_effect, _ = _mock_post(_responses([]))

        run(_make_args(), _make_config())
        assert "No messages found in this window." in capsys.readouterr().out

        mock_post.side_effect, _ = _mock_post(_responses([]))
        run(_make_args(csv=True), _make_config())
        assert (
            capsys.readouterr().out == "link,source_type,from_where,from_time,to_time\n"
        )
