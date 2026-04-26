from __future__ import annotations

from fastapi.testclient import TestClient


def test_completions_401_without_key(client: TestClient) -> None:
    r = client.post(
        "/v1/chat/completions",
        json={"model": "gpt-4o-mini", "messages": [{"role": "user", "content": "hi"}]},
    )
    assert r.status_code == 401


def test_completions_401_bad_key(client: TestClient) -> None:
    r = client.post(
        "/v1/chat/completions",
        headers={"Authorization": "Bearer sk-invalid"},
        json={"model": "gpt-4o-mini", "messages": [{"role": "user", "content": "hi"}]},
    )
    assert r.status_code == 401


def test_completions_200_mock(client: TestClient) -> None:
    k = client.post(
        "/admin/keys",
        json={"label": "c"},
        headers={"X-Admin-Secret": "pytest-admin-secret-value-ok"},
    ).json()["api_key"]
    r = client.post(
        "/v1/chat/completions",
        headers={"Authorization": f"Bearer {k}"},
        json={"model": "gpt-4o-mini", "messages": [{"role": "user", "content": "ping"}]},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["choices"][0]["message"]["content"]
    usage = data.get("usage") or {}
    assert usage.get("prompt_tokens", 0) > 0
    assert usage.get("completion_tokens", 0) > 0
