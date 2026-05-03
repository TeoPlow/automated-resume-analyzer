import uuid

from search.schemas.search import (
    CandidateSearchData,
    GradeCount,
    LocationCount,
    MatchSearchData,
    SkillCount,
    SummaryData,
    VacancySearchData,
)
from search.services.search_service import (
    _to_candidate_data,
    _to_match_data,
    _to_vacancy_data,
)
from search.routers.search import _parse_csv


class TestToCandidateData:

    def test_with_profile(self):
        class FakeCandidate:
            id = uuid.UUID("550e8400-e29b-41d4-a716-446655440000")
            full_name = "Иванов Иван"
            email = "ivan@test.com"
            phone = "+79001112233"

        class FakeProfile:
            skills = ["Python", "FastAPI"]
            grade = "middle"
            location = "Москва"
            experience_years = 4.0
            salary_expectation = 200000

        result = _to_candidate_data(FakeCandidate(), FakeProfile())

        assert result.full_name == "Иванов Иван"
        assert result.skills == ["Python", "FastAPI"]
        assert result.grade == "middle"
        assert result.experience_years == 4.0

    def test_without_profile(self):
        class FakeCandidate:
            id = uuid.UUID("550e8400-e29b-41d4-a716-446655440000")
            full_name = "Петров Пётр"
            email = None
            phone = None

        result = _to_candidate_data(FakeCandidate(), None)

        assert result.full_name == "Петров Пётр"
        assert result.skills == []
        assert result.grade is None
        assert result.experience_years is None


class TestToVacancyData:

    def test_with_requirements(self):
        class FakeReq:
            pass

        class FakeVacancy:
            id = uuid.UUID("660e8400-e29b-41d4-a716-446655440001")
            title = "Python Developer"
            department = "Backend"
            location = "Москва"
            grade = ["middle", "senior"]
            salary_min = 150000
            salary_max = 250000
            status = "open"
            requirements = [FakeReq(), FakeReq(), FakeReq()]

        result = _to_vacancy_data(FakeVacancy())

        assert result.title == "Python Developer"
        assert result.requirements_count == 3
        assert result.status == "open"

    def test_no_requirements(self):
        class FakeVacancy:
            id = uuid.UUID("660e8400-e29b-41d4-a716-446655440001")
            title = "QA Engineer"
            department = None
            location = "Remote"
            grade = []
            salary_min = None
            salary_max = None
            status = "draft"
            requirements = None

        result = _to_vacancy_data(FakeVacancy())

        assert result.requirements_count == 0
        assert result.grade == []


class TestToMatchData:

    def test_maps_all_fields(self):
        class FakeResult:
            candidate_id = uuid.UUID("550e8400-e29b-41d4-a716-446655440000")
            vacancy_id = uuid.UUID("660e8400-e29b-41d4-a716-446655440001")
            final_score = 85.5
            skill_score = 90.0
            experience_score = 80.0
            grade_score = 100.0
            location_score = 70.0
            salary_score = 60.0
            rank = 1

        class FakeCandidate:
            full_name = "Иванов Иван"

        class FakeVacancy:
            title = "Python Developer"

        result = _to_match_data(FakeResult(), FakeCandidate(), FakeVacancy())

        assert result.candidate_name == "Иванов Иван"
        assert result.vacancy_title == "Python Developer"
        assert result.final_score == 85.5
        assert result.rank == 1


class TestParseCsv:

    def test_parses_skills(self):
        result = _parse_csv("Python, FastAPI, Docker")

        assert result == ["Python", "FastAPI", "Docker"]

    def test_strips_whitespace(self):
        result = _parse_csv("  Python ,  FastAPI  ")

        assert result == ["Python", "FastAPI"]

    def test_empty_string(self):
        result = _parse_csv("")

        assert result == []

    def test_single_value(self):
        result = _parse_csv("Python")

        assert result == ["Python"]

    def test_trailing_comma(self):
        result = _parse_csv("Python,FastAPI,")

        assert result == ["Python", "FastAPI"]


class TestSchemas:

    def test_candidate_search_data_defaults(self):
        data = CandidateSearchData(id="1", full_name="Test")

        assert data.skills == []
        assert data.grade is None

    def test_vacancy_search_data_defaults(self):
        data = VacancySearchData(id="1", title="Dev", location="MSK", status="open")

        assert data.grade == []
        assert data.requirements_count == 0

    def test_summary_data_defaults(self):
        data = SummaryData()

        assert data.total_candidates == 0
        assert data.grades == []
        assert data.top_skills == []

    def test_grade_count(self):
        gc = GradeCount(grade="middle", count=42)

        assert gc.grade == "middle"
        assert gc.count == 42

    def test_summary_with_data(self):
        data = SummaryData(
            total_candidates=100,
            total_vacancies=20,
            total_matches=500,
            grades=[GradeCount(grade="middle", count=40)],
            top_skills=[SkillCount(skill="Python", count=80)],
            locations=[LocationCount(location="Москва", count=60)],
        )

        assert data.total_candidates == 100
        assert len(data.grades) == 1
        assert data.top_skills[0].skill == "Python"
