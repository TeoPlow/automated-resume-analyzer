import pytest

from common.exceptions import AppError
from vacancy.services.vacancy_service import (
    _validate_status_transition,
)


class TestStatusTransitions:

    def test_draft_to_open_allowed(self):
        _validate_status_transition("draft", "open")

    def test_open_to_closed_allowed(self):
        _validate_status_transition("open", "closed")

    def test_closed_to_archived_allowed(self):
        _validate_status_transition("closed", "archived")

    def test_draft_to_closed_forbidden(self):
        with pytest.raises(AppError) as exc_info:
            _validate_status_transition("draft", "closed")

        assert exc_info.value.status_code == 400
        assert exc_info.value.code == "invalid_transition"

    def test_open_to_draft_forbidden(self):
        with pytest.raises(AppError) as exc_info:
            _validate_status_transition("open", "draft")

        assert exc_info.value.status_code == 400

    def test_archived_to_any_forbidden(self):
        with pytest.raises(AppError) as exc_info:
            _validate_status_transition("archived", "open")

        assert exc_info.value.status_code == 400

    def test_invalid_target_status(self):
        with pytest.raises(AppError) as exc_info:
            _validate_status_transition("draft", "deleted")

        assert exc_info.value.code == "invalid_status"

    def test_closed_to_open_forbidden(self):
        with pytest.raises(AppError) as exc_info:
            _validate_status_transition("closed", "open")

        assert exc_info.value.status_code == 400


class TestParseUuid:

    def test_valid_uuid_parsed(self):
        from vacancy.services.vacancy_service import _parse_uuid

        result = _parse_uuid("550e8400-e29b-41d4-a716-446655440000")

        assert str(result) == "550e8400-e29b-41d4-a716-446655440000"

    def test_invalid_uuid_raises_400(self):
        from vacancy.services.vacancy_service import _parse_uuid

        with pytest.raises(AppError) as exc_info:
            _parse_uuid("not-a-uuid")

        assert exc_info.value.status_code == 400
        assert exc_info.value.code == "invalid_id"


class TestVacancyDataMapping:

    def test_to_vacancy_data_maps_fields(self):
        from datetime import datetime, timezone
        from unittest.mock import MagicMock

        from vacancy.services.vacancy_service import _to_vacancy_data

        vacancy = MagicMock()
        vacancy.id = "550e8400-e29b-41d4-a716-446655440000"
        vacancy.title = "Backend Developer"
        vacancy.description = "Develop APIs"
        vacancy.department = "Engineering"
        vacancy.location = "Moscow"
        vacancy.grade = ["middle", "senior"]
        vacancy.salary_min = 150000
        vacancy.salary_max = 250000
        vacancy.status = "open"
        vacancy.created_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
        vacancy.updated_at = datetime(2026, 1, 2, tzinfo=timezone.utc)
        vacancy.requirements = []

        result = _to_vacancy_data(vacancy)

        assert result.title == "Backend Developer"
        assert result.location == "Moscow"
        assert result.grade == ["middle", "senior"]
        assert result.status == "open"
        assert result.salary_min == 150000

    def test_to_vacancy_data_maps_requirements(self):
        from datetime import datetime, timezone
        from unittest.mock import MagicMock

        from vacancy.services.vacancy_service import _to_vacancy_data

        req = MagicMock()
        req.id = "req-uuid"
        req.skill = "python"
        req.category = "hard"
        req.priority = "required"
        req.min_experience_years = 3.0

        vacancy = MagicMock()
        vacancy.id = "vac-uuid"
        vacancy.title = "Dev"
        vacancy.description = "Desc"
        vacancy.department = None
        vacancy.location = "Remote"
        vacancy.grade = ["junior"]
        vacancy.salary_min = None
        vacancy.salary_max = None
        vacancy.status = "draft"
        vacancy.created_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
        vacancy.updated_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
        vacancy.requirements = [req]

        result = _to_vacancy_data(vacancy)

        assert len(result.requirements) == 1
        assert result.requirements[0].skill == "python"
        assert result.requirements[0].priority == "required"
        assert result.requirements[0].min_experience_years == 3.0
