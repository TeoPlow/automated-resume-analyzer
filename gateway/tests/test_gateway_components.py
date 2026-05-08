from __future__ import annotations

from typing import cast
from unittest.mock import AsyncMock

import httpx
import pytest
from common.exceptions import AppError

import gateway.app as gateway_app
from gateway.config import GatewayConfig
from gateway.schemas.auth import MeData
from gateway.services.auth_service import (
    AuthService,
    FallbackAuthStore,
    InMemoryAuthStore,
    RedisAuthStore,
)
from gateway.services.jwt_service import JwtService
from gateway.services.proxy_service import ProxyService


@pytest.mark.asyncio
class TestGatewayApp:
    async def test_build_auth_store_variants(self, gateway_auth_store_factory):
        assert isinstance(gateway_auth_store_factory("memory"), InMemoryAuthStore)
        assert isinstance(gateway_auth_store_factory("redis"), RedisAuthStore)
        assert isinstance(gateway_auth_store_factory("auto"), FallbackAuthStore)
        assert isinstance(
            gateway_auth_store_factory("something-else"),
            FallbackAuthStore,
        )

    async def test_lifespan_closes_services(self):
        auth_close = AsyncMock()
        proxy_close = AsyncMock()
        gateway_app.auth_service.close = auth_close
        gateway_app.proxy_service.close = proxy_close

        async with gateway_app.lifespan(gateway_app.app):
            pass

        auth_close.assert_awaited_once()
        proxy_close.assert_awaited_once()


class TestRateLimiter:
    @pytest.mark.asyncio
    async def test_check_enforces_sliding_window(
        self, monkeypatch, gateway_rate_limiter
    ):
        moments = [100.0, 101.0, 102.0, 111.5]
        monkeypatch.setattr(
            "gateway.services.rate_limiter.time.time",
            lambda: moments.pop(0) if moments else 111.5,
        )

        assert await gateway_rate_limiter.check("client-1") is True
        assert await gateway_rate_limiter.check("client-1") is True
        assert await gateway_rate_limiter.check("client-1") is False
        assert await gateway_rate_limiter.check("client-1") is True

    def test_extract_client_key_prefers_api_key(
        self,
        gateway_rate_limiter,
        gateway_request_factory,
    ):
        request = gateway_request_factory(headers=[(b"x-api-key", b"secret")])

        assert gateway_rate_limiter.extract_client_key(request).startswith("apikey:")

    def test_extract_client_key_prefers_authorization(
        self,
        gateway_rate_limiter,
        gateway_request_factory,
    ):
        request = gateway_request_factory(headers=[(b"authorization", b"Bearer token")])

        assert gateway_rate_limiter.extract_client_key(request).startswith("auth:")

    def test_extract_client_key_falls_back_to_ip(
        self,
        gateway_rate_limiter,
        gateway_request_factory,
    ):
        request = gateway_request_factory(client_host="10.0.0.10")

        assert gateway_rate_limiter.extract_client_key(request) == "ip:10.0.0.10"


@pytest.mark.asyncio
class TestProxyService:
    async def test_forward_builds_headers_and_strips_hop_by_hop(
        self,
        gateway_proxy_service: ProxyService,
        gateway_request_factory,
        gateway_config,
    ):
        captured: dict[str, object] = {}

        async def fake_request(**kwargs):
            captured.update(kwargs)
            return httpx.Response(
                status_code=202,
                content=b'{"ok":true}',
                headers={"x-custom": "1"},
            )

        gateway_proxy_service._client.request = fake_request  # type: ignore[method-assign]

        request = gateway_request_factory(
            method="POST",
            path="/api/v1/profiles/resumes/upload",
            headers=[
                (b"host", b"localhost"),
                (b"x-request-id", b"req-123"),
                (b"connection", b"keep-alive"),
                (b"content-type", b"application/json"),
            ],
            body=b'{"a":1}',
        )
        actor = MeData(actor_id="admin", actor_type="hr", permissions=["search:use"])

        response = await gateway_proxy_service.forward(
            request,
            "profiles",
            "resumes/upload",
            actor,
        )

        assert response.status_code == 202
        assert captured["method"] == "POST"
        assert (
            captured["url"]
            == f"{gateway_config.PROFILE_URL}/api/v1/profiles/resumes/upload"
        )
        assert captured["content"] == b'{"a":1}'
        headers = cast(dict[str, str], captured["headers"])
        assert headers["X-Actor-Id"] == "admin"
        assert headers["X-Actor-Type"] == "hr"
        assert headers["X-Permissions"] == "search:use"
        assert headers["X-Internal-Token"] == gateway_config.INTERNAL_TOKEN
        assert headers["X-Request-Id"] == "req-123"
        assert "connection" not in {k.lower() for k in headers}
        assert "host" not in {k.lower() for k in headers}
        assert response.headers["x-custom"] == "1"

    async def test_forward_raises_connect_error_as_app_error(
        self,
        gateway_proxy_service: ProxyService,
        gateway_request_factory,
        gateway_config,
    ):
        async def fail_request(**kwargs):
            raise httpx.ConnectError(
                "boom",
                request=httpx.Request(
                    "GET", f"{gateway_config.PROFILE_URL}/api/v1/profiles"
                ),
            )

        gateway_proxy_service._client.request = fail_request  # type: ignore[method-assign]
        request = gateway_request_factory(path="/api/v1/profiles")
        actor = MeData(actor_id="admin", actor_type="hr", permissions=[])

        with pytest.raises(AppError) as exc_info:
            await gateway_proxy_service.forward(request, "profiles", "", actor)

        assert exc_info.value.code == "service_unavailable"

    async def test_forward_raises_timeout_as_app_error(
        self,
        gateway_proxy_service: ProxyService,
        gateway_request_factory,
        gateway_config,
    ):
        async def fail_request(**kwargs):
            raise httpx.TimeoutException(
                "boom",
                request=httpx.Request(
                    "GET", f"{gateway_config.PROFILE_URL}/api/v1/profiles"
                ),
            )

        gateway_proxy_service._client.request = fail_request  # type: ignore[method-assign]
        request = gateway_request_factory(path="/api/v1/profiles")
        actor = MeData(actor_id="admin", actor_type="hr", permissions=[])

        with pytest.raises(AppError) as exc_info:
            await gateway_proxy_service.forward(request, "profiles", "", actor)

        assert exc_info.value.code == "service_timeout"

    async def test_unknown_service_raises_app_error(
        self, gateway_proxy_service: ProxyService
    ):
        with pytest.raises(AppError) as exc_info:
            gateway_proxy_service._resolve_service("unknown")

        assert exc_info.value.code == "unknown_service"


@pytest.mark.asyncio
class TestAuthServiceDirect:
    async def test_login_refresh_logout_and_keys(
        self,
        gateway_auth_service: AuthService,
        gateway_jwt_service: JwtService,
        gateway_fake_store,
        gateway_config,
    ):
        tokens = await gateway_auth_service.login(
            gateway_config.ADMIN_USERNAME,
            gateway_config.ADMIN_PASSWORD,
        )
        access_payload = gateway_jwt_service.decode(tokens.access_token)
        refresh_payload = gateway_jwt_service.decode(tokens.refresh_token)
        assert access_payload["sub"] == gateway_config.ADMIN_USERNAME
        assert refresh_payload["type"] == "refresh"

        me = await gateway_auth_service.authenticate_request(
            authorization=f"Bearer {tokens.access_token}",
            api_key=None,
        )
        assert me.actor_id == gateway_config.ADMIN_USERNAME

        integration = await gateway_auth_service.create_integration_key(
            "bot",
            ["resumes:upload"],
        )
        assert integration.name == "bot"
        assert integration.api_key

        api_me = await gateway_auth_service.authenticate_request(
            authorization=None,
            api_key=integration.api_key,
        )
        assert api_me.actor_type == "integration"
        assert api_me.actor_id.startswith("integration:")

        keys = await gateway_auth_service.list_integration_keys()
        assert keys[0].name == "bot"

        rotated = await gateway_auth_service.rotate_integration_key(integration.key_id)
        assert rotated.name == "bot"

        await gateway_auth_service.revoke_integration_key(rotated.key_id)
        await gateway_auth_service.logout(tokens.refresh_token)
        assert gateway_fake_store.blacklisted

    async def test_refresh_and_authenticate_error_paths(
        self,
        gateway_auth_service: AuthService,
        gateway_jwt_service: JwtService,
        gateway_config,
    ):
        access_token = gateway_jwt_service.create_access_token(
            actor_id=gateway_config.ADMIN_USERNAME,
            actor_type="hr",
            permissions=["search:use"],
        )
        with pytest.raises(AppError) as exc_info:
            await gateway_auth_service.refresh(access_token)
        assert exc_info.value.code == "invalid_token"

        refresh_token, _ = gateway_jwt_service.create_refresh_token(
            actor_id=gateway_config.ADMIN_USERNAME,
        )
        with pytest.raises(AppError) as exc_info:
            await gateway_auth_service.authenticate_request(
                authorization=f"Bearer {refresh_token}",
                api_key=None,
            )
        assert exc_info.value.code == "invalid_token"

        with pytest.raises(AppError) as exc_info:
            await gateway_auth_service.authenticate_request(
                authorization=None,
                api_key=None,
            )
        assert exc_info.value.code == "unauthorized"

    async def test_refresh_rejects_blacklisted_and_missing_users(
        self,
        gateway_auth_service: AuthService,
        gateway_jwt_service: JwtService,
        gateway_fake_store,
    ):
        refresh_token, jti = gateway_jwt_service.create_refresh_token(actor_id="ghost")
        gateway_fake_store.blacklisted.add(jti)
        with pytest.raises(AppError) as exc_info:
            await gateway_auth_service.refresh(refresh_token)
        assert exc_info.value.code == "token_revoked"

        gateway_fake_store.blacklisted.clear()
        with pytest.raises(AppError) as exc_info:
            await gateway_auth_service.refresh(refresh_token)
        assert exc_info.value.code == "user_not_found"

    async def test_logout_swallows_invalid_token_and_refresh_ttl_uses_exp(
        self,
        gateway_auth_service: AuthService,
        gateway_config,
        monkeypatch,
    ):
        monkeypatch.setattr("gateway.services.auth_service.time.time", lambda: 1000)

        await gateway_auth_service.logout("not-a-token")
        assert gateway_auth_service._resolve_refresh_blacklist_ttl({"exp": 1010}) == 10
        assert (
            gateway_auth_service._resolve_refresh_blacklist_ttl({})
            == gateway_config.JWT_REFRESH_TTL
        )


@pytest.mark.asyncio
class TestGatewayRoutersViaClient:
    async def test_integrations_router_full_crud(
        self,
        client,
        admin_credentials,
        hr_credentials,
        gateway_login,
    ):
        admin_username, admin_password = admin_credentials
        hr_username, hr_password = hr_credentials

        admin_token = await gateway_login(admin_username, admin_password)
        hr_token = await gateway_login(hr_username, hr_password)

        forbidden = await client.post(
            "/api/v1/integrations/keys",
            headers={"Authorization": f"Bearer {hr_token}"},
            json={"name": "bot", "permissions": ["resumes:upload"]},
        )
        assert forbidden.status_code == 403

        created = await client.post(
            "/api/v1/integrations/keys",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"name": "bot", "permissions": ["resumes:upload"]},
        )
        assert created.status_code == 200
        key_id = created.json()["data"]["key_id"]
        api_key = created.json()["data"]["api_key"]

        listed = await client.get(
            "/api/v1/integrations/keys",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert listed.status_code == 200
        assert listed.json()["data"]

        rotated = await client.post(
            f"/api/v1/integrations/keys/{key_id}/rotate",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert rotated.status_code == 200
        assert rotated.json()["data"]["api_key"] != api_key

        deleted = await client.delete(
            f"/api/v1/integrations/keys/{rotated.json()['data']['key_id']}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert deleted.status_code == 204

    async def test_proxy_router_forwards_root_and_subpath(
        self,
        client,
        admin_credentials,
        monkeypatch,
        gateway_login,
    ):
        username, password = admin_credentials
        token = await gateway_login(username, password)

        forward = AsyncMock(
            return_value=httpx.Response(
                status_code=200,
                content=b'{"ok":true}',
            )
        )
        monkeypatch.setattr(gateway_app.proxy_service, "forward", forward)

        root_response = await client.get(
            "/api/v1/profiles",
            headers={"Authorization": f"Bearer {token}", "X-Request-Id": "req-1"},
        )
        assert root_response.status_code == 200

        sub_response = await client.post(
            "/api/v1/profiles/resumes/upload",
            headers={"Authorization": f"Bearer {token}"},
            json={"source": "web"},
        )
        assert sub_response.status_code == 200

        assert forward.await_count == 2
        assert forward.await_args_list[0].args[1] == "profiles"
        assert forward.await_args_list[0].args[2] == ""
        assert forward.await_args_list[1].args[2] == "resumes/upload"

    async def test_proxy_router_rate_limit_and_unknown_service(
        self,
        client,
        admin_credentials,
        monkeypatch,
        gateway_login,
    ):
        username, password = admin_credentials
        token = await gateway_login(username, password)

        monkeypatch.setattr(
            gateway_app.rate_limiter, "check", AsyncMock(return_value=False)
        )
        denied = await client.get(
            "/api/v1/profiles",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert denied.status_code == 429

        monkeypatch.setattr(
            gateway_app.rate_limiter, "check", AsyncMock(return_value=True)
        )
        unknown = await client.get(
            "/api/v1/unknown-service",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert unknown.status_code == 404
