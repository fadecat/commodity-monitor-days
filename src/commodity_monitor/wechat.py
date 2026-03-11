from __future__ import annotations

from typing import Iterable

import requests


def _split_paragraphs(text: str) -> list[str]:
    parts = text.split("\n\n")
    return [part for part in parts if part]


def _split_oversize_paragraph(paragraph: str, max_chars: int) -> list[str]:
    """
    Fallback for rare oversize paragraph.
    Keep line boundaries where possible; hard-cut only if one line itself is too long.
    """
    out: list[str] = []
    current = ""
    for line in paragraph.splitlines():
        candidate = line if not current else f"{current}\n{line}"
        if len(candidate) <= max_chars:
            current = candidate
            continue

        if current:
            out.append(current)
            current = ""

        if len(line) <= max_chars:
            current = line
            continue

        # Last resort: hard split an oversized single line.
        for idx in range(0, len(line), max_chars):
            out.append(line[idx : idx + max_chars])

    if current:
        out.append(current)
    return out


def split_message(text: str, max_chars: int) -> list[str]:
    if max_chars <= 20:
        raise ValueError("max_chars must be > 20")
    if len(text) <= max_chars:
        return [text]

    paragraphs = _split_paragraphs(text)
    chunks: list[str] = []
    current = ""

    for para in paragraphs:
        if len(para) > max_chars:
            # Flush previous block first, then split this oversize paragraph.
            if current:
                chunks.append(current)
                current = ""
            chunks.extend(_split_oversize_paragraph(para, max_chars=max_chars))
            continue

        candidate = para if not current else f"{current}\n\n{para}"
        if len(candidate) <= max_chars:
            current = candidate
        else:
            chunks.append(current)
            current = para

    if current:
        chunks.append(current)

    return chunks


def send_wechat_markdown(
    webhook_url: str, content: str, timeout_seconds: int = 20
) -> dict[str, object]:
    payload = {"msgtype": "markdown", "markdown": {"content": content}}
    resp = requests.post(webhook_url, json=payload, timeout=timeout_seconds)
    resp.raise_for_status()
    data = resp.json()
    if data.get("errcode") != 0:
        raise RuntimeError(f"WeChat API error: {data}")
    return data


def send_in_chunks(
    webhook_url: str, content: str, max_chars: int, timeout_seconds: int = 20
) -> Iterable[dict[str, object]]:
    for chunk in split_message(content, max_chars=max_chars):
        yield send_wechat_markdown(
            webhook_url=webhook_url, content=chunk, timeout_seconds=timeout_seconds
        )
