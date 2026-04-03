from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from tests.helpers.module_loader import load_service_module


class _FakeHttpxResponse:
    def __init__(self, status_code: int, payload: dict, headers: dict | None = None) -> None:
        self.status_code = status_code
        self.headers = headers or {"content-type": "application/json"}
        self.content = json.dumps(payload).encode("utf-8")


class _FakeAsyncClient:
    def __init__(self, recorder: dict, timeout: float) -> None:
        self._recorder = recorder
        self._timeout = timeout

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def request(self, method, url, params=None, content=None, headers=None):
        self._recorder["method"] = method
        self._recorder["url"] = url
        self._recorder["params"] = list(params or [])
        self._recorder["body"] = content
        self._recorder["headers"] = dict(headers or {})
        self._recorder["timeout"] = self._timeout
        return _FakeHttpxResponse(
            200,
            {
                "status": "ok",
                "data": {"candidate_id": "cand_1", "full_name": "Ivan Petrov"},
            },
        )


class _FakeHttpxModule:
    class TimeoutException(Exception):
        pass

    class RequestError(Exception):
        pass

    def __init__(self, recorder: dict) -> None:
        self._recorder = recorder

    def AsyncClient(self, timeout: float):
        return _FakeAsyncClient(self._recorder, timeout=timeout)


def _load_gateway_module():
    project_root = Path(__file__).resolve().parents[2]
    return load_service_module(
        module_name="gateway_main_test",
        service_dir=project_root / "services" / "api",
        file_name="main.py",
    )


def _login_and_get_token(client: TestClient) -> str:
    response = client.post(
        "/api/v1/auth/login",
        json={"username": "hr", "password": "hr123"},
    )
    assert response.status_code == 200
    payload = response.json()
    return payload["access_token"]


def test_gateway_login_and_me_flow() -> None:
    gateway = _load_gateway_module()
    client = TestClient(gateway.app)

    token = _login_and_get_token(client)
    me_response = client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"})

    assert me_response.status_code == 200
    me_payload = me_response.json()
    assert me_payload["actor_type"] == "hr"
    assert me_payload["is_admin"] is False
    assert me_response.headers.get("X-Request-Id")


def test_gateway_proxy_forwards_actor_and_request_headers() -> None:
    gateway = _load_gateway_module()
    client = TestClient(gateway.app)

    recorder: dict = {}
    setattr(gateway, "httpx_module", _FakeHttpxModule(recorder))

    token = _login_and_get_token(client)
    response = client.get(
        "/api/v1/profiles/candidates/cand_1",
        params={"expand": "profile"},
        headers={
            "Authorization": f"Bearer {token}",
            "X-Request-Id": "req-proxy-1",
        },
    )

    assert response.status_code == 200
    assert recorder["method"] == "GET"
    assert recorder["url"] == "http://profile:8000/api/v1/profiles/candidates/cand_1"
    assert recorder["params"] == [("expand", "profile")]
    assert recorder["headers"]["X-Request-Id"] == "req-proxy-1"
    assert recorder["headers"]["X-Actor-Id"] == "u_hr"
    assert recorder["headers"]["X-Actor-Type"] == "hr"
    assert recorder["headers"]["X-Roles"] == "hr"
    assert response.headers.get("X-Request-Id") == "req-proxy-1"


def test_gateway_rate_limit_returns_429() -> None:
    gateway = _load_gateway_module()
    client = TestClient(gateway.app)

    token = _login_and_get_token(client)

    class _AlwaysDenyRateLimiter:
        def is_allowed(self, _key: str) -> bool:
            return False

    setattr(gateway, "rate_limiter", _AlwaysDenyRateLimiter())
    response = client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 429
    payload = response.json()
    assert payload["status"] == "error"
    assert payload["error"]["code"] == "rate_limited"
    assert response.headers.get("X-Request-Id")
