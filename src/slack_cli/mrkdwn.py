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
