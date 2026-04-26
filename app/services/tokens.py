"""Підрахунок токенів через tiktoken (cl100k_base, як у сімействі GPT-4 / text-embedding-3)."""

from __future__ import annotations

from typing import Any

import tiktoken

_cached_encoding: tiktoken.Encoding | None = None


def _get_encoding() -> tiktoken.Encoding:
    global _cached_encoding
    if _cached_encoding is None:
        _cached_encoding = tiktoken.get_encoding("cl100k_base")
    return _cached_encoding


def count_text_tokens(text: str) -> int:
    if not text:
        return 0
    return len(_get_encoding().encode(text))


def count_messages_prompt_tokens(messages: list[dict[str, Any]] | None) -> int:
    """Сума токенів по полю content у повідомленнях (спрощено, без overhead ролей OpenAI)."""
    if not messages:
        return 0
    total = 0
    for m in messages:
        if not isinstance(m, dict):
            continue
        c = m.get("content")
        if isinstance(c, str):
            total += count_text_tokens(c)
    return total
