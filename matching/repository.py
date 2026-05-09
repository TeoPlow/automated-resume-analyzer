import uuid
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from matching.models.match import MatchExplanation, MatchResult, MatchRun


class MatchingRepository:
    """Доступ к данным матчинга"""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_run(
        self,
        vacancy_id: uuid.UUID,
        config: dict,
    ) -> MatchRun:
        """Создать запись о запуске матчинга"""
        run = MatchRun(
            vacancy_id=vacancy_id,
            status="running",
            config=config,
        )
        self._session.add(run)
        await self._session.flush()
        return run

    async def complete_run(
        self,
        run_id: uuid.UUID,
        status: str,
        total_candidates: int,
    ) -> None:
        """Завершить запуск матчинга"""
        stmt = (
            update(MatchRun)
            .where(MatchRun.id == run_id)
            .values(
                status=status,
                total_candidates=total_candidates,
                completed_at=datetime.now(timezone.utc),
            )
        )
        await self._session.execute(stmt)

    async def get_run(self, run_id: uuid.UUID) -> MatchRun | None:
        """Получить запуск матчинга по ID"""
        return await self._session.get(MatchRun, run_id)

    async def save_result(
        self,
        run_id: uuid.UUID,
        candidate_id: uuid.UUID,
        vacancy_id: uuid.UUID,
        scores: dict[str, float],
        final_score: float,
        rank: int,
    ) -> MatchResult:
        """Сохранить результат скоринга кандидата"""
        result = MatchResult(
            run_id=run_id,
            candidate_id=candidate_id,
            vacancy_id=vacancy_id,
            final_score=final_score,
            skill_score=scores["skills"],
            experience_score=scores["experience"],
            grade_score=scores["grade"],
            location_score=scores["location"],
            salary_score=scores["salary"],
            rank=rank,
        )
        self._session.add(result)
        await self._session.flush()
        return result

    async def save_explanation(
        self,
        result_id: uuid.UUID,
        factor: str,
        detail: str,
        score: float,
        weight: float,
        impact: float,
    ) -> MatchExplanation:
        """Сохранить пояснение к оценке по фактору"""
        explanation = MatchExplanation(
            result_id=result_id,
            factor=factor,
            detail=detail,
            score=score,
            weight=weight,
            impact=impact,
        )
        self._session.add(explanation)
        await self._session.flush()
        return explanation

    async def get_results_by_run(self, run_id: uuid.UUID) -> list[MatchResult]:
        """Получить все результаты запуска матчинга"""
        stmt = (
            select(MatchResult)
            .where(MatchResult.run_id == run_id)
            .order_by(MatchResult.rank.asc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_latest_results_by_vacancy(
        self, vacancy_id: uuid.UUID
    ) -> list[MatchResult]:
        """Получить результаты последнего завершённого запуска для вакансии"""
        run = await self.get_latest_completed_run_by_vacancy(vacancy_id)
        if not run:
            return []
        return await self.get_results_by_run(run.id)

    async def get_latest_completed_run_by_vacancy(
        self, vacancy_id: uuid.UUID
    ) -> MatchRun | None:
        """Получить последний завершённый запуск матчинга для вакансии"""
        run_stmt = (
            select(MatchRun)
            .where(
                MatchRun.vacancy_id == vacancy_id,
                MatchRun.status == "completed",
            )
            .order_by(MatchRun.completed_at.desc())
            .limit(1)
        )
        run_result = await self._session.execute(run_stmt)
        return run_result.scalar_one_or_none()

    async def get_results_by_candidate(
        self, candidate_id: uuid.UUID
    ) -> list[MatchResult]:
        """Получить все результаты матчинга для кандидата (последние по вакансиям)"""
        stmt = (
            select(MatchResult)
            .where(MatchResult.candidate_id == candidate_id)
            .order_by(MatchResult.final_score.desc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def commit(self) -> None:
        """Зафиксировать транзакцию"""
        await self._session.commit()
