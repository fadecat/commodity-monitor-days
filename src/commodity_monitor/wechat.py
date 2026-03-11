from __future__ import annotations

from typing import Iterable

import requests


def split_message(text: str, max_chars: int) -> list[str]:
    if max_chars <= 20:
        raise ValueError("max_chars must be > 20")
    if len(text) <= max_chars:
        return [text]

    chunks: list[str] = []
    current: list[str] = []
    current_len = 0

    for line in text.splitlines(keepends=True):
        line_len = len(line)
        if line_len > max_chars:
            if current:
                chunks.append("".join(current))
                current = []
                current_len = 0
            for idx in range(0, line_len, max_chars):
                chunks.append(line[idx : idx + max_chars])
            continue

        if current_len + line_len > max_chars:
            chunks.append("".join(current))
            current = [line]
            current_len = line_len
            continue

        current.append(line)
        current_len += line_len

    if current:
        chunks.append("".join(current))

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
