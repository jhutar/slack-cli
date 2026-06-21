from datetime import datetime, timezone

from slack_cli.formatter import format_messages


def _msg(text="hello", user_name="alice", ts="1718972400.000000", replies=None, files=None):
    return {
        "text": text,
        "user_name": user_name,
        "ts": ts,
        "datetime": datetime(2025, 6, 21, 14, 0, 0, tzinfo=timezone.utc),
        "replies": replies or [],
        "files": files or [],
    }


def test_single_message():
    result = format_messages([_msg()])
    assert "### @alice (2025-06-21 14:00 UTC)" in result
    assert "hello" in result
    assert "---" in result


def test_message_with_file_attachment():
    msg = _msg(text="", files=[{"name": "report.pdf"}])
    result = format_messages([msg])
    assert "[Attachment: report.pdf]" in result


def test_thread_output_with_sub_numbering():
    parent = _msg(
        text="parent message",
        replies=[
            _msg(text="reply one", user_name="bob"),
            _msg(text="reply two", user_name="carol"),
        ],
    )
    result = format_messages([parent])
    assert "### 1. @alice" in result
    assert "#### 1.1. @bob" in result
    assert "#### 1.2. @carol" in result
    assert "parent message" in result
    assert "reply one" in result
    assert "reply two" in result


def test_multiple_messages_numbered():
    msgs = [
        _msg(text="first"),
        _msg(text="second", user_name="bob"),
    ]
    result = format_messages(msgs)
    assert "### 1. @alice" in result
    assert "### 2. @bob" in result
