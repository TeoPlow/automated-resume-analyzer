import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from profile.models.candidate import Candidate, CandidateProfile, Resume


class ProfileRepository:
    """Доступ к данным кандидатов, резюме и профилей."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_resume(
        self,
        file_key: str,
        source: str,
        external_id: str | None = None,
    ) -> Resume:
        """Создать запись о загруженном резюме."""
        resume = Resume(
            file_key=file_key,
            source=source,
            external_id=external_id,
            status="uploaded",
        )
        self._session.add(resume)
        await self._session.flush()
        return resume

    async def get_resume(self, resume_id: uuid.UUID) -> Resume | None:
        """Получить резюме по ID."""
        return await self._session.get(Resume, resume_id)

    async def update_resume_status(
        self,
        resume_id: uuid.UUID,
        status: str,
        raw_text: str | None = None,
        parsed_data: dict | None = None,
        error_detail: str | None = None,
        candidate_id: uuid.UUID | None = None,
    ) -> None:
        """Обновить статус резюме и связанные данные."""
        values: dict = {"status": status}
        if raw_text is not None:
            values["raw_text"] = raw_text
        if parsed_data is not None:
            values["parsed_data"] = parsed_data
        if error_detail is not None:
            values["error_detail"] = error_detail
        if candidate_id is not None:
            values["candidate_id"] = candidate_id
        stmt = update(Resume).where(Resume.id == resume_id).values(**values)
        await self._session.execute(stmt)

    async def get_candidate(
        self, candidate_id: uuid.UUID
    ) -> Candidate | None:
        """Получить кандидата по ID с профилем и резюме."""
        return await self._session.get(Candidate, candidate_id)

    async def get_candidate_by_email(self, email: str) -> Candidate | None:
        """Найти кандидата по email."""
        stmt = select(Candidate).where(Candidate.email == email)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_candidate_by_phone(self, phone: str) -> Candidate | None:
        """Найти кандидата по телефону."""
        stmt = select(Candidate).where(Candidate.phone == phone)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def create_candidate(
        self,
        full_name: str,
        email: str | None = None,
        phone: str | None = None,
    ) -> Candidate:
        """Создать нового кандидата."""
        candidate = Candidate(
            full_name=full_name,
            email=email,
            phone=phone,
        )
        self._session.add(candidate)
        await self._session.flush()
        return candidate

    async def update_candidate(
        self,
        candidate_id: uuid.UUID,
        **fields: str | None,
    ) -> Candidate | None:
        """Обновить поля кандидата."""
        values: dict[str, Any] = {k: v for k, v in fields.items() if v is not None}
        if not values:
            return await self.get_candidate(candidate_id)
        values["updated_at"] = datetime.now(timezone.utc)
        stmt = (
            update(Candidate)
            .where(Candidate.id == candidate_id)
            .values(**values)
        )
        await self._session.execute(stmt)
        return await self.get_candidate(candidate_id)

    async def get_candidate_resumes(
        self, candidate_id: uuid.UUID
    ) -> list[Resume]:
        """Получить все резюме кандидата."""
        stmt = (
            select(Resume)
            .where(Resume.candidate_id == candidate_id)
            .order_by(Resume.created_at.desc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_parsed_resumes(
        self, candidate_id: uuid.UUID
    ) -> list[Resume]:
        """Получить все успешно распарсенные резюме кандидата."""
        stmt = (
            select(Resume)
            .where(
                Resume.candidate_id == candidate_id,
                Resume.status == "parsed",
            )
            .order_by(Resume.created_at.asc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_candidate_profile(
        self, candidate_id: uuid.UUID
    ) -> CandidateProfile | None:
        """Получить агрегированный профиль кандидата."""
        stmt = select(CandidateProfile).where(
            CandidateProfile.candidate_id == candidate_id
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def upsert_candidate_profile(
        self,
        candidate_id: uuid.UUID,
        data: dict,
        skills: list[str],
        grade: str | None,
        location: str | None,
        experience_years: float | None,
        salary_expectation: int | None,
    ) -> CandidateProfile:
        """Создать или обновить агрегированный профиль кандидата."""
        profile = await self.get_candidate_profile(candidate_id)
        if profile:
            profile.data = data
            profile.skills = skills
            profile.grade = grade
            profile.location = location
            profile.experience_years = experience_years
            profile.salary_expectation = salary_expectation
            profile.updated_at = datetime.now(timezone.utc)
        else:
            profile = CandidateProfile(
                candidate_id=candidate_id,
                data=data,
                skills=skills,
                grade=grade,
                location=location,
                experience_years=experience_years,
                salary_expectation=salary_expectation,
            )
            self._session.add(profile)
        await self._session.flush()
        return profile

    async def get_candidates_bulk(
        self, candidate_ids: list[uuid.UUID]
    ) -> list[Candidate]:
        """Получить список кандидатов по массиву ID."""
        stmt = select(Candidate).where(Candidate.id.in_(candidate_ids))
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_active_candidates(self) -> list[Candidate]:
        """Получить кандидатов с готовым агрегированным профилем."""
        stmt = (
            select(Candidate)
            .join(
                CandidateProfile,
                CandidateProfile.candidate_id == Candidate.id,
            )
            .order_by(Candidate.updated_at.desc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def delete_candidate(self, candidate_id: uuid.UUID) -> bool:
        """Удалить кандидата. Возвращает True, если кандидат найден."""
        candidate = await self.get_candidate(candidate_id)
        if not candidate:
            return False
        await self._session.delete(candidate)
        await self._session.flush()
        return True

    async def commit(self) -> None:
        """Зафиксировать транзакцию."""
        await self._session.commit()
