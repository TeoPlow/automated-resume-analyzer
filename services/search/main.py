from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

from fastapi import Depends, FastAPI, Query
from pydantic import BaseModel, Field

from auth import require_authenticated_actor
from libs import Actor, BaseResponse, install_exception_handlers, install_health_endpoint, install_request_id_middleware
from repository import get_repository


app = FastAPI(title="Search Service")
install_request_id_middleware(app)
install_exception_handlers(app)
install_health_endpoint(app)


class CandidateSearchItem(BaseModel):
	candidate_id: str
	full_name: str | None = None
	email: str | None = None
	phone: str | None = None
	location: str | None = None
	source: str
	external_id: str | None = None
	profile: dict[str, Any] = Field(default_factory=dict)
	latest_match_score: float | None = None
	latest_match_vacancy_id: str | None = None
	latest_match_computed_at: datetime | None = None
	created_at: datetime
	updated_at: datetime


class VacancySearchItem(BaseModel):
	vacancy_id: str
	title: str
	description: str | None = None
	grade: str | None = None
	location: str | None = None
	status: str
	salary_from: float | None = None
	salary_to: float | None = None
	currency: str | None = None
	requirements: list[str] = Field(default_factory=list)
	created_at: datetime
	updated_at: datetime


class MatchSearchItem(BaseModel):
	run_id: str
	vacancy_id: str
	candidate_id: str
	score: float
	rank_position: int
	computed_at: datetime
	explanation: dict[str, Any] = Field(default_factory=dict)


class SearchListData[T](BaseModel):
	items: list[T]
	limit: int
	offset: int
	total: int


class SearchSummaryData(BaseModel):
	total_candidates: int
	total_vacancies: int
	open_vacancies: int
	total_matches: int
	total_runs: int
	completed_runs: int
	average_score: float | None = None


def _candidate_item(row: dict[str, Any]) -> CandidateSearchItem:
	return CandidateSearchItem(
		candidate_id=str(row["candidate_id"]),
		full_name=row.get("full_name"),
		email=row.get("email"),
		phone=row.get("phone"),
		location=row.get("location"),
		source=str(row["source"]),
		external_id=row.get("external_id"),
		profile=row.get("profile") or {},
		latest_match_score=float(row["latest_match_score"]) if row.get("latest_match_score") is not None else None,
		latest_match_vacancy_id=row.get("latest_match_vacancy_id"),
		latest_match_computed_at=row.get("latest_match_computed_at"),
		created_at=row["created_at"],
		updated_at=row["updated_at"],
	)


def _vacancy_item(row: dict[str, Any]) -> VacancySearchItem:
	return VacancySearchItem(
		vacancy_id=str(row["vacancy_id"]),
		title=str(row["title"]),
		description=row.get("description"),
		grade=row.get("grade"),
		location=row.get("location"),
		status=str(row["status"]),
		salary_from=float(row["salary_from"]) if row.get("salary_from") is not None else None,
		salary_to=float(row["salary_to"]) if row.get("salary_to") is not None else None,
		currency=row.get("currency"),
		requirements=[str(item) for item in (row.get("requirements") or [])],
		created_at=row["created_at"],
		updated_at=row["updated_at"],
	)


def _match_item(row: dict[str, Any]) -> MatchSearchItem:
	return MatchSearchItem(
		run_id=str(row["run_id"]),
		vacancy_id=str(row["vacancy_id"]),
		candidate_id=str(row["candidate_id"]),
		score=float(row["score"]),
		rank_position=int(row["rank_position"]),
		computed_at=row["computed_at"],
		explanation=row.get("explanation") if isinstance(row.get("explanation"), dict) else {},
	)


@app.on_event("startup")
def setup_search_indexes() -> None:
	repository = get_repository()
	repository.ensure_search_indexes()


@app.get(
	"/api/v1/search/candidates",
	response_model=BaseResponse[SearchListData[CandidateSearchItem]],
)
def search_candidates(
	skills: list[str] = Query(default_factory=list),
	grade: str | None = Query(default=None),
	location: str | None = Query(default=None),
	experience_years: float | None = Query(default=None, ge=0),
	salary: float | None = Query(default=None, ge=0),
	status: str | None = Query(default=None),
	limit: int = Query(default=20, ge=1, le=200),
	offset: int = Query(default=0, ge=0),
	sort_by: str = Query(default="updated_at"),
	sort_order: str = Query(default="desc"),
	_: Annotated[Actor, Depends(require_authenticated_actor)] = None,
) -> BaseResponse[SearchListData[CandidateSearchItem]]:
	repository = get_repository()
	rows, total = repository.search_candidates(
		skills=skills,
		grade=grade,
		location=location,
		experience_years=experience_years,
		salary=salary,
		status=status,
		limit=limit,
		offset=offset,
		sort_by=sort_by,
		sort_order=sort_order,
	)

	items = [_candidate_item(row) for row in rows]
	return BaseResponse(
		status="ok",
		data=SearchListData(items=items, limit=limit, offset=offset, total=total),
	)


@app.get(
	"/api/v1/search/vacancies",
	response_model=BaseResponse[SearchListData[VacancySearchItem]],
)
def search_vacancies(
	query: str | None = Query(default=None),
	status: str | None = Query(default=None),
	grade: str | None = Query(default=None),
	location: str | None = Query(default=None),
	skill: str | None = Query(default=None),
	limit: int = Query(default=20, ge=1, le=200),
	offset: int = Query(default=0, ge=0),
	sort_by: str = Query(default="updated_at"),
	sort_order: str = Query(default="desc"),
	_: Annotated[Actor, Depends(require_authenticated_actor)] = None,
) -> BaseResponse[SearchListData[VacancySearchItem]]:
	repository = get_repository()
	rows, total = repository.search_vacancies(
		query=query,
		status=status,
		grade=grade,
		location=location,
		skill=skill,
		limit=limit,
		offset=offset,
		sort_by=sort_by,
		sort_order=sort_order,
	)

	items = [_vacancy_item(row) for row in rows]
	return BaseResponse(
		status="ok",
		data=SearchListData(items=items, limit=limit, offset=offset, total=total),
	)


@app.get(
	"/api/v1/search/matches",
	response_model=BaseResponse[SearchListData[MatchSearchItem]],
)
def search_matches(
	vacancy_id: str | None = Query(default=None),
	candidate_id: str | None = Query(default=None),
	run_id: str | None = Query(default=None),
	min_score: float | None = Query(default=None, ge=0, le=100),
	limit: int = Query(default=20, ge=1, le=200),
	offset: int = Query(default=0, ge=0),
	sort_by: str = Query(default="score"),
	sort_order: str = Query(default="desc"),
	_: Annotated[Actor, Depends(require_authenticated_actor)] = None,
) -> BaseResponse[SearchListData[MatchSearchItem]]:
	repository = get_repository()
	rows, total = repository.search_matches(
		vacancy_id=vacancy_id,
		candidate_id=candidate_id,
		run_id=run_id,
		min_score=min_score,
		limit=limit,
		offset=offset,
		sort_by=sort_by,
		sort_order=sort_order,
	)

	items = [_match_item(row) for row in rows]
	return BaseResponse(
		status="ok",
		data=SearchListData(items=items, limit=limit, offset=offset, total=total),
	)


@app.get(
	"/api/v1/search/summary",
	response_model=BaseResponse[SearchSummaryData],
)
def search_summary(
	_: Annotated[Actor, Depends(require_authenticated_actor)],
) -> BaseResponse[SearchSummaryData]:
	repository = get_repository()
	summary = repository.get_summary()
	return BaseResponse(status="ok", data=SearchSummaryData(**summary))
