from slack_cli.mrkdwn import convert


def test_bold():
    assert convert("*bold text*") == "**bold text**"


def test_italic():
    assert convert("_italic text_") == "*italic text*"


def test_strikethrough():
    assert convert("~struck text~") == "~~struck text~~"


def test_inline_code_unchanged():
    assert convert("`code here`") == "`code here`"


def test_fenced_code_block_unchanged():
    text = "```\nsome code\n*not bold*\n```"
    assert convert(text) == "```\nsome code\n*not bold*\n```"


def test_link_with_display_text():
    assert (
        convert("<https://example.com|Click here>")
        == "[Click here](https://example.com)"
    )


def test_bare_link():
    assert convert("<https://example.com>") == "https://example.com"


def test_user_mention_with_map():
    user_map = {"U12345": "alice"}
    assert convert("<@U12345>", user_map=user_map) == "@alice"


def test_user_mention_without_map():
    assert convert("<@U12345>") == "@U12345"


def test_channel_ref():
    assert convert("<#C12345|general>") == "#general"


def test_channel_ref_with_map():
    channel_map = {"C12345": "general"}
    assert convert("<#C12345>", channel_map=channel_map) == "#general"


def test_special_mention_channel():
    assert convert("<!channel>") == "@channel"


def test_special_mention_here():
    assert convert("<!here>") == "@here"


def test_special_mention_everyone():
    assert convert("<!everyone>") == "@everyone"


def test_html_entity_amp():
    assert convert("&amp;") == "&"


def test_html_entity_lt():
    assert convert("&lt;") == "<"


def test_html_entity_gt():
    assert convert("&gt;") == ">"


def test_mixed_formatting():
    result = convert("*bold* and _italic_ and ~struck~")
    assert result == "**bold** and *italic* and ~~struck~~"


def test_code_block_preserves_mrkdwn():
    text = "before ```\n*bold* _italic_\n``` after *bold*"
    result = convert(text)
    assert "*bold* _italic_" in result
    assert "**bold**" in result
