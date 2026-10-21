import re


def convert(text, user_map=None, channel_map=None):
    if user_map is None:
        user_map = {}
    if channel_map is None:
        channel_map = {}

    parts = _split_code_blocks(text)
    result = []
    for part, is_code in parts:
        if is_code:
            result.append(part)
        else:
            result.append(_convert_segment(part, user_map, channel_map))
    return "".join(result)


def _split_code_blocks(text):
    parts = []
    segments = re.split(r"(```[\s\S]*?```)", text)
    for segment in segments:
        if segment.startswith("```") and segment.endswith("```"):
            parts.append((segment, True))
        else:
            subsegments = re.split(r"(`[^`]+`)", segment)
            for sub in subsegments:
                if sub.startswith("`") and sub.endswith("`") and len(sub) > 1:
                    parts.append((sub, True))
                else:
                    parts.append((sub, False))
    return parts


def _convert_segment(text, user_map, channel_map):
    text = _resolve_user_mentions(text, user_map)
    text = _resolve_channel_refs(text, channel_map)
    text = _resolve_special_mentions(text)
    text = _convert_links(text)
    text = _convert_bold(text)
    text = _convert_italic(text)
    text = _convert_strikethrough(text)
    text = _decode_html_entities(text)
    return text


def _resolve_user_mentions(text, user_map):
    def replace(m):
        uid = m.group(1)
        name = user_map.get(uid, uid)
        return f"@{name}"

    return re.sub(r"<@(U[A-Z0-9]+)>", replace, text)


def _resolve_channel_refs(text, channel_map):
    def replace(m):
        cid = m.group(1)
        name = m.group(2)
        if name:
            return f"#{name}"
        return f"#{channel_map.get(cid, cid)}"

    return re.sub(r"<#([CDGW][A-Z0-9]+)(?:\|([^>]*))?>", replace, text)


def _resolve_special_mentions(text):
    text = re.sub(r"<!channel>", "@channel", text)
    text = re.sub(r"<!here>", "@here", text)
    text = re.sub(r"<!everyone>", "@everyone", text)
    return text


def _convert_links(text):
    def replace(m):
        url = m.group(1)
        display = m.group(2)
        if display:
            return f"[{display}]({url})"
        return url

    return re.sub(r"<(https?://[^|>]+)(?:\|([^>]+))?>", replace, text)


def _convert_bold(text):
    return re.sub(r"(?<![*\w])\*([^*\n]+)\*(?![*\w])", r"**\1**", text)


def _convert_italic(text):
    return re.sub(r"(?<![_\w])_([^_\n]+)_(?![_\w])", r"*\1*", text)


def _convert_strikethrough(text):
    return re.sub(r"(?<![~\w])~([^~\n]+)~(?![~\w])", r"~~\1~~", text)


def _decode_html_entities(text):
    text = text.replace("&amp;", "&")
    text = text.replace("&lt;", "<")
    text = text.replace("&gt;", ">")
    return text


# Marks already-converted bold spans so later passes cannot re-match them
# as italic (mrkdwn bold `*x*` is valid markdown italic `*x*`).
_BOLD = "\x00"


def to_mrkdwn(text):
    """Convert markdown text to Slack mrkdwn (inverse of convert)."""
    parts = _split_code_blocks(text)
    result = []
    for part, is_code in parts:
        result.append(part if is_code else _md_to_mrkdwn_segment(part))
    return "".join(result)


def _md_to_mrkdwn_segment(text):
    text = _md_links(text)
    text = _md_bold(text)
    text = _md_italic(text)
    text = _md_strikethrough(text)
    text = _md_headings(text)
    return text.replace(_BOLD, "*")


def _md_links(text):
    """[text](url) -> <url|text>"""
    return re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", r"<\2|\1>", text)


def _md_bold(text):
    """**x** and __x__ -> bold placeholder"""
    text = re.sub(
        r"(?<!\*)\*\*(?!\s)([^*\n]+?)(?<!\s)\*\*(?!\*)",
        rf"{_BOLD}\1{_BOLD}",
        text,
    )
    return re.sub(
        r"(?<!_)__(?!_)([^_\n]+?)(?<!_)__(?!_)",
        rf"{_BOLD}\1{_BOLD}",
        text,
    )


def _md_italic(text):
    """*x* -> _x_ (mrkdwn italic is _x_; markdown _x_ needs no change)"""
    return re.sub(r"(?<![\w*])\*(?!\s)([^*\n]+?)(?<!\s)\*(?![\w*])", r"_\1_", text)


def _md_strikethrough(text):
    """~~x~~ -> ~x~"""
    return re.sub(r"(?<!~)~~(?!\s)([^~\n]+?)(?<!\s)~~(?!~)", r"~\1~", text)


def _md_headings(text):
    """# Heading -> *Heading* (mrkdwn has no headings; bold the line)"""

    def repl(m):
        content = m.group(1)
        if content.startswith(_BOLD) and content.endswith(_BOLD):
            return content  # already bold; bold(bold(x)) == bold(x)
        return f"{_BOLD}{content}{_BOLD}"

    return re.sub(r"^#{1,6}[ \t]+(.+?)[ \t]*$", repl, text, flags=re.MULTILINE)
