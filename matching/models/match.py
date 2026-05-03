import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from common.database import Base


class MatchRun(Base):
    """Запуск матчинга — одна итерация скоринга кандидатов по вакансии."""

    __tablename__ = "match_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    vacancy_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="running")
    config: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    total_candidates: Mapped[int | None] = mapped_column(Integer, nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    results: Mapped[list["MatchResult"]] = relationship(
        back_populates="run",
        lazy="selectin",
        cascade="all, delete-orphan",
    )


class MatchResult(Base):
    """Результат матчинга — оценка одного кандидата по вакансии."""

    __tablename__ = "match_results"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("match_runs.id"), nullable=False
    )
    candidate_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    vacancy_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    final_score: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    skill_score: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    experience_score: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    grade_score: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    location_score: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    salary_score: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)

    run: Mapped["MatchRun"] = relationship(back_populates="results", lazy="selectin")
    explanations: Mapped[list["MatchExplanation"]] = relationship(
        back_populates="result",
        lazy="selectin",
        cascade="all, delete-orphan",
    )


class MatchExplanation(Base):
    """Пояснение к оценке — вклад одного фактора."""

    __tablename__ = "match_explanations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    result_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("match_results.id"), nullable=False
    )
    factor: Mapped[str] = mapped_column(String(50), nullable=False)
    detail: Mapped[str] = mapped_column(Text, nullable=False)
    score: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    weight: Mapped[float] = mapped_column(Numeric(3, 2), nullable=False)
    impact: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)

    result: Mapped["MatchResult"] = relationship(
        back_populates="explanations", lazy="selectin"
    )
