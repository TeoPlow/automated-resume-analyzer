import asyncio
import importlib
import sys
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from starlette.requests import Request

from common.auth import Actor
from common.exceptions import AppError
from profile.config import ProfileConfig
from profile.schemas.candidate import CandidateBulkRequest


def _make_request(headers=None):
    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": headers or [],
        "query_string": b"",
        "client": ("127.0.0.1", 12345),
    }
    return Request(scope, receive)


@pytest.fixture(autouse=True)
def _disable_multipart_requirement(monkeypatch):
    monkeypatch.setattr(
        "fastapi.dependencies.utils.ensure_multipart_is_installed",
        lambda: None,
        raising=False,
    )
    monkeypatch.setattr(
        "fastapi.routing.ensure_multipart_is_installed",
        lambda: None,
        raising=False,
    )


class FakeRepo:

    def __init__(self):
        self.get_candidate = AsyncMock()
        self.update_candidate = AsyncMock()
        self.get_candidate_resumes = AsyncMock()
        self.delete_candidate = AsyncMock()
        self.commit = AsyncMock()
        self.get_active_candidates = AsyncMock()
        self.get_candidates_bulk = AsyncMock()
        self.create_resume = AsyncMock()
        self.get_resume = AsyncMock()


class FakeSessionContext:

    async def __aenter__(self):
        return object()

    async def __aexit__(self, exc_type, exc, tb):
        return False


class FakeDb:

    def __init__(self, repo):
        self.repo = repo

    def session(self):
        return FakeSessionContext()


class FakeUploadFile:

    def __init__(self, filename: str, content: bytes):
        self.filename = filename
        self._content = content

    async def read(self):
        return self._content


def _candidate(fake_id=None, with_profile=True):
    now = datetime.now(timezone.utc)
    candidate_id = fake_id or uuid.uuid4()
    profile = None
    if with_profile:
        profile = SimpleNamespace(
            skills=["python"],
            grade="middle",
            location="Москва",
            experience_years=3.0,
            salary_expectation=200000,
            data={"skills": ["python"]},
        )
    return SimpleNamespace(
        id=candidate_id,
        full_name="Иван Иванов",
        email="ivan@example.com",
        phone="+79990000000",
        created_at=now,
        updated_at=now,
        profile=profile,
    )


def _resume(fake_id=None, parsed=True):
    now = datetime.now(timezone.utc)
    resume_id = fake_id or uuid.uuid4()
    parsed_data = None
    if parsed:
        parsed_data = {
            "skills": ["Python"],
            "total_experience_years": 3.0,
            "location": "Москва",
        }
    return SimpleNamespace(
        id=resume_id,
        candidate_id=None,
        file_key="file.pdf",
        source="upload",
        external_id=None,
        status="parsed",
        parsed_data=parsed_data,
        error_detail=None,
        created_at=now,
    )


def _find_route(router, path, method):
    for route in router.routes:
        if getattr(route, "path", None) == path and method in getattr(
            route, "methods", set()
        ):
            return route.endpoint
    raise AssertionError(f"route not found: {method} {path}")


@pytest.mark.asyncio
async def test_candidates_router_success_and_not_found(monkeypatch):
    from profile.routers import candidates as module

    repo = FakeRepo()
    repo.get_candidate.return_value = _candidate()
    repo.update_candidate.return_value = _candidate()
    repo.get_candidate_resumes.return_value = [_resume()]
    repo.delete_candidate.return_value = True

    monkeypatch.setattr(module, "ProfileRepository", lambda session: repo)
    router = module.create_router(FakeDb(repo))

    actor = Actor(
        actor_id="1",
        actor_type="hr",
        permissions=["candidates:read", "candidates:write", "integrations:manage"],
    )

    get_candidate = _find_route(router, "/candidates/{candidate_id}", "GET")
    result = await get_candidate(candidate_id=str(uuid.uuid4()), actor=actor)
    assert result.data.full_name == "Иван Иванов"

    update_candidate = _find_route(router, "/candidates/{candidate_id}", "PATCH")
    updated = await update_candidate(
        candidate_id=str(uuid.uuid4()),
        body=module.CandidateUpdateRequest(full_name="Пётр Петров"),
        actor=actor,
    )
    assert updated.data.full_name == "Иван Иванов"

    get_resumes = _find_route(router, "/candidates/{candidate_id}/resumes", "GET")
    resumes = await get_resumes(candidate_id=str(uuid.uuid4()), actor=actor)
    assert len(resumes.data) == 1

    delete_candidate = _find_route(router, "/candidates/{candidate_id}", "DELETE")
    deleted = await delete_candidate(candidate_id=str(uuid.uuid4()), actor=actor)
    assert deleted is None


@pytest.mark.asyncio
async def test_candidates_router_not_found_and_forbidden(monkeypatch):
    from profile.routers import candidates as module

    repo = FakeRepo()
    repo.get_candidate.return_value = None
    repo.update_candidate.return_value = None
    repo.get_candidate_resumes.return_value = []
    repo.delete_candidate.return_value = False

    monkeypatch.setattr(module, "ProfileRepository", lambda session: repo)
    router = module.create_router(FakeDb(repo))

    actor = Actor(
        actor_id="1",
        actor_type="hr",
        permissions=["candidates:read", "candidates:write"],
    )

    get_candidate = _find_route(router, "/candidates/{candidate_id}", "GET")
    with pytest.raises(AppError):
        await get_candidate(candidate_id=str(uuid.uuid4()), actor=actor)

    delete_candidate = _find_route(router, "/candidates/{candidate_id}", "DELETE")
    with pytest.raises(AppError):
        await delete_candidate(candidate_id=str(uuid.uuid4()), actor=actor)


@pytest.mark.asyncio
async def test_internal_router_success_and_not_found(monkeypatch):
    from profile.routers import internal as module

    repo = FakeRepo()
    repo.get_active_candidates.return_value = [_candidate()]
    repo.get_candidate.return_value = _candidate()
    repo.get_candidates_bulk.return_value = [_candidate()]

    monkeypatch.setattr(module, "ProfileRepository", lambda session: repo)
    config = ProfileConfig()
    router = module.create_router(config, FakeDb(repo))

    request = _make_request([(b"x-internal-token", config.INTERNAL_TOKEN.encode())])

    get_active = _find_route(router, "/internal/v1/candidates/active", "GET")
    active = await get_active(request=request)
    assert active.data[0].full_name == "Иван Иванов"

    get_candidate = _find_route(
        router, "/internal/v1/candidates/{candidate_id:uuid}", "GET"
    )
    candidate = await get_candidate(candidate_id=uuid.uuid4(), request=request)
    assert candidate.data.full_name == "Иван Иванов"

    bulk_get = _find_route(router, "/internal/v1/candidates/bulk-get", "POST")
    bulk = await bulk_get(
        body=CandidateBulkRequest(candidate_ids=[str(uuid.uuid4())]), request=request
    )
    assert len(bulk.data) == 1


@pytest.mark.asyncio
async def test_internal_router_unauthorized_and_not_found(monkeypatch):
    from profile.routers import internal as module

    repo = FakeRepo()
    repo.get_active_candidates.return_value = []
    repo.get_candidate.return_value = None
    repo.get_candidates_bulk.return_value = []

    monkeypatch.setattr(module, "ProfileRepository", lambda session: repo)
    config = ProfileConfig()
    router = module.create_router(config, FakeDb(repo))

    request = _make_request([])
    get_active = _find_route(router, "/internal/v1/candidates/active", "GET")
    with pytest.raises(AppError):
        await get_active(request=request)

    request = _make_request([(b"x-internal-token", config.INTERNAL_TOKEN.encode())])
    get_candidate = _find_route(
        router, "/internal/v1/candidates/{candidate_id:uuid}", "GET"
    )
    with pytest.raises(AppError):
        await get_candidate(candidate_id=uuid.uuid4(), request=request)


@pytest.mark.asyncio
async def test_resumes_router_upload_and_status(monkeypatch):
    from profile.routers import resumes as module

    repo = FakeRepo()
    resume_id = uuid.uuid4()
    repo.create_resume.return_value = SimpleNamespace(id=resume_id)
    repo.get_resume.return_value = _resume(resume_id)

    file_validator = MagicMock()
    file_validator.validate.return_value = "pdf"
    file_storage = MagicMock()
    file_storage.upload.return_value = "stored.pdf"
    event_publisher = MagicMock()
    resume_processor = MagicMock()
    resume_processor.process = AsyncMock()

    monkeypatch.setattr(module, "ProfileRepository", lambda session: repo)
    captured_tasks = []

    def fake_create_task(coro):
        captured_tasks.append(coro)
        return SimpleNamespace(cancel=lambda: None)

    monkeypatch.setattr(module.asyncio, "create_task", fake_create_task)

    router = module.create_router(
        config=ProfileConfig(),
        db=FakeDb(repo),
        file_validator=file_validator,
        file_storage=file_storage,
        event_publisher=event_publisher,
        resume_processor=resume_processor,
    )

    actor = Actor(actor_id="1", actor_type="hr", permissions=["resumes:upload"])
    upload_resume = _find_route(router, "/resumes/upload", "POST")
    result = await upload_resume(
        file=FakeUploadFile("resume.pdf", b"%PDF-1.4"),
        source="upload",
        external_id="ext-1",
        actor=actor,
    )
    assert result.data.status == "uploaded"
    assert captured_tasks
    await captured_tasks[0]
    resume_processor.process.assert_awaited_once()

    get_resume_status = _find_route(router, "/resumes/{resume_id}", "GET")
    status = await get_resume_status(resume_id=str(resume_id), actor=actor)
    assert status.data.status == "parsed"


@pytest.mark.asyncio
async def test_resumes_router_invalid_id_and_not_found(monkeypatch):
    from profile.routers import resumes as module

    repo = FakeRepo()
    repo.get_resume.return_value = None
    monkeypatch.setattr(module, "ProfileRepository", lambda session: repo)

    router = module.create_router(
        config=ProfileConfig(),
        db=FakeDb(repo),
        file_validator=MagicMock(),
        file_storage=MagicMock(),
        event_publisher=MagicMock(),
        resume_processor=MagicMock(),
    )

    actor = Actor(actor_id="1", actor_type="hr", permissions=["resumes:upload"])
    get_resume_status = _find_route(router, "/resumes/{resume_id}", "GET")

    with pytest.raises(AppError):
        await get_resume_status(resume_id="not-a-uuid", actor=actor)

    with pytest.raises(AppError):
        await get_resume_status(resume_id=str(uuid.uuid4()), actor=actor)


def test_profile_app_import_and_lifespan(monkeypatch):
    class FakeParams:

        def __init__(self, url):
            self.url = url
            self.heartbeat = None
            self.blocked_connection_timeout = None

    class FakeChannel:

        def __init__(self):
            self.is_open = True

        def exchange_declare(self, **kwargs):
            return None

        def basic_publish(self, **kwargs):
            return None

    class FakeConnection:

        def __init__(self, params):
            self.params = params
            self.is_open = True
            self._channel = FakeChannel()

        def channel(self):
            return self._channel

        def close(self):
            self.is_open = False

    class FakeS3Client:

        def head_bucket(self, Bucket):
            return None

    class FakeDatabase:

        def __init__(self, url, echo=False):
            self.url = url
            self.echo = echo
            self.created = False
            self.disposed = False

        async def create_tables(self):
            self.created = True

        def session(self):
            return FakeSessionContext()

        async def dispose(self):
            self.disposed = True

    monkeypatch.setattr("common.database.Database", FakeDatabase)
    monkeypatch.setattr(
        "profile.services.storage.boto3.client", lambda *args, **kwargs: FakeS3Client()
    )
    monkeypatch.setattr("profile.services.event_publisher.URLParameters", FakeParams)
    monkeypatch.setattr(
        "profile.services.event_publisher.BlockingConnection", FakeConnection
    )

    sys.modules.pop("profile.app", None)
    app_module = importlib.import_module("profile.app")

    async def run_lifespan():
        async with app_module.lifespan(app_module.app):
            assert app_module.app.title == "Profile — Resume Analyzer"
            assert any(
                route.path.startswith("/api/v1/profiles")
                for route in app_module.app.routes
            )

    asyncio.run(run_lifespan())

    assert app_module.db.created is True
    assert app_module.db.disposed is True
