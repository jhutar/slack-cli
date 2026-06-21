import pytest

from slack_cli.link import SlackLink, parse_slack_link


def test_valid_channel_link():
    link = parse_slack_link(
        "https://mywork.slack.com/archives/C01234567/p1234567890123456"
    )
    assert link == SlackLink(
        workspace="mywork",
        channel_id="C01234567",
        message_ts="1234567890.123456",
        thread_ts=None,
        is_thread=False,
        is_reply=False,
    )


def test_link_with_thread_ts():
    link = parse_slack_link(
        "https://mywork.slack.com/archives/C01234567/p1234567890123456"
        "?thread_ts=1234567890.123456&cid=C01234567"
    )
    assert link.is_thread is True
    assert link.is_reply is False
    assert link.thread_ts == "1234567890.123456"


def test_link_with_reply():
    link = parse_slack_link(
        "https://mywork.slack.com/archives/C01234567/p1111111111222222"
        "?thread_ts=1234567890.123456&cid=C01234567"
    )
    assert link.is_thread is True
    assert link.is_reply is True
    assert link.message_ts == "1111111111.222222"
    assert link.thread_ts == "1234567890.123456"


def test_invalid_url():
    with pytest.raises(ValueError, match="Invalid Slack link"):
        parse_slack_link("https://not-a-slack-link.com/foo")


def test_missing_parts():
    with pytest.raises(ValueError, match="Invalid Slack link"):
        parse_slack_link("https://mywork.slack.com/archives/")


def test_dm_link_prefix():
    link = parse_slack_link(
        "https://mywork.slack.com/archives/D01234567/p1234567890123456"
    )
    assert link.channel_id == "D01234567"


def test_group_dm_link_prefix():
    link = parse_slack_link(
        "https://mywork.slack.com/archives/G01234567/p1234567890123456"
    )
    assert link.channel_id == "G01234567"


def test_workspace_with_hyphens():
    link = parse_slack_link(
        "https://my-company.slack.com/archives/C01234567/p1234567890123456"
    )
    assert link.workspace == "my-company"
