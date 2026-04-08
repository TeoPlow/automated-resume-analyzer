import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    ARRAY,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from common.database import Base


class Vacancy(Base):
    """Вакансия — позиция, на которую ведётся подбор кандидатов."""

    __tablename__ = "vacancies"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    department: Mapped[str | None] = mapped_column(
        String(100), nullable=True
    )
    location: Mapped[str] = mapped_column(String(255), nullable=False)
    grade: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, default=list
    )
    salary_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    salary_max: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="draft"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    requirements: Mapped[list["VacancyRequirement"]] = relationship(
        back_populates="vacancy",
        lazy="selectin",
        cascade="all, delete-orphan",
    )


class VacancyRequirement(Base):
    """Требование вакансии — навык с категорией и приоритетом."""

    __tablename__ = "vacancy_requirements"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    vacancy_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("vacancies.id"), nullable=False
    )
    skill: Mapped[str] = mapped_column(String(100), nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    priority: Mapped[str] = mapped_column(String(20), nullable=False)
    min_experience_years: Mapped[float | None] = mapped_column(
        Numeric(4, 1), nullable=True
    )

    vacancy: Mapped["Vacancy"] = relationship(
        back_populates="requirements", lazy="selectin"
    )
