from __future__ import annotations

import json
from collections.abc import AsyncIterator, Iterator
from typing import Any

import httpx

from fastlm_sdk.types import ChatCompletion, Message


def _headers(api_key: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }


def _iter_stream_deltas(lines: Iterator[str]) -> Iterator[str]:
    for line in lines:
        if not line.startswith("data: "):
            continue
        raw = line[6:].strip()
        if raw == "[DONE]":
            break
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError:
            continue
        err = obj.get("error")
        if err:
            raise RuntimeError(str(err))
        choices = obj.get("choices") or []
        if not choices:
            continue
        delta = choices[0].get("delta") or {}
        c = delta.get("content")
        if isinstance(c, str) and c:
            yield c


async def _aiter_stream_deltas(lines: AsyncIterator[str]) -> AsyncIterator[str]:
    async for line in lines:
        if not line.startswith("data: "):
            continue
        raw = line[6:].strip()
        if raw == "[DONE]":
            break
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError:
            continue
        err = obj.get("error")
        if err:
            raise RuntimeError(str(err))
        choices = obj.get("choices") or []
        if not choices:
            continue
        delta = choices[0].get("delta") or {}
        c = delta.get("content")
        if isinstance(c, str) and c:
            yield c


class FastLMClient:
    """Синхронний HTTP-клієнт до FastLM (базовий URL без завершального слешу)."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        timeout: float = 120.0,
    ) -> None:
        self._base = base_url.rstrip("/")
        self._api_key = api_key
        self._timeout = timeout

    def chat(
        self,
        *,
        model: str,
        messages: list[Message],
        temperature: float | None = 0.7,
        stream: bool = False,
    ) -> ChatCompletion:
        if stream:
            raise ValueError("Для stream використовуйте stream_chat()")
        payload: dict[str, Any] = {
            "model": model,
            "messages": [m.to_api() for m in messages],
            "stream": False,
        }
        if temperature is not None:
            payload["temperature"] = temperature
        with httpx.Client(timeout=self._timeout) as client:
            r = client.post(
                f"{self._base}/v1/chat/completions",
                headers=_headers(self._api_key),
                json=payload,
            )
        r.raise_for_status()
        return ChatCompletion(raw=r.json())

    def stream_chat(
        self,
        *,
        model: str,
        messages: list[Message],
        temperature: float | None = 0.7,
    ) -> Iterator[str]:
        payload: dict[str, Any] = {
            "model": model,
            "messages": [m.to_api() for m in messages],
            "stream": True,
        }
        if temperature is not None:
            payload["temperature"] = temperature
        with httpx.Client(timeout=self._timeout) as client:
            with client.stream(
                "POST",
                f"{self._base}/v1/chat/completions",
                headers=_headers(self._api_key),
                json=payload,
            ) as r:
                r.raise_for_status()
                yield from _iter_stream_deltas(r.iter_lines())


class AsyncFastLMClient:
    """Асинхронний клієнт (httpx.AsyncClient)."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        timeout: float = 120.0,
    ) -> None:
        self._base = base_url.rstrip("/")
        self._api_key = api_key
        self._timeout = timeout

    async def chat(
        self,
        *,
        model: str,
        messages: list[Message],
        temperature: float | None = 0.7,
    ) -> ChatCompletion:
        payload: dict[str, Any] = {
            "model": model,
            "messages": [m.to_api() for m in messages],
            "stream": False,
        }
        if temperature is not None:
            payload["temperature"] = temperature
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            r = await client.post(
                f"{self._base}/v1/chat/completions",
                headers=_headers(self._api_key),
                json=payload,
            )
        r.raise_for_status()
        return ChatCompletion(raw=r.json())

    async def stream_chat(
        self,
        *,
        model: str,
        messages: list[Message],
        temperature: float | None = 0.7,
    ) -> AsyncIterator[str]:
        payload: dict[str, Any] = {
            "model": model,
            "messages": [m.to_api() for m in messages],
            "stream": True,
        }
        if temperature is not None:
            payload["temperature"] = temperature
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            async with client.stream(
                "POST",
                f"{self._base}/v1/chat/completions",
                headers=_headers(self._api_key),
                json=payload,
            ) as r:
                r.raise_for_status()
                async for chunk in _aiter_stream_deltas(r.aiter_lines()):
                    yield chunk
