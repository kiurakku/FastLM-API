"""Стримінг і SDK: потрібен запущений docker compose у корені FastLM-API."""

from __future__ import annotations

import asyncio
import os

import httpx
import pytest

FASTLM_BASE = os.environ.get("FASTLM_BASE", "http://127.0.0.1:8001").rstrip("/")
FASTLM_ADMIN_SECRET = os.environ.get("FASTLM_ADMIN_SECRET", "")


@pytest.fixture(scope="module")
def fastlm_api_key() -> str:
    if not FASTLM_ADMIN_SECRET:
        pytest.skip("FASTLM_ADMIN_SECRET не задано")
    r = httpx.post(
        f"{FASTLM_BASE}/admin/keys",
        headers={"X-Admin-Secret": FASTLM_ADMIN_SECRET},
        json={"label": "pytest-stream"},
        timeout=30.0,
    )
    assert r.status_code == 200, r.text
    key = r.json().get("api_key")
    assert isinstance(key, str) and key.startswith("sk-")
    return key


def test_sync_stream(fastlm_api_key: str) -> None:
    from fastlm_sdk import FastLMClient, Message

    c = FastLMClient(base_url=FASTLM_BASE, api_key=fastlm_api_key, timeout=60.0)
    parts = list(
        c.stream_chat(
            model="gpt-4o-mini",
            messages=[Message(role="user", content="stream test")],
        )
    )
    assert len(parts) >= 1
    assert len("".join(parts)) > 0


def test_async_stream(fastlm_api_key: str) -> None:
    from fastlm_sdk import AsyncFastLMClient, Message

    async def run() -> str:
        c = AsyncFastLMClient(base_url=FASTLM_BASE, api_key=fastlm_api_key, timeout=60.0)
        parts: list[str] = []
        async for d in c.stream_chat(
            model="gpt-4o-mini",
            messages=[Message(role="user", content="async stream")],
        ):
            parts.append(d)
        return "".join(parts)

    assert len(asyncio.run(run())) > 0
