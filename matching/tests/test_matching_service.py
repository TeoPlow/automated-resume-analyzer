import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from common.exceptions import AppError
from matching.schemas.match import MatchRunRequest
from matching.services.matching_service import _parse_uuid, _to_result_data


class TestParseUuid:

    def test_valid_uuid(self):
        result = _parse_uuid("550e8400-e29b-41d4-a716-446655440000")

        assert isinstance(result, uuid.UUID)
        assert str(result) == "550e8400-e29b-41d4-a716-446655440000"

    def test_invalid_uuid_raises(self):
        with pytest.raises(AppError) as exc_info:
            _parse_uuid("not-a-uuid")

        assert exc_info.value.status_code == 400
        assert exc_info.value.code == "invalid_id"


class TestToResultData:

    def test_maps_all_fields(self):
        class FakeExplanation:
            factor = "skills"
            detail = "3/4 совпали"
            score = 75.0
            weight = 0.40
            impact = 30.0

        class FakeResult:
            id = uuid.UUID("550e8400-e29b-41d4-a716-446655440000")
            candidate_id = uuid.UUID("660e8400-e29b-41d4-a716-446655440001")
            vacancy_id = uuid.UUID("770e8400-e29b-41d4-a716-446655440002")
            final_score = 85.5
            skill_score = 75.0
            experience_score = 100.0
            grade_score = 100.0
            location_score = 100.0
            salary_score = 90.0
            rank = 1
            explanations = [FakeExplanation()]

        result = _to_result_data(FakeResult())

        assert result.candidate_id == "660e8400-e29b-41d4-a716-446655440001"
        assert result.final_score == 85.5
        assert result.rank == 1
        assert len(result.explanations) == 1
        assert result.explanations[0].factor == "skills"

    def test_no_explanations(self):
        class FakeResult:
            id = uuid.UUID("550e8400-e29b-41d4-a716-446655440000")
            candidate_id = uuid.UUID("660e8400-e29b-41d4-a716-446655440001")
            vacancy_id = uuid.UUID("770e8400-e29b-41d4-a716-446655440002")
            final_score = 50.0
            skill_score = 50.0
            experience_score = 50.0
            grade_score = 50.0
            location_score = 50.0
            salary_score = 50.0
            rank = 5
            explanations = []

        result = _to_result_data(FakeResult())

        assert result.explanations == []
        assert result.rank == 5


class TestWeightsResolution:

    def test_default_weights(self, matching_service_factory):
        service = matching_service_factory()

        weights = service._resolve_weights(None)

        assert weights["skills"] == 0.40
        assert weights["experience"] == 0.25
        assert abs(sum(weights.values()) - 1.0) < 0.001

    def test_custom_weights(self, matching_service_factory):
        from matching.schemas.match import MatchWeights

        service = matching_service_factory()
        custom = MatchWeights(
            skills=0.50,
            experience=0.20,
            grade=0.10,
            location=0.10,
            salary=0.10,
        )

        weights = service._resolve_weights(custom)

        assert weights["skills"] == 0.50
        assert weights["experience"] == 0.20


@pytest.mark.asyncio
class TestCandidateFetchStrategy:

    async def test_fetch_candidates_with_ids_uses_bulk(self, matching_service_factory):
        client = MagicMock()
        client.get_candidates_bulk = AsyncMock(return_value=[{"id": "c1"}])
        client.get_active_candidates = AsyncMock(return_value=[{"id": "c2"}])

        service = matching_service_factory(client=client)
        body = MatchRunRequest(
            vacancy_id="550e8400-e29b-41d4-a716-446655440000",
            candidate_ids=["660e8400-e29b-41d4-a716-446655440001"],
        )

        result = await service._fetch_candidates(body)

        assert result == [{"id": "c1"}]
        client.get_candidates_bulk.assert_awaited_once_with(
            ["660e8400-e29b-41d4-a716-446655440001"]
        )
        client.get_active_candidates.assert_not_awaited()

    async def test_fetch_candidates_without_ids_uses_active(
        self, matching_service_factory
    ):
        client = MagicMock()
        client.get_candidates_bulk = AsyncMock(return_value=[])
        client.get_active_candidates = AsyncMock(return_value=[{"id": "c-active"}])

        service = matching_service_factory(client=client)
        body = MatchRunRequest(vacancy_id="550e8400-e29b-41d4-a716-446655440000")

        result = await service._fetch_candidates(body)

        assert result == [{"id": "c-active"}]
        client.get_active_candidates.assert_awaited_once()
        client.get_candidates_bulk.assert_not_awaited()


@pytest.mark.asyncio
class TestForceRecomputeBehavior:

    async def test_reuses_latest_run_when_force_false(self, matching_service_factory):
        service = matching_service_factory()

        existing_id = uuid.UUID("550e8400-e29b-41d4-a716-446655440000")
        repo = MagicMock()
        repo.get_latest_completed_run_by_vacancy = AsyncMock(
            return_value=SimpleNamespace(id=existing_id, status="completed")
        )
        repo.create_run = AsyncMock()

        body = MatchRunRequest(vacancy_id=str(existing_id), force_recompute=False)
        result = await service.run(body, repo)

        assert result.run_id == str(existing_id)
        assert result.status == "completed"
        repo.create_run.assert_not_awaited()

    async def test_force_recompute_triggers_new_run(self, matching_service_factory):
        client = MagicMock()
        client.get_vacancy = AsyncMock(
            return_value={
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "requirements": [],
                "grade": [],
                "location": None,
                "salary_min": None,
                "salary_max": None,
            }
        )
        client.get_active_candidates = AsyncMock(return_value=[])
        client.get_candidates_bulk = AsyncMock(return_value=[])

        events = MagicMock()
        service = matching_service_factory(client=client, events=events)

        run_id = uuid.UUID("550e8400-e29b-41d4-a716-446655440000")
        repo = MagicMock()
        repo.get_latest_completed_run_by_vacancy = AsyncMock(
            return_value=SimpleNamespace(id=uuid.uuid4(), status="completed")
        )
        repo.create_run = AsyncMock(
            return_value=SimpleNamespace(id=run_id, status="running")
        )
        repo.commit = AsyncMock()
        repo.complete_run = AsyncMock()
        repo.save_result = AsyncMock()
        repo.save_explanation = AsyncMock()

        body = MatchRunRequest(vacancy_id=str(run_id), force_recompute=True)
        result = await service.run(body, repo)

        assert result.run_id == str(run_id)
        assert result.status == "completed"
        repo.get_latest_completed_run_by_vacancy.assert_not_awaited()
        repo.create_run.assert_awaited_once()
        repo.complete_run.assert_awaited_once()
        events.publish.assert_called_once()


@pytest.mark.asyncio
class TestResultEnrichmentFallback:

    async def test_load_candidate_names_uses_single_fetch_for_missing(
        self, matching_service_factory
    ):
        first_candidate_id = "660e8400-e29b-41d4-a716-446655440001"
        second_candidate_id = "660e8400-e29b-41d4-a716-446655440002"
        vacancy_id = "770e8400-e29b-41d4-a716-446655440010"

        client = MagicMock()
        client.get_candidates_bulk = AsyncMock(
            return_value=[{"id": first_candidate_id, "full_name": "Иван Иванов"}]
        )
        client.get_candidate = AsyncMock(
            return_value={"id": second_candidate_id, "full_name": "Пётр Петров"}
        )

        service = matching_service_factory(client=client)

        results = [
            SimpleNamespace(
                candidate_id=uuid.UUID(first_candidate_id),
                vacancy_id=uuid.UUID(vacancy_id),
            ),
            SimpleNamespace(
                candidate_id=uuid.UUID(second_candidate_id),
                vacancy_id=uuid.UUID(vacancy_id),
            ),
        ]

        names = await service._load_candidate_names(results)

        assert names[first_candidate_id] == "Иван Иванов"
        assert names[second_candidate_id] == "Пётр Петров"
        client.get_candidates_bulk.assert_awaited_once_with(
            sorted([first_candidate_id, second_candidate_id])
        )
        client.get_candidate.assert_awaited_once_with(second_candidate_id)

    async def test_to_result_data_list_uses_fallback_for_missing_titles(
        self, matching_service_factory
    ):
        candidate_id = "660e8400-e29b-41d4-a716-446655440003"
        vacancy_id = "770e8400-e29b-41d4-a716-446655440011"
        result_id = "550e8400-e29b-41d4-a716-446655440111"

        client = MagicMock()
        client.get_candidates_bulk = AsyncMock(return_value=[])
        client.get_candidate = AsyncMock(
            return_value={"id": candidate_id, "full_name": "Мария Сидорова"}
        )
        client.get_vacancies_bulk = AsyncMock(return_value=[])
        client.get_vacancy = AsyncMock(
            return_value={"id": vacancy_id, "title": "Python Developer"}
        )

        service = matching_service_factory(client=client)

        result = SimpleNamespace(
            id=uuid.UUID(result_id),
            candidate_id=uuid.UUID(candidate_id),
            vacancy_id=uuid.UUID(vacancy_id),
            final_score=82.0,
            skill_score=80.0,
            experience_score=90.0,
            grade_score=70.0,
            location_score=100.0,
            salary_score=75.0,
            rank=1,
            explanations=[],
        )

        rows = await service._to_result_data_list([result])

        assert len(rows) == 1
        assert rows[0].candidate_name == "Мария Сидорова"
        assert rows[0].vacancy_title == "Python Developer"
        client.get_candidate.assert_awaited_once_with(candidate_id)
        client.get_vacancy.assert_awaited_once_with(vacancy_id)


@pytest.mark.asyncio
class TestRunSuccessPath:

    async def test_run_saves_top_candidates_and_publishes_event(
        self, matching_service_factory
    ):
        vacancy_id = "550e8400-e29b-41d4-a716-446655440000"
        run_id = uuid.UUID("550e8400-e29b-41d4-a716-446655440999")
        first_candidate_id = "660e8400-e29b-41d4-a716-446655440001"
        second_candidate_id = "660e8400-e29b-41d4-a716-446655440002"

        client = MagicMock()
        client.get_vacancy = AsyncMock(
            return_value={
                "id": vacancy_id,
                "requirements": [],
                "grade": [],
                "location": None,
                "salary_min": None,
                "salary_max": None,
            }
        )
        client.get_active_candidates = AsyncMock(
            return_value=[
                {"id": first_candidate_id, "profile": {}},
                {"id": second_candidate_id, "profile": {}},
            ]
        )
        client.get_candidates_bulk = AsyncMock(return_value=[])

        scorer = MagicMock()
        scorer.score = MagicMock(
            side_effect=[
                (
                    82.0,
                    {"skills": 82.0},
                    [
                        {
                            "factor": "skills",
                            "detail": "first",
                            "score": 82.0,
                            "weight": 0.4,
                            "impact": 32.8,
                        }
                    ],
                ),
                (
                    95.0,
                    {"skills": 95.0},
                    [
                        {
                            "factor": "skills",
                            "detail": "second",
                            "score": 95.0,
                            "weight": 0.4,
                            "impact": 38.0,
                        }
                    ],
                ),
            ]
        )

        events = MagicMock()
        repo = MagicMock()
        repo.get_latest_completed_run_by_vacancy = AsyncMock(return_value=None)
        repo.create_run = AsyncMock(
            return_value=SimpleNamespace(id=run_id, status="running")
        )
        repo.commit = AsyncMock()
        repo.save_result = AsyncMock(
            side_effect=[
                SimpleNamespace(id=uuid.UUID("550e8400-e29b-41d4-a716-446655440010")),
            ]
        )
        repo.save_explanation = AsyncMock()
        repo.complete_run = AsyncMock()

        service = matching_service_factory(
            scorer=scorer, client=client, events=events
        )
        body = MatchRunRequest(
            vacancy_id=vacancy_id,
            candidate_ids=None,
            top_k=1,
            force_recompute=True,
        )

        result = await service.run(body, repo)

        assert result.run_id == str(run_id)
        assert result.status == "completed"
        client.get_active_candidates.assert_awaited_once()
        scorer.score.assert_any_call(
            {"id": second_candidate_id, "profile": {}},
            client.get_vacancy.return_value,
            service._resolve_weights(None),
        )
        repo.save_result.assert_awaited_once()
        assert repo.save_result.await_args.kwargs["candidate_id"] == uuid.UUID(
            second_candidate_id
        )
        repo.save_explanation.assert_awaited_once()
        repo.complete_run.assert_awaited_once_with(
            run_id, status="completed", total_candidates=1
        )
        events.publish.assert_called_once()


@pytest.mark.asyncio
class TestRunFailurePath:

    async def test_run_marks_failed_when_vacancy_load_fails(
        self, matching_service_factory
    ):
        run_id = uuid.UUID("550e8400-e29b-41d4-a716-446655440123")

        client = MagicMock()
        client.get_vacancy = AsyncMock(side_effect=RuntimeError("boom"))
        client.get_active_candidates = AsyncMock(return_value=[])
        client.get_candidates_bulk = AsyncMock(return_value=[])

        repo = MagicMock()
        repo.get_latest_completed_run_by_vacancy = AsyncMock(return_value=None)
        repo.create_run = AsyncMock(
            return_value=SimpleNamespace(id=run_id, status="running")
        )
        repo.commit = AsyncMock()
        repo.complete_run = AsyncMock()

        service = matching_service_factory(client=client)
        body = MatchRunRequest(
            vacancy_id=str(run_id),
            force_recompute=True,
        )

        with pytest.raises(AppError) as exc_info:
            await service.run(body, repo)

        assert exc_info.value.code == "matching_failed"
        repo.complete_run.assert_awaited_once_with(
            run_id, status="failed", total_candidates=0
        )


@pytest.mark.asyncio
class TestServiceRetrieval:

    async def test_get_results_enriches_names_and_titles(self, matching_service_factory):
        run_id = "550e8400-e29b-41d4-a716-446655440222"
        candidate_id = "660e8400-e29b-41d4-a716-446655440222"
        vacancy_id = "770e8400-e29b-41d4-a716-446655440222"

        client = MagicMock()
        client.get_candidates_bulk = AsyncMock(
            return_value=[{"id": candidate_id, "full_name": "Иван Иванов"}]
        )
        client.get_vacancies_bulk = AsyncMock(
            return_value=[{"id": vacancy_id, "title": "Python Developer"}]
        )

        repo = MagicMock()
        repo.get_results_by_run = AsyncMock(
            return_value=[
                SimpleNamespace(
                    id=uuid.UUID("550e8400-e29b-41d4-a716-446655440220"),
                    candidate_id=uuid.UUID(candidate_id),
                    vacancy_id=uuid.UUID(vacancy_id),
                    final_score=91.5,
                    skill_score=90.0,
                    experience_score=100.0,
                    grade_score=85.0,
                    location_score=100.0,
                    salary_score=80.0,
                    rank=1,
                    explanations=[],
                )
            ]
        )

        service = matching_service_factory(client=client)
        results = await service.get_results(run_id, repo)

        assert len(results) == 1
        assert results[0].candidate_name == "Иван Иванов"
        assert results[0].vacancy_title == "Python Developer"
        repo.get_results_by_run.assert_awaited_once_with(uuid.UUID(run_id))

    async def test_get_vacancy_results_uses_latest_results(
        self, matching_service_factory
    ):
        vacancy_id = "550e8400-e29b-41d4-a716-446655440333"
        candidate_id = "660e8400-e29b-41d4-a716-446655440333"

        client = MagicMock()
        client.get_candidates_bulk = AsyncMock(return_value=[])
        client.get_candidate = AsyncMock(
            return_value={"id": candidate_id, "full_name": "Мария Сидорова"}
        )
        client.get_vacancies_bulk = AsyncMock(return_value=[])
        client.get_vacancy = AsyncMock(
            return_value={"id": vacancy_id, "title": "Backend Developer"}
        )

        repo = MagicMock()
        repo.get_latest_results_by_vacancy = AsyncMock(
            return_value=[
                SimpleNamespace(
                    id=uuid.UUID("550e8400-e29b-41d4-a716-446655440330"),
                    candidate_id=uuid.UUID(candidate_id),
                    vacancy_id=uuid.UUID(vacancy_id),
                    final_score=88.0,
                    skill_score=88.0,
                    experience_score=88.0,
                    grade_score=88.0,
                    location_score=88.0,
                    salary_score=88.0,
                    rank=1,
                    explanations=[],
                )
            ]
        )

        service = matching_service_factory(client=client)
        results = await service.get_vacancy_results(vacancy_id, repo)

        assert results[0].candidate_name == "Мария Сидорова"
        assert results[0].vacancy_title == "Backend Developer"
        repo.get_latest_results_by_vacancy.assert_awaited_once_with(
            uuid.UUID(vacancy_id)
        )

    async def test_get_candidate_vacancies_uses_candidate_results(
        self, matching_service_factory
    ):
        candidate_id = "660e8400-e29b-41d4-a716-446655440444"
        vacancy_id = "770e8400-e29b-41d4-a716-446655440444"

        client = MagicMock()
        client.get_candidates_bulk = AsyncMock(return_value=[])
        client.get_candidate = AsyncMock(
            return_value={"id": candidate_id, "full_name": "Пётр Петров"}
        )
        client.get_vacancies_bulk = AsyncMock(return_value=[])
        client.get_vacancy = AsyncMock(
            return_value={"id": vacancy_id, "title": "Data Engineer"}
        )

        repo = MagicMock()
        repo.get_results_by_candidate = AsyncMock(
            return_value=[
                SimpleNamespace(
                    id=uuid.UUID("550e8400-e29b-41d4-a716-446655440440"),
                    candidate_id=uuid.UUID(candidate_id),
                    vacancy_id=uuid.UUID(vacancy_id),
                    final_score=77.0,
                    skill_score=77.0,
                    experience_score=77.0,
                    grade_score=77.0,
                    location_score=77.0,
                    salary_score=77.0,
                    rank=1,
                    explanations=[],
                )
            ]
        )

        service = matching_service_factory(client=client)
        results = await service.get_candidate_vacancies(candidate_id, repo)

        assert results[0].candidate_name == "Пётр Петров"
        assert results[0].vacancy_title == "Data Engineer"
        repo.get_results_by_candidate.assert_awaited_once_with(
            uuid.UUID(candidate_id)
        )

    async def test_to_result_data_list_empty_returns_empty(self, matching_service_factory):
        service = matching_service_factory()

        result = await service._to_result_data_list([])

        assert result == []


@pytest.mark.asyncio
class TestEnrichmentFallbackBranches:

    async def test_load_candidate_names_falls_back_when_bulk_fails(
        self, matching_service_factory
    ):
        candidate_id = "660e8400-e29b-41d4-a716-446655440555"
        vacancy_id = "770e8400-e29b-41d4-a716-446655440555"

        client = MagicMock()
        client.get_candidates_bulk = AsyncMock(side_effect=RuntimeError("boom"))
        client.get_candidate = AsyncMock(
            return_value={"id": candidate_id, "full_name": "Ольга Орлова"}
        )
        service = matching_service_factory(client=client)

        results = [
            SimpleNamespace(
                candidate_id=uuid.UUID(candidate_id),
                vacancy_id=uuid.UUID(vacancy_id),
            )
        ]

        names = await service._load_candidate_names(results)

        assert names[candidate_id] == "Ольга Орлова"

    async def test_load_vacancy_titles_falls_back_when_bulk_fails(
        self, matching_service_factory
    ):
        candidate_id = "660e8400-e29b-41d4-a716-446655440666"
        vacancy_id = "770e8400-e29b-41d4-a716-446655440666"

        client = MagicMock()
        client.get_vacancies_bulk = AsyncMock(side_effect=RuntimeError("boom"))
        client.get_vacancy = AsyncMock(
            return_value={"id": vacancy_id, "title": "QA Engineer"}
        )
        service = matching_service_factory(client=client)

        results = [
            SimpleNamespace(
                candidate_id=uuid.UUID(candidate_id),
                vacancy_id=uuid.UUID(vacancy_id),
            )
        ]

        titles = await service._load_vacancy_titles(results)

        assert titles[vacancy_id] == "QA Engineer"
