from slack_cli.mrkdwn import convert, to_mrkdwn


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


# --- to_mrkdwn (markdown -> Slack mrkdwn) ---


def test_to_mrkdwn_bold():
    assert to_mrkdwn("**bold text**") == "*bold text*"


def test_to_mrkdwn_bold_underscores():
    assert to_mrkdwn("__bold text__") == "*bold text*"


def test_to_mrkdwn_italic():
    assert to_mrkdwn("*italic text*") == "_italic text_"


def test_to_mrkdwn_italic_underscores_unchanged():
    assert to_mrkdwn("_italic text_") == "_italic text_"


def test_to_mrkdwn_strikethrough():
    assert to_mrkdwn("~~struck text~~") == "~struck text~"


def test_to_mrkdwn_mixed_formatting():
    result = to_mrkdwn("**bold** and *italic* and ~~struck~~")
    assert result == "*bold* and _italic_ and ~struck~"


def test_to_mrkdwn_inline_code_unchanged():
    assert to_mrkdwn("`**not bold**`") == "`**not bold**`"


def test_to_mrkdwn_fenced_code_block_unchanged():
    text = "before ```\n**not bold**\n``` after **bold**"
    result = to_mrkdwn(text)
    assert "**not bold**" in result
    assert "*bold*" in result


def test_to_mrkdwn_link_with_display_text():
    assert (
        to_mrkdwn("[Click here](https://example.com)")
        == "<https://example.com|Click here>"
    )


def test_to_mrkdwn_bare_link_unchanged():
    assert to_mrkdwn("https://example.com") == "https://example.com"


def test_to_mrkdwn_heading():
    assert to_mrkdwn("# Heading") == "*Heading*"


def test_to_mrkdwn_heading_with_bold_not_doubled():
    assert to_mrkdwn("# **Bold heading**") == "*Bold heading*"


def test_to_mrkdwn_blockquote_unchanged():
    assert to_mrkdwn("> quoted text") == "> quoted text"


def test_to_mrkdwn_list_unchanged():
    assert to_mrkdwn("- item one\n- item two") == "- item one\n- item two"


def test_to_mrkdwn_spacing_not_italic():
    assert to_mrkdwn("a * b * c") == "a * b * c"


def test_to_mrkdwn_snake_case_not_bold():
    assert to_mrkdwn("some_var_name") == "some_var_name"
