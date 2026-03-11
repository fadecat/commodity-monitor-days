from __future__ import annotations

from typing import Iterable

import requests


def _split_paragraphs(text: str) -> list[str]:
    parts = text.split("\n\n")
    return [part for part in parts if part]


def _utf8_len(text: str) -> int:
    return len(text.encode("utf-8"))


def _fits_limit(text: str, max_chars: int, max_bytes: int) -> bool:
    return len(text) <= max_chars and _utf8_len(text) <= max_bytes


def _hard_split_text(text: str, max_chars: int, max_bytes: int) -> list[str]:
    out: list[str] = []
    current = ""
    for ch in text:
        candidate = current + ch
        if _fits_limit(candidate, max_chars=max_chars, max_bytes=max_bytes):
            current = candidate
            continue
        if current:
            out.append(current)
            current = ch
        else:
            # Extremely small limit fallback
            out.append(ch)
            current = ""
    if current:
        out.append(current)
    return out


def _split_oversize_paragraph(paragraph: str, max_chars: int, max_bytes: int) -> list[str]:
    """
    Fallback for rare oversize paragraph.
    Keep line boundaries where possible; hard-cut only if one line itself is too long.
    """
    out: list[str] = []
    current = ""
    for line in paragraph.splitlines():
        candidate = line if not current else f"{current}\n{line}"
        if _fits_limit(candidate, max_chars=max_chars, max_bytes=max_bytes):
            current = candidate
            continue

        if current:
            out.append(current)
            current = ""

        if _fits_limit(line, max_chars=max_chars, max_bytes=max_bytes):
            current = line
            continue

        # Last resort: hard split an oversized single line.
        out.extend(_hard_split_text(line, max_chars=max_chars, max_bytes=max_bytes))

    if current:
        out.append(current)
    return out


def split_message(text: str, max_chars: int, max_bytes: int = 3900) -> list[str]:
    if max_chars <= 20:
        raise ValueError("max_chars must be > 20")
    if max_bytes <= 200:
        raise ValueError("max_bytes must be > 200")
    if _fits_limit(text, max_chars=max_chars, max_bytes=max_bytes):
        return [text]

    paragraphs = _split_paragraphs(text)
    chunks: list[str] = []
    current = ""

    for para in paragraphs:
        if not _fits_limit(para, max_chars=max_chars, max_bytes=max_bytes):
            # Flush previous block first, then split this oversize paragraph.
            if current:
                chunks.append(current)
                current = ""
            chunks.extend(
                _split_oversize_paragraph(
                    para, max_chars=max_chars, max_bytes=max_bytes
                )
            )
            continue

        candidate = para if not current else f"{current}\n\n{para}"
        if _fits_limit(candidate, max_chars=max_chars, max_bytes=max_bytes):
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
    for chunk in split_message(content, max_chars=max_chars, max_bytes=3900):
        yield send_wechat_markdown(
            webhook_url=webhook_url, content=chunk, timeout_seconds=timeout_seconds
        )
