from __future__ import annotations

import os
import re
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formatdate

SMTP_HOST = "smtp.qq.com"
SMTP_PORT = 465

WECHAT_COLOR_MAP = {
    "warning": "#D93026",
    "info": "#1AAD19",
    "comment": "#888888",
}


def _markdown_to_html(text: str) -> str:
    def font_sub(match: re.Match[str]) -> str:
        name = match.group(1)
        color = WECHAT_COLOR_MAP.get(name, name)
        return f'<span style="color:{color}">{match.group(2)}</span>'

    html = re.sub(r'<font color="([^"]+)">(.*?)</font>', font_sub, text, flags=re.DOTALL)
    html = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", html)

    lines: list[str] = []
    for line in html.split("\n"):
        stripped = line.strip()
        if stripped == "---":
            lines.append("<hr>")
        elif line.startswith("> "):
            lines.append(
                f'<div style="margin-left:1em;color:#555">{line[2:]}</div>'
            )
        else:
            lines.append(line + "<br>")
    return "\n".join(lines)


def render_markdown(text: str) -> str:
    return f'<div style="margin:8px 0">{_markdown_to_html(text)}</div>'


def render_table(headers: list[str], row_specs: list[dict]) -> str:
    """
    row_specs: list of {"cells": [html,...], "note": optional colspan note html}
    """
    th_style = (
        "padding:6px 10px;border-bottom:2px solid #333;text-align:left;"
        "background:#f0f0f0;font-weight:bold;white-space:nowrap"
    )
    td_style = "padding:6px 10px;border-bottom:1px solid #eee;white-space:nowrap"
    note_style = (
        "padding:2px 10px 6px;border-bottom:1px solid #eee;"
        f"color:{WECHAT_COLOR_MAP['warning']};font-size:12px"
    )

    thead = "".join(f'<th style="{th_style}">{h}</th>' for h in headers)
    body_rows: list[str] = []
    for spec in row_specs:
        tds = "".join(f'<td style="{td_style}">{c}</td>' for c in spec["cells"])
        body_rows.append(f"<tr>{tds}</tr>")
        note = spec.get("note")
        if note:
            body_rows.append(
                f'<tr><td colspan="{len(headers)}" style="{note_style}">{note}</td></tr>'
            )

    return (
        '<table cellpadding="0" cellspacing="0" border="0" '
        'style="border-collapse:collapse;font-size:13px;width:100%;margin:8px 0">'
        f"<thead><tr>{thead}</tr></thead>"
        f'<tbody>{"".join(body_rows)}</tbody>'
        "</table>"
    )


def send_email(subject: str, html_parts: list[str], image_path: str | None = None) -> None:
    smtp_user = os.environ.get("SMTP_USER", "").strip()
    smtp_pass = os.environ.get("SMTP_PASS", "").strip()
    receiver_email = os.environ.get("RECEIVER_EMAIL", "").strip()

    if not (smtp_user and smtp_pass and receiver_email):
        print("邮件未配置 (SMTP_USER/SMTP_PASS/RECEIVER_EMAIL 缺失)，跳过邮件推送")
        return

    receivers = [addr.strip() for addr in receiver_email.split(",") if addr.strip()]
    if not receivers:
        print("RECEIVER_EMAIL 为空，跳过邮件推送")
        return

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = smtp_user
    msg["To"] = ", ".join(receivers)
    msg["Date"] = formatdate(localtime=True)
    msg.set_content("本邮件为 HTML 格式，请使用支持 HTML 的客户端查看。")

    separator = '<hr style="border:0;border-top:1px solid #ddd;margin:12px 0">'
    html = (
        '<div style="font-family:-apple-system,BlinkMacSystemFont,PingFang SC,Microsoft YaHei,sans-serif;'
        'font-size:14px;line-height:1.6">'
        + separator.join(html_parts)
    )

    cid = None
    if image_path and os.path.exists(image_path):
        cid = "preview_image"
        html += f'{separator}<img src="cid:{cid}" style="max-width:100%">'
    html += "</div>"

    msg.add_alternative(html, subtype="html")

    if cid and image_path:
        with open(image_path, "rb") as image_file:
            image_bytes = image_file.read()
        html_part = msg.get_payload()[1]
        html_part.add_related(
            image_bytes, maintype="image", subtype="png", cid=f"<{cid}>"
        )

    context = ssl.create_default_context()
    with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=context, timeout=30) as server:
        server.login(smtp_user, smtp_pass)
        server.send_message(msg)
    print(f"邮件推送成功: {subject} -> {len(receivers)} 位收件人")
