import pytest
from httpx import ASGITransport, AsyncClient
from starlette.requests import Request
from unittest.mock import MagicMock

from gateway.app import _build_auth_store
from gateway.config import GatewayConfig
from gateway.models.user import IntegrationKey
from gateway.services.auth_service import AuthService, InMemoryAuthStore
from gateway.services.jwt_service import JwtService
from gateway.services.proxy_service import ProxyService
from gateway.services.rate_limiter import SlidingWindowRateLimiter
from matching.config import MatchingConfig
from matching.services.matching_service import MatchingService
from matching.services.scorer import CandidateScorer
from profile.config import ProfileConfig
from profile.services.llm_parser import LlmParser
from profile.services.file_validator import FileValidator
from profile.services.text_extractor import TextExtractor


@pytest.fixture
def gateway_config():
    return GatewayConfig()


@pytest.fixture
def jwt_service(gateway_config):
    return JwtService(
        gateway_config.JWT_SECRET,
        gateway_config.JWT_ACCESS_TTL,
        gateway_config.JWT_REFRESH_TTL,
    )


@pytest.fixture
def auth_store():
    return InMemoryAuthStore()


class GatewayFakeStore:
    def __init__(self) -> None:
        self.blacklisted: set[str] = set()
        self.saved: list[IntegrationKey] = []

    async def add_to_blacklist(self, jti: str, ttl_seconds: int) -> None:
        self.blacklisted.add(jti)

    async def is_blacklisted(self, jti: str) -> bool:
        return jti in self.blacklisted

    async def save_integration_key(self, key: IntegrationKey) -> None:
        self.saved.append(key)

    async def get_integration_key_by_hash(self, key_hash: str):
        for key in self.saved:
            if key.key_hash == key_hash and key.is_active:
                return key
        return None

    async def list_integration_keys(self):
        return list(self.saved)

    async def delete_integration_key(self, key_id: str) -> bool:
        for key in self.saved:
            if key.key_id == key_id:
                key.is_active = False
                return True
        return False

    async def close(self) -> None:
        return None


class GatewayFakeRedisPipeline:
    def __init__(self, redis_client):
        self._redis = redis_client
        self._ops: list[tuple[str, tuple, dict]] = []

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


class GatewayFakeRedis:
    def __init__(self):
        import time

        self._time = time
        self._values: dict[str, str] = {}
        self._hashes: dict[str, dict[str, str]] = {}
        self._sets: dict[str, set[str]] = {}
        self._expires_at: dict[str, float] = {}

    def _expire_if_needed(self, key: str) -> None:
        expires = self._expires_at.get(key)
        if expires is None:
            return
        if self._time.time() <= expires:
            return

        self._expires_at.pop(key, None)
        self._values.pop(key, None)
        self._hashes.pop(key, None)
        self._sets.pop(key, None)

    def _has_key(self, key: str) -> bool:
        self._expire_if_needed(key)
        return key in self._values or key in self._hashes or key in self._sets

    async def set(self, key: str, value: str, ex: int | None = None):
        self._values[key] = value
        if ex:
            self._expires_at[key] = self._time.time() + ex
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
        self._expires_at[key] = self._time.time() + ttl
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
        return GatewayFakeRedisPipeline(self)

    async def aclose(self):
        return None


@pytest.fixture
def gateway_fake_store():
    return GatewayFakeStore()


@pytest.fixture
def gateway_jwt_service(gateway_config):
    return JwtService(
        gateway_config.JWT_SECRET,
        gateway_config.JWT_ACCESS_TTL,
        gateway_config.JWT_REFRESH_TTL,
    )


@pytest.fixture
def gateway_auth_service(gateway_config, gateway_fake_store, gateway_jwt_service):
    return AuthService(
        config=gateway_config,
        store=gateway_fake_store,
        jwt=gateway_jwt_service,
    )


@pytest.fixture
def gateway_proxy_service(gateway_config):
    return ProxyService(gateway_config)


@pytest.fixture
def gateway_rate_limiter():
    return SlidingWindowRateLimiter(max_requests=2, window_seconds=10)


@pytest.fixture
def gateway_request_factory():
    def factory(
        method: str = "GET",
        path: str = "/",
        headers: list[tuple[bytes, bytes]] | None = None,
        client_host: str = "127.0.0.1",
        body: bytes = b"",
    ) -> Request:
        async def receive():
            return {"type": "http.request", "body": body, "more_body": False}

        scope = {
            "type": "http",
            "method": method,
            "path": path,
            "headers": headers or [],
            "client": (client_host, 12345),
            "query_string": b"",
        }
        return Request(scope, receive)

    return factory


@pytest.fixture
def gateway_auth_store_factory():
    def factory(backend: str):
        cfg = GatewayConfig()
        cfg.AUTH_STORE_BACKEND = backend
        return _build_auth_store(cfg)

    return factory


@pytest.fixture
def gateway_login(client):
    async def login(username: str, password: str) -> str:
        response = await client.post(
            "/api/v1/auth/login",
            json={"username": username, "password": password},
        )
        return response.json()["data"]["access_token"]

    return login


@pytest.fixture
def gateway_login_response(client):
    async def login(username: str, password: str):
        response = await client.post(
            "/api/v1/auth/login",
            json={"username": username, "password": password},
        )
        return response

    return login


@pytest.fixture
def gateway_login_tokens(gateway_login_response):
    async def login(username: str, password: str):
        response = await gateway_login_response(username, password)
        return response.json()["data"]

    return login


@pytest.fixture
def gateway_fake_redis():
    return GatewayFakeRedis()


@pytest.fixture
def matching_service_factory(matching_config):
    def factory(*, scorer=None, client=None, events=None):
        return MatchingService(
            config=matching_config,
            scorer=scorer or MagicMock(),
            client=client or MagicMock(),
            events=events or MagicMock(),
        )

    return factory


@pytest.fixture
def llm_parser():
    return LlmParser("http://fake:11434", "test", max_retries=0)


@pytest.fixture
def admin_credentials(gateway_config):
    return gateway_config.ADMIN_USERNAME, gateway_config.ADMIN_PASSWORD


@pytest.fixture
def hr_credentials(gateway_config):
    return gateway_config.HR_USERNAME, gateway_config.HR_PASSWORD


@pytest.fixture
async def client():
    from gateway.app import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def profile_config():
    return ProfileConfig()


@pytest.fixture
def file_validator(profile_config):
    return FileValidator(
        max_size=profile_config.MAX_FILE_SIZE,
        allowed_extensions=profile_config.ALLOWED_EXTENSIONS,
    )


@pytest.fixture
def text_extractor():
    return TextExtractor()


@pytest.fixture
def matching_config():
    return MatchingConfig()


@pytest.fixture
def scorer():
    return CandidateScorer(embedding_model_name="test-model")


@pytest.fixture
def default_weights():
    return {
        "skills": 0.40,
        "experience": 0.25,
        "grade": 0.15,
        "location": 0.10,
        "salary": 0.10,
    }


@pytest.fixture
def sample_vacancy():
    return {
        "id": "550e8400-e29b-41d4-a716-446655440000",
        "title": "Python Developer",
        "grade": ["middle", "senior"],
        "location": "Москва",
        "salary_min": 150000,
        "salary_max": 250000,
        "requirements": [
            {"skill": "Python", "priority": "required"},
            {"skill": "FastAPI", "priority": "required"},
            {"skill": "PostgreSQL", "priority": "preferred"},
            {"skill": "Docker", "priority": "nice_to_have"},
        ],
    }


@pytest.fixture
def sample_candidate():
    return {
        "id": "660e8400-e29b-41d4-a716-446655440001",
        "profile": {
            "skills": ["Python", "FastAPI", "PostgreSQL", "Redis"],
            "experience_years": 4,
            "grade": "middle",
            "location": "Москва",
            "salary_expectation": 200000,
        },
    }
