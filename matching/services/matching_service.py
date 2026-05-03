import uuid

from common.exceptions import AppError
from common.logger import setup_logger

from matching.config import MatchingConfig
from matching.repository import MatchingRepository
from matching.schemas.match import (
    ExplanationData,
    MatchResultData,
    MatchRunData,
    MatchRunRequest,
    MatchWeights,
)
from matching.services.clients import ServiceClient
from matching.services.event_publisher import EventPublisher
from matching.services.scorer import CandidateScorer

logger = setup_logger("matching.service")


class MatchingService:
    """Управление процессом матчинга: запуск, скоринг, публикация."""

    def __init__(
        self,
        config: MatchingConfig,
        scorer: CandidateScorer,
        client: ServiceClient,
        events: EventPublisher,
    ) -> None:
        self._config = config
        self._scorer = scorer
        self._client = client
        self._events = events

    async def run(
        self,
        body: MatchRunRequest,
        repo: MatchingRepository,
    ) -> MatchRunData:
        """Запустить матчинг: получить данные, рассчитать скоры, сохранить."""
        vacancy_id = _parse_uuid(body.vacancy_id)
        weights = self._resolve_weights(body.weights)

        if self._can_reuse_latest_run(body):
            existing_run = await repo.get_latest_completed_run_by_vacancy(
                vacancy_id
            )
            if existing_run:
                logger.info(
                    "Использован существующий run=%s для vacancy=%s",
                    existing_run.id,
                    vacancy_id,
                )
                return MatchRunData(
                    run_id=str(existing_run.id),
                    status=existing_run.status,
                )

        run = await repo.create_run(
            vacancy_id=vacancy_id,
            config={"weights": weights},
        )
        await repo.commit()

        try:
            vacancy = await self._client.get_vacancy(body.vacancy_id)
            candidates = await self._fetch_candidates(body)

            scored = []
            for cand in candidates:
                final_score, scores, explanations = self._scorer.score(
                    cand, vacancy, weights
                )
                scored.append((cand, final_score, scores, explanations))

            scored.sort(key=lambda x: x[1], reverse=True)

            if body.top_k:
                scored = scored[: body.top_k]

            for rank, (cand, final_score, scores, explanations) in enumerate(
                scored, start=1
            ):
                result = await repo.save_result(
                    run_id=run.id,
                    candidate_id=uuid.UUID(cand["id"]),
                    vacancy_id=vacancy_id,
                    scores=scores,
                    final_score=final_score,
                    rank=rank,
                )
                for expl in explanations:
                    await repo.save_explanation(
                        result_id=result.id, **expl
                    )

            await repo.complete_run(
                run.id, status="completed", total_candidates=len(scored)
            )
            await repo.commit()

            top_score = scored[0][1] if scored else 0.0
            self._events.publish(
                routing_key="matching.completed",
                event_type="matching.completed",
                payload={
                    "run_id": str(run.id),
                    "vacancy_id": str(vacancy_id),
                    "total_scored": len(scored),
                    "top_score": top_score,
                },
            )
            logger.info(
                "Матчинг завершён: run=%s, кандидатов=%d, top=%.2f",
                run.id,
                len(scored),
                top_score,
            )

        except Exception as exc:
            logger.error("Ошибка матчинга: %s", exc)
            await repo.complete_run(run.id, status="failed", total_candidates=0)
            await repo.commit()
            raise AppError(
                code="matching_failed",
                message=f"Ошибка выполнения матчинга: {exc}",
                status_code=500,
            )

        return MatchRunData(run_id=str(run.id), status="completed")

    async def get_results(
        self, run_id: str, repo: MatchingRepository
    ) -> list[MatchResultData]:
        """Получить результаты по ID запуска."""
        uid = _parse_uuid(run_id)
        results = await repo.get_results_by_run(uid)
        return await self._to_result_data_list(results)

    async def get_vacancy_results(
        self, vacancy_id: str, repo: MatchingRepository
    ) -> list[MatchResultData]:
        """Получить лучших кандидатов по последнему запуску для вакансии."""
        uid = _parse_uuid(vacancy_id)
        results = await repo.get_latest_results_by_vacancy(uid)
        return await self._to_result_data_list(results)

    async def get_candidate_vacancies(
        self, candidate_id: str, repo: MatchingRepository
    ) -> list[MatchResultData]:
        """Получить подходящие вакансии для кандидата."""
        uid = _parse_uuid(candidate_id)
        results = await repo.get_results_by_candidate(uid)
        return await self._to_result_data_list(results)

    async def _to_result_data_list(
        self, results: list
    ) -> list[MatchResultData]:
        """Обогатить результаты именем кандидата и названием вакансии."""
        if not results:
            return []

        candidate_names = await self._load_candidate_names(results)
        vacancy_titles = await self._load_vacancy_titles(results)

        return [
            _to_result_data(
                r,
                candidate_name=candidate_names.get(str(r.candidate_id)),
                vacancy_title=vacancy_titles.get(str(r.vacancy_id)),
            )
            for r in results
        ]

    async def _load_candidate_names(self, results: list) -> dict[str, str]:
        """Загрузить ФИО кандидатов по списку результатов."""
        candidate_ids = sorted({str(r.candidate_id) for r in results})
        if not candidate_ids:
            return {}

        try:
            candidates = await self._client.get_candidates_bulk(candidate_ids)
        except Exception as exc:
            logger.warning("Не удалось загрузить кандидатов для обогащения: %s", exc)
            return {}

        return {
            c["id"]: c.get("full_name")
            for c in candidates
            if c.get("id") and c.get("full_name")
        }

    async def _load_vacancy_titles(self, results: list) -> dict[str, str]:
        """Загрузить названия вакансий по списку результатов."""
        vacancy_ids = sorted({str(r.vacancy_id) for r in results})
        if not vacancy_ids:
            return {}

        try:
            vacancies = await self._client.get_vacancies_bulk(vacancy_ids)
        except Exception as exc:
            logger.warning("Не удалось загрузить вакансии для обогащения: %s", exc)
            return {}

        return {
            v["id"]: v.get("title")
            for v in vacancies
            if v.get("id") and v.get("title")
        }

    def _resolve_weights(
        self, weights: MatchWeights | None
    ) -> dict[str, float]:
        """Получить веса: пользовательские или из конфигурации."""
        if weights:
            return weights.model_dump()
        return {
            "skills": self._config.DEFAULT_WEIGHT_SKILLS,
            "experience": self._config.DEFAULT_WEIGHT_EXPERIENCE,
            "grade": self._config.DEFAULT_WEIGHT_GRADE,
            "location": self._config.DEFAULT_WEIGHT_LOCATION,
            "salary": self._config.DEFAULT_WEIGHT_SALARY,
        }

    async def _fetch_candidates(
        self, body: MatchRunRequest
    ) -> list[dict]:
        """Загрузить кандидатов для скоринга."""
        if body.candidate_ids is not None:
            return await self._client.get_candidates_bulk(body.candidate_ids)
        return await self._client.get_active_candidates()

    @staticmethod
    def _can_reuse_latest_run(body: MatchRunRequest) -> bool:
        """Проверить, можно ли переиспользовать существующий completed run."""
        return (
            not body.force_recompute
            and body.candidate_ids is None
            and body.top_k is None
            and body.weights is None
        )


def _parse_uuid(value: str) -> uuid.UUID:
    """Преобразовать строку в UUID."""
    try:
        return uuid.UUID(value)
    except ValueError:
        raise AppError(
            code="invalid_id",
            message="Некорректный формат ID",
            status_code=400,
        )


def _to_result_data(
    result,
    candidate_name: str | None = None,
    vacancy_title: str | None = None,
) -> MatchResultData:
    """Преобразовать ORM-модель результата в Pydantic-схему."""
    explanations = []
    for e in (result.explanations or []):
        explanations.append(
            ExplanationData(
                factor=e.factor,
                detail=e.detail,
                score=float(e.score),
                weight=float(e.weight),
                impact=float(e.impact),
            )
        )
    return MatchResultData(
        id=str(result.id),
        candidate_id=str(result.candidate_id),
        candidate_name=candidate_name,
        vacancy_id=str(result.vacancy_id),
        vacancy_title=vacancy_title,
        final_score=float(result.final_score),
        skill_score=float(result.skill_score),
        experience_score=float(result.experience_score),
        grade_score=float(result.grade_score),
        location_score=float(result.location_score),
        salary_score=float(result.salary_score),
        rank=result.rank,
        explanations=explanations,
    )
