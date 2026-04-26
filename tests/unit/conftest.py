from __future__ import annotations

import os
from collections.abc import Iterator
from unittest.mock import AsyncMock

import pytest
import redis.asyncio as aioredis

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("ADMIN_SECRET", "pytest-admin-secret-value-ok")
os.environ.setdefault("WEBHOOK_HMAC_SECRET", "whsec-pytest-test")
os.environ.setdefault("OPENAI_API_KEY", "")

_redis: AsyncMock | None = None


def _make_redis() -> AsyncMock:
    global _redis
    m = AsyncMock()
    m.incr = AsyncMock(return_value=1)
    m.expire = AsyncMock(return_value=True)
    m.close = AsyncMock()
    m.aclose = AsyncMock()
    _redis = m
    return m


def _from_url(*_a, **_kw) -> AsyncMock:
    return _make_redis()


aioredis.from_url = _from_url  # type: ignore[method-assign]

from app.main import app  # noqa: E402


@pytest.fixture
def client() -> Iterator:
    from fastapi.testclient import TestClient

    with TestClient(app) as c:
        yield c


@pytest.fixture
def redis_mock() -> AsyncMock:
    assert _redis is not None
    return _redis
