import pytest

pytestmark = pytest.mark.asyncio


class TestLogin:

    async def test_login_with_valid_credentials_returns_tokens(
        self, client, admin_credentials
    ):
        username, password = admin_credentials

        response = await client.post(
            "/api/v1/auth/login",
            json={"username": username, "password": password},
        )

        assert response.status_code == 200
        data = response.json()["data"]
        assert data["access_token"]
        assert data["refresh_token"]
        assert data["token_type"] == "bearer"

    async def test_login_with_invalid_password_returns_401(self, client):
        response = await client.post(
            "/api/v1/auth/login",
            json={"username": "admin", "password": "wrong"},
        )

        assert response.status_code == 401
        assert response.json()["error"]["code"] == "invalid_credentials"

    async def test_login_with_unknown_user_returns_401(self, client):
        response = await client.post(
            "/api/v1/auth/login",
            json={"username": "nobody", "password": "pass"},
        )

        assert response.status_code == 401

    async def test_login_hr_user_has_no_integrations_manage(
        self, client, hr_credentials
    ):
        username, password = hr_credentials

        response = await client.post(
            "/api/v1/auth/login",
            json={"username": username, "password": password},
        )

        assert response.status_code == 200
        token = response.json()["data"]["access_token"]
        me_resp = await client.get(
            "/api/v1/me", headers={"Authorization": f"Bearer {token}"}
        )
        assert "integrations:manage" not in me_resp.json()["data"]["permissions"]


class TestMe:

    async def test_me_with_valid_token_returns_actor(self, client, admin_credentials):
        username, password = admin_credentials
        login_resp = await client.post(
            "/api/v1/auth/login",
            json={"username": username, "password": password},
        )
        token = login_resp.json()["data"]["access_token"]

        response = await client.get(
            "/api/v1/me", headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 200
        data = response.json()["data"]
        assert data["actor_id"] == username
        assert data["actor_type"] == "hr"
        assert "integrations:manage" in data["permissions"]

    async def test_me_without_token_returns_401(self, client):
        response = await client.get("/api/v1/me")

        assert response.status_code == 401


class TestRefresh:

    async def test_refresh_returns_new_token_pair(self, client, admin_credentials):
        username, password = admin_credentials
        login_resp = await client.post(
            "/api/v1/auth/login",
            json={"username": username, "password": password},
        )
        refresh_token = login_resp.json()["data"]["refresh_token"]

        response = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": refresh_token},
        )

        assert response.status_code == 200
        data = response.json()["data"]
        assert data["access_token"]
        assert data["refresh_token"] != refresh_token

    async def test_refresh_with_reused_token_returns_401(
        self, client, admin_credentials
    ):
        username, password = admin_credentials
        login_resp = await client.post(
            "/api/v1/auth/login",
            json={"username": username, "password": password},
        )
        refresh_token = login_resp.json()["data"]["refresh_token"]

        await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": refresh_token},
        )

        response = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": refresh_token},
        )

        assert response.status_code == 401

    async def test_refresh_with_access_token_returns_401(
        self, client, admin_credentials
    ):
        username, password = admin_credentials
        login_resp = await client.post(
            "/api/v1/auth/login",
            json={"username": username, "password": password},
        )
        access_token = login_resp.json()["data"]["access_token"]

        response = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": access_token},
        )

        assert response.status_code == 401


class TestLogout:

    async def test_logout_invalidates_refresh_token(self, client, admin_credentials):
        username, password = admin_credentials
        login_resp = await client.post(
            "/api/v1/auth/login",
            json={"username": username, "password": password},
        )
        refresh_token = login_resp.json()["data"]["refresh_token"]

        await client.post(
            "/api/v1/auth/logout",
            json={"refresh_token": refresh_token},
        )

        response = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": refresh_token},
        )

        assert response.status_code == 401


class TestHealthcheck:

    async def test_health_returns_service_name(self, client):
        response = await client.get("/api/v1/health")

        assert response.status_code == 200
        data = response.json()["data"]
        assert data["service"] == "gateway"
        assert data["status"] == "healthy"
