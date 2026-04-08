import uuid

import pytest

from common.exceptions import AppError
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

    def test_default_weights(self, matching_config):
        from matching.services.matching_service import MatchingService
        from unittest.mock import MagicMock

        service = MatchingService(
            config=matching_config,
            scorer=MagicMock(),
            client=MagicMock(),
            events=MagicMock(),
        )

        weights = service._resolve_weights(None)

        assert weights["skills"] == 0.40
        assert weights["experience"] == 0.25
        assert abs(sum(weights.values()) - 1.0) < 0.001

    def test_custom_weights(self, matching_config):
        from matching.services.matching_service import MatchingService
        from matching.schemas.match import MatchWeights
        from unittest.mock import MagicMock

        service = MatchingService(
            config=matching_config,
            scorer=MagicMock(),
            client=MagicMock(),
            events=MagicMock(),
        )
        custom = MatchWeights(
            skills=0.50, experience=0.20, grade=0.10,
            location=0.10, salary=0.10,
        )

        weights = service._resolve_weights(custom)

        assert weights["skills"] == 0.50
        assert weights["experience"] == 0.20
