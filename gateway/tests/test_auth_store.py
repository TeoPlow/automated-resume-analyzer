import time

import pytest
from redis.exceptions import RedisError

from gateway.models.user import IntegrationKey
from gateway.services.auth_service import (
    FallbackAuthStore,
    InMemoryAuthStore,
    RedisAuthStore,
)


@pytest.mark.asyncio
class TestRedisAuthStore:
    async def test_refresh_blacklist_uses_ttl(self, monkeypatch, gateway_fake_redis):
        now = {"value": 1000.0}

        def fake_time() -> float:
            return now["value"]

        monkeypatch.setattr(time, "time", fake_time)

        monkeypatch.setattr(
            "gateway.services.auth_service.redis.from_url",
            lambda *_args, **_kwargs: gateway_fake_redis,
        )
        store = RedisAuthStore("redis://fake", key_prefix="test")

        await store.add_to_blacklist("jti-1", 1)
        assert await store.is_blacklisted("jti-1") is True

        now["value"] += 1.1
        assert await store.is_blacklisted("jti-1") is False

    async def test_save_list_rotate_revoke_key(self, monkeypatch, gateway_fake_redis):
        monkeypatch.setattr(
            "gateway.services.auth_service.redis.from_url",
            lambda *_args, **_kwargs: gateway_fake_redis,
        )
        store = RedisAuthStore("redis://fake", key_prefix="test")

        key = IntegrationKey(
            key_id="k1",
            name="bot",
            key_hash="hash-1",
            permissions=["resumes:upload"],
            created_at="2026-04-22T10:00:00+00:00",
        )
        await store.save_integration_key(key)

        loaded = await store.get_integration_key_by_hash("hash-1")
        assert loaded is not None
        assert loaded.key_id == "k1"
        assert loaded.is_active is True

        keys = await store.list_integration_keys()
        assert len(keys) == 1
        assert keys[0].key_id == "k1"

        deleted = await store.delete_integration_key("k1")
        assert deleted is True
        assert await store.get_integration_key_by_hash("hash-1") is None

        keys_after_revoke = await store.list_integration_keys()
        assert len(keys_after_revoke) == 1
        assert keys_after_revoke[0].is_active is False


class BrokenRedisStore:
    async def add_to_blacklist(self, _jti: str, _ttl_seconds: int) -> None:
        raise RedisError("redis down")

    async def is_blacklisted(self, _jti: str) -> bool:
        raise RedisError("redis down")

    async def save_integration_key(self, _key: IntegrationKey) -> None:
        raise RedisError("redis down")

    async def get_integration_key_by_hash(self, _key_hash: str):
        raise RedisError("redis down")

    async def list_integration_keys(self):
        raise RedisError("redis down")

    async def delete_integration_key(self, _key_id: str):
        raise RedisError("redis down")

    async def close(self) -> None:
        return None


@pytest.mark.asyncio
class TestFallbackAuthStore:
    async def test_switches_to_inmemory_when_redis_unavailable(self):
        fallback = InMemoryAuthStore()
        store = FallbackAuthStore(
            primary=BrokenRedisStore(),
            fallback=fallback,
        )

        await store.add_to_blacklist("jti-2", 60)
        assert store._fallback_mode is True
        assert await store.is_blacklisted("jti-2") is True
