import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from profile.schemas.resume import ParsedContacts, ParsedData
from profile.services.resume_processor import ResumeProcessor


def _make_processor(
    storage=None, text_extractor=None, llm_parser=None, event_publisher=None
):
    return ResumeProcessor(
        storage=storage or MagicMock(),
        text_extractor=text_extractor or MagicMock(),
        llm_parser=llm_parser or MagicMock(),
        event_publisher=event_publisher or MagicMock(),
    )


@pytest.mark.asyncio
async def test_process_success_aggregates_profile_and_publishes_event():
    candidate_id = uuid.UUID("550e8400-e29b-41d4-a716-446655440001")
    resume_id = uuid.UUID("550e8400-e29b-41d4-a716-446655440010")

    storage = MagicMock()
    storage.download = MagicMock(return_value=b"resume-bytes")

    text_extractor = MagicMock()
    text_extractor.extract = MagicMock(return_value="raw resume text")

    llm_parser = MagicMock()
    llm_parser.parse = AsyncMock(
        return_value=ParsedData(
            full_name="Иван Иванов",
            contacts=ParsedContacts(email="ivan@example.com"),
            location="Москва",
            summary="Senior developer",
            skills=["Python", "FastAPI"],
            total_experience_years=4.0,
            desired_salary=250000,
            desired_position="Python Developer",
        )
    )

    event_publisher = MagicMock()

    repo = MagicMock()
    repo.update_resume_status = AsyncMock()
    repo.commit = AsyncMock()
    repo.get_candidate_by_email = AsyncMock(
        return_value=SimpleNamespace(id=candidate_id)
    )
    repo.get_candidate_by_phone = AsyncMock(return_value=None)
    repo.create_candidate = AsyncMock()
    repo.get_parsed_resumes = AsyncMock(
        return_value=[
            SimpleNamespace(
                parsed_data={
                    "skills": ["Python", "FastAPI"],
                    "experience": [
                        {
                            "company": "Acme",
                            "position": "Dev",
                            "start_date": "2020-01",
                        }
                    ],
                    "education": [{"institution": "MSU", "degree": "Bachelor"}],
                    "languages": [{"language": "English", "level": "B2"}],
                    "total_experience_years": 3.0,
                    "location": "Москва",
                    "desired_salary": 250000,
                    "desired_position": "Python Developer",
                    "summary": "first",
                    "grade": "middle",
                }
            ),
            SimpleNamespace(
                parsed_data={
                    "skills": ["FastAPI", "Docker"],
                    "experience": [
                        {
                            "company": "Acme",
                            "position": "Dev",
                            "start_date": "2020-01",
                        },
                        {
                            "company": "Beta",
                            "position": "Lead",
                            "start_date": "2022-01",
                        },
                    ],
                    "education": [
                        {"institution": "MSU", "degree": "Bachelor"},
                        {"institution": "MIT", "degree": "Master"},
                    ],
                    "languages": [{"language": "Russian", "level": "C2"}],
                    "total_experience_years": 4.0,
                    "location": "Казань",
                    "desired_salary": 300000,
                    "desired_position": "Backend Developer",
                    "summary": "latest",
                }
            ),
        ]
    )
    repo.upsert_candidate_profile = AsyncMock(
        return_value=SimpleNamespace(id=candidate_id)
    )

    processor = _make_processor(storage, text_extractor, llm_parser, event_publisher)

    await processor.process(resume_id, "resume.pdf", repo)

    assert repo.update_resume_status.await_count == 3
    repo.get_candidate_by_email.assert_awaited_once_with("ivan@example.com")
    repo.create_candidate.assert_not_awaited()
    repo.upsert_candidate_profile.assert_awaited_once()
    event_publisher.publish.assert_called_once()
    payload = event_publisher.publish.call_args.kwargs["payload"]
    assert payload["candidate_id"] == str(candidate_id)
    assert sorted(payload["skills"]) == ["docker", "fastapi", "python"]


@pytest.mark.asyncio
async def test_deduplicate_uses_phone_and_creates_when_missing():
    processor = _make_processor()

    repo = MagicMock()
    repo.get_candidate_by_email = AsyncMock(return_value=None)
    repo.get_candidate_by_phone = AsyncMock(
        return_value=SimpleNamespace(id=uuid.uuid4())
    )
    repo.create_candidate = AsyncMock(return_value=SimpleNamespace(id=uuid.uuid4()))

    parsed_by_phone = ParsedData(contacts=ParsedContacts(phone="+79991234567"))
    candidate = await processor._deduplicate(parsed_by_phone, repo)
    assert candidate == repo.get_candidate_by_phone.return_value.id

    repo.get_candidate_by_phone = AsyncMock(return_value=None)
    parsed_empty = ParsedData(contacts=ParsedContacts())
    candidate = await processor._deduplicate(parsed_empty, repo)
    assert candidate == repo.create_candidate.return_value.id
    repo.create_candidate.assert_awaited_once()


@pytest.mark.asyncio
async def test_aggregate_profile_without_resumes_returns_early():
    processor = _make_processor()

    repo = MagicMock()
    repo.get_parsed_resumes = AsyncMock(return_value=[])
    repo.upsert_candidate_profile = AsyncMock()

    await processor._aggregate_profile(uuid.uuid4(), repo)

    repo.upsert_candidate_profile.assert_not_awaited()


@pytest.mark.asyncio
async def test_process_failure_marks_resume_failed():
    resume_id = uuid.uuid4()

    storage = MagicMock()
    storage.download = MagicMock(side_effect=RuntimeError("boom"))
    processor = _make_processor(storage=storage)

    repo = MagicMock()
    repo.update_resume_status = AsyncMock()
    repo.commit = AsyncMock()

    await processor.process(resume_id, "resume.pdf", repo)

    repo.update_resume_status.assert_any_await(
        resume_id, status="failed", error_detail="boom"
    )
    assert repo.commit.await_count == 2
