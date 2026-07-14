import re
from dataclasses import dataclass
from urllib.parse import parse_qs, urlparse

SLACK_LINK_RE = re.compile(
    r"^https://([a-zA-Z0-9][a-zA-Z0-9-]*)\.slack\.com/archives/([CDGW][A-Z0-9]+)/p(\d+)$"
)


@dataclass
class SlackLink:
    workspace: str
    channel_id: str
    message_ts: str
    thread_ts: str | None
    is_thread: bool
    is_reply: bool


def _convert_timestamp(p_ts):
    if len(p_ts) <= 6:
        return p_ts + "." + "0" * (6 - len(p_ts))
    return p_ts[:-6] + "." + p_ts[-6:]


def parse_slack_link(url):
    parsed = urlparse(url)
    path_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
    match = SLACK_LINK_RE.match(path_url)
    if not match:
        raise ValueError(
            "Invalid Slack link format. Expected: "
            "https://<workspace>.slack.com/archives/<channel>/p<timestamp>"
        )

    workspace = match.group(1)
    channel_id = match.group(2)
    raw_ts = match.group(3)
    message_ts = _convert_timestamp(raw_ts)

    query = parse_qs(parsed.query)
    thread_ts = query.get("thread_ts", [None])[0]

    is_thread = thread_ts is not None
    is_reply = is_thread and thread_ts != message_ts

    return SlackLink(
        workspace=workspace,
        channel_id=channel_id,
        message_ts=message_ts,
        thread_ts=thread_ts,
        is_thread=is_thread,
        is_reply=is_reply,
    )
