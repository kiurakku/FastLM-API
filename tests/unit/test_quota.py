from __future__ import annotations

from unittest.mock import AsyncMock

from fastapi.testclient import TestClient


def test_minute_quota_429(client: TestClient, redis_mock: AsyncMock) -> None:
    k = client.post(
        "/admin/keys",
        json={"label": "q"},
        headers={"X-Admin-Secret": "pytest-admin-secret-value-ok"},
    ).json()["api_key"]

    redis_mock.incr = AsyncMock(return_value=9999)

    r = client.post(
        "/v1/chat/completions",
        headers={"Authorization": f"Bearer {k}"},
        json={"model": "gpt-4o-mini", "messages": [{"role": "user", "content": "x"}]},
    )
    assert r.status_code == 429
