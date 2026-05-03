from common.logger import setup_logger

logger = setup_logger("matching.scorer")

_GRADE_ORDER = {"intern": 0, "junior": 1, "middle": 2, "senior": 3, "lead": 4}


class CandidateScorer:
    """Вычисление composite-скоринга кандидата по вакансии.

    Факторы:
    - skills: семантическое сходство навыков (cosine similarity)
    - experience: соответствие опыта требованиям
    - grade: соответствие грейда
    - location: совпадение локации
    - salary: попадание в зарплатную вилку
    """

    def __init__(self, embedding_model_name: str) -> None:
        self._model_name = embedding_model_name
        self._model = None

    def score(
        self,
        candidate: dict,
        vacancy: dict,
        weights: dict[str, float],
    ) -> tuple[float, dict[str, float], list[dict]]:
        """Рассчитать итоговый скоринг кандидата.

        Возвращает (final_score, factor_scores, explanations).
        """
        profile = candidate.get("profile") or {}

        skill_score, skill_detail = self._score_skills(
            profile.get("skills", []),
            [r["skill"] for r in vacancy.get("requirements", [])],
        )
        exp_score, exp_detail = self._score_experience(
            profile.get("experience_years"),
            vacancy.get("requirements", []),
        )
        grade_score, grade_detail = self._score_grade(
            profile.get("grade"),
            vacancy.get("grade", []),
        )
        loc_score, loc_detail = self._score_location(
            profile.get("location"),
            vacancy.get("location"),
        )
        sal_score, sal_detail = self._score_salary(
            profile.get("salary_expectation"),
            vacancy.get("salary_min"),
            vacancy.get("salary_max"),
        )

        scores = {
            "skills": skill_score,
            "experience": exp_score,
            "grade": grade_score,
            "location": loc_score,
            "salary": sal_score,
        }

        final = sum(scores[k] * weights[k] for k in scores)

        explanations = [
            _make_explanation("skills", skill_detail, skill_score, weights["skills"]),
            _make_explanation("experience", exp_detail, exp_score, weights["experience"]),
            _make_explanation("grade", grade_detail, grade_score, weights["grade"]),
            _make_explanation("location", loc_detail, loc_score, weights["location"]),
            _make_explanation("salary", sal_detail, sal_score, weights["salary"]),
        ]

        return round(final, 2), scores, explanations

    # --- Приватные методы ---

    def _get_model(self):
        """Ленивая загрузка embedding-модели."""
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self._model_name)
            logger.info("Embedding-модель загружена: %s", self._model_name)
        return self._model

    def _score_skills(
        self,
        candidate_skills: list[str],
        required_skills: list[str],
    ) -> tuple[float, str]:
        """Оценить навыки через семантическое сходство."""
        if not required_skills:
            return 100.0, "Требования к навыкам не указаны"
        if not candidate_skills:
            return 0.0, "У кандидата нет навыков в профиле"

        try:
            model = self._get_model()

            req_embeddings = model.encode(required_skills, normalize_embeddings=True)
            cand_embeddings = model.encode(candidate_skills, normalize_embeddings=True)

            similarity_matrix = req_embeddings @ cand_embeddings.T

            matched = 0
            matched_skills = []
            for i, req_skill in enumerate(required_skills):
                max_sim = float(similarity_matrix[i].max())
                if max_sim >= 0.6:
                    matched += 1
                    best_idx = int(similarity_matrix[i].argmax())
                    matched_skills.append(
                        f"{req_skill} ≈ {candidate_skills[best_idx]} ({max_sim:.0%})"
                    )

            score = (matched / len(required_skills)) * 100
            detail = (
                f"Совпадение: {matched}/{len(required_skills)}. "
                + "; ".join(matched_skills[:5])
            )
            return round(score, 2), detail

        except Exception as exc:
            logger.warning("Ошибка embedding-скоринга: %s, fallback на exact match", exc)
            return self._score_skills_exact(candidate_skills, required_skills)

    def _score_skills_exact(
        self,
        candidate_skills: list[str],
        required_skills: list[str],
    ) -> tuple[float, str]:
        """Fallback: точное совпадение навыков (без embeddings)."""
        cand_lower = {s.lower().strip() for s in candidate_skills}
        matched = [s for s in required_skills if s.lower().strip() in cand_lower]
        score = (len(matched) / len(required_skills)) * 100 if required_skills else 100
        detail = f"Точное совпадение: {len(matched)}/{len(required_skills)}"
        return round(score, 2), detail

    def _score_experience(
        self,
        candidate_years: float | None,
        requirements: list[dict],
    ) -> tuple[float, str]:
        """Оценить опыт кандидата относительно требований."""
        if candidate_years is None:
            return 50.0, "Опыт кандидата не указан"

        min_years_list: list[float] = [
            float(r["min_experience_years"])
            for r in requirements
            if r.get("min_experience_years")
        ]
        if not min_years_list:
            return 80.0, f"Требования к опыту не указаны, у кандидата {candidate_years} лет"

        avg_required = sum(min_years_list) / len(min_years_list)
        if candidate_years >= avg_required:
            return 100.0, f"{candidate_years} лет ≥ требуемых {avg_required:.1f}"

        ratio = candidate_years / avg_required if avg_required > 0 else 0
        score = max(ratio * 100, 0)
        detail = f"{candidate_years} лет из требуемых {avg_required:.1f}"
        return round(score, 2), detail

    def _score_grade(
        self,
        candidate_grade: str | None,
        vacancy_grades: list[str],
    ) -> tuple[float, str]:
        """Оценить соответствие грейда кандидата вакансии."""
        if not vacancy_grades:
            return 80.0, "Грейд вакансии не указан"
        if not candidate_grade:
            return 50.0, "Грейд кандидата не определён"

        cand_lvl = _GRADE_ORDER.get(candidate_grade.lower(), -1)
        vacancy_levels = [_GRADE_ORDER.get(g.lower(), -1) for g in vacancy_grades]
        vacancy_levels = [v for v in vacancy_levels if v >= 0]

        if not vacancy_levels:
            return 80.0, f"Грейд вакансии не распознан: {vacancy_grades}"

        if cand_lvl in vacancy_levels:
            return 100.0, f"Грейд {candidate_grade} соответствует"

        min_dist = min(abs(cand_lvl - v) for v in vacancy_levels)
        score = max(100 - min_dist * 30, 0)
        detail = f"Грейд {candidate_grade}, ожидается {vacancy_grades}"
        return round(score, 2), detail

    def _score_location(
        self,
        candidate_location: str | None,
        vacancy_location: str | None,
    ) -> tuple[float, str]:
        """Оценить совпадение локации."""
        if not vacancy_location or vacancy_location.lower() == "remote":
            return 100.0, "Удалённая работа или локация не указана"
        if not candidate_location:
            return 50.0, "Локация кандидата не указана"

        if candidate_location.lower().strip() == vacancy_location.lower().strip():
            return 100.0, f"Локация совпадает: {candidate_location}"

        return 30.0, f"Кандидат: {candidate_location}, вакансия: {vacancy_location}"

    def _score_salary(
        self,
        candidate_salary: int | None,
        vacancy_min: int | None,
        vacancy_max: int | None,
    ) -> tuple[float, str]:
        """Оценить попадание зарплатных ожиданий в вилку вакансии."""
        if candidate_salary is None:
            return 70.0, "Зарплатные ожидания кандидата не указаны"

        if vacancy_min is None and vacancy_max is None:
            return 80.0, f"Вилка не указана, ожидания: {candidate_salary}"

        low = vacancy_min or 0
        high = vacancy_max or float("inf")

        if low <= candidate_salary <= high:
            return 100.0, f"Ожидания {candidate_salary} в вилке [{low}–{high}]"

        if candidate_salary < low:
            return 90.0, f"Ожидания {candidate_salary} ниже вилки [{low}–{high}]"

        overshoot = (candidate_salary - high) / high if high > 0 else 1
        score = max(100 - overshoot * 100, 0)
        detail = f"Ожидания {candidate_salary} выше вилки [{low}–{high}]"
        return round(score, 2), detail


def _make_explanation(
    factor: str,
    detail: str,
    score: float,
    weight: float,
) -> dict:
    """Создать запись пояснения к оценке."""
    return {
        "factor": factor,
        "detail": detail,
        "score": round(score, 2),
        "weight": round(weight, 2),
        "impact": round(score * weight, 2),
    }
