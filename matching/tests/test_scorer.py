import pytest

from unittest.mock import MagicMock

from matching.services.scorer import CandidateScorer, _make_explanation


class TestScoreSkillsExact:
    """Тесты exact-match скоринга навыков (fallback)."""

    def test_all_skills_match(self, scorer):
        result, detail = scorer._score_skills_exact(
            ["Python", "FastAPI", "Docker"],
            ["python", "fastapi", "docker"],
        )

        assert result == 100.0
        assert "3/3" in detail

    def test_partial_match(self, scorer):
        result, detail = scorer._score_skills_exact(
            ["Python", "Go"],
            ["python", "fastapi", "docker"],
        )

        assert result == pytest.approx(33.33, abs=0.1)
        assert "1/3" in detail

    def test_no_match(self, scorer):
        result, detail = scorer._score_skills_exact(
            ["Java", "C#"],
            ["python", "fastapi"],
        )

        assert result == 0.0
        assert "0/2" in detail

    def test_no_requirements(self, scorer):
        result, detail = scorer._score_skills_exact(
            ["Python"],
            [],
        )

        assert result == 100.0

    def test_empty_candidate_skills(self, scorer):
        result, detail = scorer._score_skills([], ["Python"])

        assert result == 0.0


class TestScoreExperience:
    """Тесты оценки опыта."""

    def test_experience_meets_requirement(self, scorer):
        result, detail = scorer._score_experience(
            5.0,
            [{"min_experience_years": 3}],
        )

        assert result == 100.0

    def test_experience_below_requirement(self, scorer):
        result, detail = scorer._score_experience(
            1.0,
            [{"min_experience_years": 4}],
        )

        assert result == 25.0

    def test_no_experience_specified(self, scorer):
        result, detail = scorer._score_experience(
            None,
            [{"min_experience_years": 3}],
        )

        assert result == 50.0

    def test_no_requirements_specified(self, scorer):
        result, detail = scorer._score_experience(5.0, [])

        assert result == 80.0


class TestScoreGrade:
    """Тесты оценки грейда."""

    def test_exact_grade_match(self, scorer):
        result, detail = scorer._score_grade("middle", ["middle", "senior"])

        assert result == 100.0

    def test_adjacent_grade(self, scorer):
        result, detail = scorer._score_grade("junior", ["middle"])

        assert result == 70.0

    def test_far_grade(self, scorer):
        result, detail = scorer._score_grade("intern", ["senior"])

        assert result == 10.0

    def test_no_vacancy_grade(self, scorer):
        result, detail = scorer._score_grade("middle", [])

        assert result == 80.0

    def test_no_candidate_grade(self, scorer):
        result, detail = scorer._score_grade(None, ["middle"])

        assert result == 50.0


class TestScoreLocation:
    """Тесты оценки локации."""

    def test_exact_match(self, scorer):
        result, detail = scorer._score_location("Москва", "Москва")

        assert result == 100.0

    def test_remote_vacancy(self, scorer):
        result, detail = scorer._score_location("Казань", "Remote")

        assert result == 100.0

    def test_mismatch(self, scorer):
        result, detail = scorer._score_location("Казань", "Москва")

        assert result == 30.0

    def test_no_candidate_location(self, scorer):
        result, detail = scorer._score_location(None, "Москва")

        assert result == 50.0


class TestScoreSalary:
    """Тесты оценки зарплаты."""

    def test_within_range(self, scorer):
        result, detail = scorer._score_salary(200000, 150000, 250000)

        assert result == 100.0

    def test_below_range(self, scorer):
        result, detail = scorer._score_salary(100000, 150000, 250000)

        assert result == 90.0

    def test_above_range(self, scorer):
        result, detail = scorer._score_salary(300000, 150000, 250000)

        assert result == 80.0

    def test_no_salary_expectation(self, scorer):
        result, detail = scorer._score_salary(None, 150000, 250000)

        assert result == 70.0

    def test_no_vacancy_range(self, scorer):
        result, detail = scorer._score_salary(200000, None, None)

        assert result == 80.0


class TestMakeExplanation:
    """Тесты формирования пояснений."""

    def test_explanation_structure(self):
        result = _make_explanation("skills", "3/4 совпали", 75.0, 0.40)

        assert result["factor"] == "skills"
        assert result["detail"] == "3/4 совпали"
        assert result["score"] == 75.0
        assert result["weight"] == 0.40
        assert result["impact"] == 30.0

    def test_zero_weight(self):
        result = _make_explanation("location", "не указано", 50.0, 0.0)

        assert result["impact"] == 0.0


class TestCompositeScore:
    """Тесты финального скоринга (без embedding, через exact match fallback)."""

    def test_ideal_candidate(
        self, scorer, sample_vacancy, sample_candidate, default_weights
    ):
        final, scores, explanations = scorer.score(
            sample_candidate, sample_vacancy, default_weights
        )

        assert final > 0
        assert len(explanations) == 5
        assert scores["location"] == 100.0
        assert scores["salary"] == 100.0
        assert scores["grade"] == 100.0

    def test_empty_profile(self, scorer, sample_vacancy, default_weights):
        candidate = {"id": "test", "profile": {}}

        final, scores, explanations = scorer.score(
            candidate, sample_vacancy, default_weights
        )

        assert final >= 0
        assert scores["skills"] == 0.0

    def test_no_profile_key(self, scorer, sample_vacancy, default_weights):
        candidate = {"id": "test"}

        final, scores, explanations = scorer.score(
            candidate, sample_vacancy, default_weights
        )

        assert final >= 0
        assert len(explanations) == 5


class TestEmbeddingPath:

    def test_embedding_match_uses_threshold(self, scorer, monkeypatch):
        class FakeRow:
            def __init__(self, values):
                self._values = values

            def max(self):
                return max(self._values)

            def argmax(self):
                return self._values.index(max(self._values))

        class FakeSimilarityMatrix:
            def __init__(self, values):
                self._values = values

            def __getitem__(self, index):
                return FakeRow(self._values[index])

        class FakeEmbeddingMatrix:
            def __init__(self, values):
                self._values = values

            @property
            def T(self):
                return FakeEmbeddingMatrix([list(column) for column in zip(*self._values)])

            def __matmul__(self, other):
                rows = []
                for row in self._values:
                    result_row = []
                    for column in zip(*other._values):
                        result_row.append(
                            sum(left * right for left, right in zip(row, column))
                        )
                    rows.append(result_row)
                return FakeSimilarityMatrix(rows)

        class FakeModel:
            def encode(self, texts, normalize_embeddings=True):
                if texts == ["Python", "FastAPI"]:
                    return FakeEmbeddingMatrix([[1.0, 0.0], [0.0, 1.0]])
                return FakeEmbeddingMatrix([[1.0, 0.0]])

        monkeypatch.setattr(scorer, "_get_model", MagicMock(return_value=FakeModel()))

        result, detail = scorer._score_skills(["Python"], ["Python", "FastAPI"])

        assert result == 50.0
        assert "1/2" in detail

    def test_embedding_error_falls_back_to_exact_match(self, scorer, monkeypatch):
        monkeypatch.setattr(
            scorer,
            "_get_model",
            MagicMock(side_effect=RuntimeError("boom")),
        )

        result, detail = scorer._score_skills(["Python"], ["Python"])

        assert result == 100.0
        assert "1/1" in detail


class TestGradeFallbacks:

    def test_unrecognized_vacancy_grade_uses_default_score(self, scorer):
        result, detail = scorer._score_grade("middle", ["unknown-grade"])

        assert result == 80.0
        assert "не распознан" in detail
