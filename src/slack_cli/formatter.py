def format_messages(messages):
    lines = []
    use_numbering = len(messages) > 1 or any(m.get("replies") for m in messages)

    for i, msg in enumerate(messages, 1):
        _format_message(lines, msg, i, use_numbering)
        lines.append("")
        lines.append("---")
        lines.append("")

    return "\n".join(lines).rstrip("\n") + "\n"


def _format_message(lines, msg, number, use_numbering):
    dt = msg["datetime"]
    timestamp = dt.strftime("%Y-%m-%d %H:%M UTC")
    user = msg["user_name"]

    if use_numbering:
        lines.append(f"### {number}. @{user} ({timestamp})")
    else:
        lines.append(f"### @{user} ({timestamp})")

    lines.append("")

    text = msg.get("text", "")
    files = msg.get("files", [])

    if text:
        lines.append(text)
    elif files:
        for f in files:
            lines.append(f"[Attachment: {f.get('name', 'unknown')}]")
    else:
        lines.append("[Attachment: unknown]")

    for j, reply in enumerate(msg.get("replies", []), 1):
        lines.append("")
        reply_dt = reply["datetime"]
        reply_ts = reply_dt.strftime("%Y-%m-%d %H:%M UTC")
        reply_user = reply["user_name"]
        lines.append(f"#### {number}.{j}. @{reply_user} ({reply_ts})")
        lines.append("")
        reply_text = reply.get("text", "")
        if reply_text:
            lines.append(reply_text)
        else:
            reply_files = reply.get("files", [])
            if reply_files:
                for f in reply_files:
                    lines.append(f"[Attachment: {f.get('name', 'unknown')}]")
            else:
                lines.append("[Attachment: unknown]")
