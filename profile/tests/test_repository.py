import uuid
from types import SimpleNamespace

import pytest

from profile.models.candidate import CandidateProfile
from profile.repository import ProfileRepository


class FakeScalarResult:

    def __init__(self, single=None, items=None):
        self._single = single
        self._items = items or []

    def scalar_one_or_none(self):
        return self._single

    def scalars(self):
        return self

    def all(self):
        return self._items


class FakeSession:

    def __init__(self):
        self.added = []
        self.deleted = []
        self.executed = []
        self.get_results = []
        self.execute_results = []
        self.flushed = 0
        self.committed = 0

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        self.flushed += 1

    async def get(self, model, key):
        if self.get_results:
            return self.get_results.pop(0)
        return None

    async def execute(self, stmt):
        self.executed.append(stmt)
        if self.execute_results:
            return self.execute_results.pop(0)
        return FakeScalarResult()

    async def delete(self, obj):
        self.deleted.append(obj)

    async def commit(self):
        self.committed += 1


@pytest.fixture
def repo_session():
    return FakeSession()


@pytest.fixture
def repo(repo_session):
    return ProfileRepository(repo_session)


@pytest.mark.asyncio
class TestProfileRepository:

    async def test_create_resume(self, repo, repo_session):
        resume = await repo.create_resume("file.pdf", "upload", "ext-1")

        assert resume.file_key == "file.pdf"
        assert resume.status == "uploaded"
        assert repo_session.added[0] is resume
        assert repo_session.flushed == 1

    async def test_get_resume(self, repo, repo_session):
        expected = SimpleNamespace(id=uuid.uuid4())
        repo_session.get_results.append(expected)

        result = await repo.get_resume(uuid.uuid4())

        assert result is expected

    async def test_update_resume_status_all_fields(self, repo, repo_session):
        resume_id = uuid.uuid4()

        await repo.update_resume_status(
            resume_id,
            status="parsed",
            raw_text="text",
            parsed_data={"skills": ["Python"]},
            error_detail="",
            candidate_id=uuid.uuid4(),
        )

        assert repo_session.executed

    async def test_get_candidate_by_email_and_phone(self, repo, repo_session):
        email_candidate = SimpleNamespace(id=uuid.uuid4())
        phone_candidate = SimpleNamespace(id=uuid.uuid4())
        repo_session.execute_results.extend(
            [
                FakeScalarResult(single=email_candidate),
                FakeScalarResult(single=phone_candidate),
            ]
        )

        assert await repo.get_candidate_by_email("test@example.com") is email_candidate
        assert await repo.get_candidate_by_phone("+7999") is phone_candidate

    async def test_create_candidate(self, repo, repo_session):
        candidate = await repo.create_candidate("Иван Иванов", "a@b.com", "+7")

        assert candidate.full_name == "Иван Иванов"
        assert repo_session.added[0] is candidate
        assert repo_session.flushed == 1

    async def test_update_candidate_without_fields_returns_existing(
        self, repo, repo_session
    ):
        existing = SimpleNamespace(id=uuid.uuid4())
        repo_session.get_results.append(existing)

        result = await repo.update_candidate(uuid.uuid4())

        assert result is existing

    async def test_update_candidate_with_fields_executes_and_returns_candidate(
        self, repo, repo_session
    ):
        updated = SimpleNamespace(id=uuid.uuid4())
        repo_session.get_results.append(updated)

        result = await repo.update_candidate(
            uuid.uuid4(),
            full_name="Пётр Петров",
            email="p@example.com",
            phone="+7000",
        )

        assert result is updated
        assert repo_session.executed

    async def test_get_candidate_resumes_and_parsed_resumes(self, repo, repo_session):
        resume_1 = SimpleNamespace(id=uuid.uuid4())
        resume_2 = SimpleNamespace(id=uuid.uuid4())
        repo_session.execute_results.extend(
            [FakeScalarResult(items=[resume_1]), FakeScalarResult(items=[resume_2])]
        )

        assert await repo.get_candidate_resumes(uuid.uuid4()) == [resume_1]
        assert await repo.get_parsed_resumes(uuid.uuid4()) == [resume_2]

    async def test_get_candidate_profile_and_upsert_create(self, repo, repo_session):
        repo_session.execute_results.append(FakeScalarResult(single=None))

        profile = await repo.upsert_candidate_profile(
            candidate_id=uuid.uuid4(),
            data={"skills": ["Python"]},
            skills=["Python"],
            grade="middle",
            location="Москва",
            experience_years=3.0,
            salary_expectation=200000,
        )

        assert profile in repo_session.added
        assert repo_session.flushed == 1

    async def test_upsert_candidate_profile_update_branch(self, repo, repo_session):
        profile = CandidateProfile(
            candidate_id=uuid.uuid4(),
            data={},
            skills=[],
            grade=None,
            location=None,
            experience_years=None,
            salary_expectation=None,
        )
        repo_session.execute_results.append(FakeScalarResult(single=profile))

        updated = await repo.upsert_candidate_profile(
            candidate_id=profile.candidate_id,
            data={"skills": ["Python"]},
            skills=["Python"],
            grade="senior",
            location="Казань",
            experience_years=7.0,
            salary_expectation=300000,
        )

        assert updated.grade == "senior"
        assert repo_session.flushed == 1

    async def test_bulk_and_active_queries(self, repo, repo_session):
        candidate = SimpleNamespace(id=uuid.uuid4())
        repo_session.execute_results.extend(
            [
                FakeScalarResult(items=[candidate]),
                FakeScalarResult(items=[candidate]),
            ]
        )

        assert await repo.get_candidates_bulk([uuid.uuid4()]) == [candidate]
        assert await repo.get_active_candidates() == [candidate]

    async def test_delete_candidate_false_then_true(self, repo, repo_session):
        repo_session.get_results.extend([None, SimpleNamespace(id=uuid.uuid4())])

        assert await repo.delete_candidate(uuid.uuid4()) is False
        assert await repo.delete_candidate(uuid.uuid4()) is True
        assert repo_session.deleted

    async def test_commit(self, repo, repo_session):
        await repo.commit()

        assert repo_session.committed == 1
