from __future__ import annotations

from fastapi.testclient import TestClient


def test_create_key_forbidden_without_secret(client: TestClient) -> None:
    r = client.post("/admin/keys", json={"label": "x"})
    assert r.status_code == 403


def test_create_key_ok_with_secret(client: TestClient) -> None:
    r = client.post(
        "/admin/keys",
        json={"label": "t"},
        headers={"X-Admin-Secret": "pytest-admin-secret-value-ok"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["api_key"].startswith("sk-")
    assert len(data["id"]) == 36
