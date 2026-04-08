import uuid

from common.logger import setup_logger

from profile.repository import ProfileRepository
from profile.services.event_publisher import EventPublisher
from profile.services.llm_parser import LlmParser
from profile.services.storage import FileStorage
from profile.services.text_extractor import TextExtractor

logger = setup_logger("profile.processor")


class ResumeProcessor:
    """Оркестратор пайплайна обработки резюме.

    Этапы: скачивание → извлечение текста → парсинг →
    дедупликация → агрегация профиля → событие.
    """

    def __init__(
        self,
        storage: FileStorage,
        text_extractor: TextExtractor,
        llm_parser: LlmParser,
        event_publisher: EventPublisher,
    ) -> None:
        self._storage = storage
        self._text_extractor = text_extractor
        self._llm_parser = llm_parser
        self._event_publisher = event_publisher

    async def process(
        self,
        resume_id: uuid.UUID,
        file_key: str,
        repo: ProfileRepository,
    ) -> None:
        """Выполнить полный пайплайн обработки резюме."""
        try:
            await repo.update_resume_status(resume_id, status="processing")
            await repo.commit()

            extension = file_key.rsplit(".", maxsplit=1)[-1].lower()
            content = self._storage.download(file_key)

            raw_text = self._text_extractor.extract(content, extension)
            await repo.update_resume_status(
                resume_id, status="processing", raw_text=raw_text
            )
            await repo.commit()

            parsed_data = await self._llm_parser.parse(raw_text)
            candidate_id = await self._deduplicate(parsed_data, repo)

            await repo.update_resume_status(
                resume_id,
                status="parsed",
                parsed_data=parsed_data.model_dump(),
                candidate_id=candidate_id,
            )
            await repo.commit()

            await self._aggregate_profile(candidate_id, repo)
            await repo.commit()

            logger.info(
                "Резюме %s обработано → кандидат %s", resume_id, candidate_id
            )
        except Exception as exc:
            logger.error("Ошибка обработки резюме %s: %s", resume_id, exc)
            await repo.update_resume_status(
                resume_id, status="failed", error_detail=str(exc)
            )
            await repo.commit()

    # --- Приватные методы ---

    async def _deduplicate(
        self, parsed_data, repo: ProfileRepository
    ) -> uuid.UUID:
        """Найти существующего кандидата или создать нового."""
        email = parsed_data.contacts.email
        if email:
            candidate = await repo.get_candidate_by_email(email)
            if candidate:
                logger.info("Дедупликация по email: %s", email)
                return candidate.id

        phone = parsed_data.contacts.phone
        if phone:
            candidate = await repo.get_candidate_by_phone(phone)
            if candidate:
                logger.info("Дедупликация по phone: %s", phone)
                return candidate.id

        candidate = await repo.create_candidate(
            full_name=parsed_data.full_name or "Неизвестный кандидат",
            email=email,
            phone=phone,
        )
        logger.info("Создан новый кандидат: %s", candidate.id)
        return candidate.id

    async def _aggregate_profile(
        self, candidate_id: uuid.UUID, repo: ProfileRepository
    ) -> None:
        """Агрегировать все резюме кандидата в единый профиль."""
        resumes = await repo.get_parsed_resumes(candidate_id)
        if not resumes:
            return

        all_skills: set[str] = set()
        all_experience: list[dict] = []
        all_education: list[dict] = []
        all_languages: list[dict] = []
        max_experience_years: float = 0.0

        experience_keys: set[str] = set()
        education_keys: set[str] = set()

        for resume in resumes:
            data = resume.parsed_data or {}
            for skill in data.get("skills", []):
                all_skills.add(skill.lower().strip())

            for exp in data.get("experience", []):
                key = _experience_dedup_key(exp)
                if key not in experience_keys:
                    experience_keys.add(key)
                    all_experience.append(exp)

            for edu in data.get("education", []):
                key = _education_dedup_key(edu)
                if key not in education_keys:
                    education_keys.add(key)
                    all_education.append(edu)

            for lang in data.get("languages", []):
                all_languages.append(lang)

            years = data.get("total_experience_years") or 0
            if years > max_experience_years:
                max_experience_years = years

        latest = resumes[-1].parsed_data or {}
        profile_data = {
            "skills": sorted(all_skills),
            "experience": all_experience,
            "education": all_education,
            "languages": all_languages,
            "location": latest.get("location"),
            "desired_salary": latest.get("desired_salary"),
            "desired_position": latest.get("desired_position"),
            "summary": latest.get("summary"),
            "total_experience_years": max_experience_years,
        }

        grade = latest.get("grade") or _infer_grade(max_experience_years)

        await repo.upsert_candidate_profile(
            candidate_id=candidate_id,
            data=profile_data,
            skills=sorted(all_skills),
            grade=grade,
            location=latest.get("location"),
            experience_years=max_experience_years,
            salary_expectation=latest.get("desired_salary"),
        )

        self._event_publisher.publish(
            routing_key="candidate.profile.updated",
            event_type="candidate.profile.updated",
            payload={
                "candidate_id": str(candidate_id),
                "skills": sorted(all_skills),
                "grade": grade,
                "experience_years": max_experience_years,
            },
        )


# --- Приватные функции ---


def _experience_dedup_key(exp: dict) -> str:
    """Ключ дедупликации записей об опыте работы."""
    company = (exp.get("company") or "").lower().strip()
    position = (exp.get("position") or "").lower().strip()
    start = (exp.get("start_date") or "").strip()
    return f"{company}|{position}|{start}"


def _education_dedup_key(edu: dict) -> str:
    """Ключ дедупликации записей об образовании."""
    institution = (edu.get("institution") or "").lower().strip()
    degree = (edu.get("degree") or "").lower().strip()
    return f"{institution}|{degree}"


def _infer_grade(experience_years: float) -> str:
    """Определить грейд по стажу работы."""
    if experience_years < 1:
        return "intern"
    if experience_years < 2:
        return "junior"
    if experience_years < 5:
        return "middle"
    if experience_years < 8:
        return "senior"
    return "lead"
