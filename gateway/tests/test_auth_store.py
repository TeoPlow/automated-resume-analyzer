import time
from typing import Any

import pytest
from redis.exceptions import RedisError

from gateway.models.user import IntegrationKey
from gateway.services.auth_service import (
    FallbackAuthStore,
    InMemoryAuthStore,
    RedisAuthStore,
)


class FakeRedisPipeline:
    def __init__(self, redis_client):
        self._redis = redis_client
        self._ops: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def hset(self, *args, **kwargs):
        self._ops.append(("hset", args, kwargs))
        return self

    def expire(self, *args, **kwargs):
        self._ops.append(("expire", args, kwargs))
        return self

    def set(self, *args, **kwargs):
        self._ops.append(("set", args, kwargs))
        return self

    def sadd(self, *args, **kwargs):
        self._ops.append(("sadd", args, kwargs))
        return self

    def hgetall(self, *args, **kwargs):
        self._ops.append(("hgetall", args, kwargs))
        return self

    def delete(self, *args, **kwargs):
        self._ops.append(("delete", args, kwargs))
        return self

    def srem(self, *args, **kwargs):
        self._ops.append(("srem", args, kwargs))
        return self

    async def execute(self):
        results = []
        for op_name, args, kwargs in self._ops:
            method = getattr(self._redis, op_name)
            results.append(await method(*args, **kwargs))
        self._ops.clear()
        return results


class FakeRedis:
    def __init__(self):
        self._values: dict[str, str] = {}
        self._hashes: dict[str, dict[str, str]] = {}
        self._sets: dict[str, set[str]] = {}
        self._expires_at: dict[str, float] = {}

    def _expire_if_needed(self, key: str) -> None:
        expires = self._expires_at.get(key)
        if expires is None:
            return
        if time.time() <= expires:
            return

        self._expires_at.pop(key, None)
        self._values.pop(key, None)
        self._hashes.pop(key, None)
        self._sets.pop(key, None)

    def _has_key(self, key: str) -> bool:
        self._expire_if_needed(key)
        return (
            key in self._values
            or key in self._hashes
            or key in self._sets
        )

    async def set(self, key: str, value: str, ex: int | None = None):
        self._values[key] = value
        if ex:
            self._expires_at[key] = time.time() + ex
        return True

    async def get(self, key: str):
        self._expire_if_needed(key)
        return self._values.get(key)

    async def exists(self, key: str):
        return 1 if self._has_key(key) else 0

    async def hset(self, key: str, mapping: dict[str, str]):
        self._expire_if_needed(key)
        entry = self._hashes.setdefault(key, {})
        entry.update(mapping)
        return len(mapping)

    async def hgetall(self, key: str):
        self._expire_if_needed(key)
        return dict(self._hashes.get(key, {}))

    async def delete(self, key: str):
        self._expire_if_needed(key)
        existed = 1 if self._has_key(key) else 0
        self._values.pop(key, None)
        self._hashes.pop(key, None)
        self._sets.pop(key, None)
        self._expires_at.pop(key, None)
        return existed

    async def expire(self, key: str, ttl: int):
        if not self._has_key(key):
            return False
        self._expires_at[key] = time.time() + ttl
        return True

    async def sadd(self, key: str, *members: str):
        self._expire_if_needed(key)
        bucket = self._sets.setdefault(key, set())
        before = len(bucket)
        bucket.update(members)
        return len(bucket) - before

    async def smembers(self, key: str):
        self._expire_if_needed(key)
        return set(self._sets.get(key, set()))

    async def srem(self, key: str, *members: str):
        self._expire_if_needed(key)
        bucket = self._sets.get(key)
        if not bucket:
            return 0
        removed = 0
        for member in members:
            if member in bucket:
                bucket.remove(member)
                removed += 1
        return removed

    def pipeline(self, transaction: bool = True):
        return FakeRedisPipeline(self)

    async def aclose(self):
        return None


@pytest.mark.asyncio
class TestRedisAuthStore:
    async def test_refresh_blacklist_uses_ttl(self, monkeypatch):
        now = {"value": 1000.0}

        def fake_time() -> float:
            return now["value"]

        monkeypatch.setattr("gateway.tests.test_auth_store.time.time", fake_time)

        fake = FakeRedis()
        monkeypatch.setattr(
            "gateway.services.auth_service.redis.from_url",
            lambda *_args, **_kwargs: fake,
        )
        store = RedisAuthStore("redis://fake", key_prefix="test")

        await store.add_to_blacklist("jti-1", 1)
        assert await store.is_blacklisted("jti-1") is True

        now["value"] += 1.1
        assert await store.is_blacklisted("jti-1") is False

    async def test_save_list_rotate_revoke_key(self, monkeypatch):
        fake = FakeRedis()
        monkeypatch.setattr(
            "gateway.services.auth_service.redis.from_url",
            lambda *_args, **_kwargs: fake,
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
