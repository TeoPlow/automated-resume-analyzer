from profile.services.resume_processor import (
    _education_dedup_key,
    _experience_dedup_key,
    _infer_grade,
)


class TestInferGrade:

    def test_zero_experience_returns_intern(self):
        assert _infer_grade(0.0) == "intern"

    def test_one_year_returns_junior(self):
        assert _infer_grade(1.5) == "junior"

    def test_three_years_returns_middle(self):
        assert _infer_grade(3.0) == "middle"

    def test_six_years_returns_senior(self):
        assert _infer_grade(6.0) == "senior"

    def test_ten_years_returns_lead(self):
        assert _infer_grade(10.0) == "lead"


class TestDedupKeys:

    def test_experience_key_normalized(self):
        exp = {
            "company": "  Yandex  ",
            "position": " Backend Dev ",
            "start_date": "2020-01",
        }

        key = _experience_dedup_key(exp)

        assert key == "yandex|backend dev|2020-01"

    def test_education_key_normalized(self):
        edu = {"institution": " МГУ ", "degree": " Магистр "}

        key = _education_dedup_key(edu)

        assert key == "мгу|магистр"

    def test_missing_fields_handled(self):
        exp = {}

        key = _experience_dedup_key(exp)

        assert key == "||"
