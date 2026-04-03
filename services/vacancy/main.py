from __future__ import annotations

from datetime import datetime
from http import HTTPStatus
from typing import Annotated, Any, NoReturn
from uuid import uuid4

from fastapi import Depends, FastAPI, Query, Request
from pydantic import BaseModel, Field, model_validator

from auth import require_authenticated_actor, require_internal_service
from events import get_event_publisher
from libs import Actor, BaseResponse, install_exception_handlers, install_health_endpoint, install_request_id_middleware, raise_http
from repository import get_repository, normalize_requirements


app = FastAPI(title="Vacancy Service")
install_request_id_middleware(app)
install_exception_handlers(app)
install_health_endpoint(app)


ALLOWED_STATUSES = {"draft", "open", "closed", "archived"}


class VacancyRequirementInfo(BaseModel):
	raw: str
	normalized: str


class VacancyInfo(BaseModel):
	vacancy_id: str
	title: str
	description: str | None = None
	grade: str | None = None
	location: str | None = None
	status: str
	salary_from: float | None = None
	salary_to: float | None = None
	currency: str | None = None
	created_by_actor_id: str | None = None
	requirements: list[VacancyRequirementInfo] = Field(default_factory=list)
	created_at: datetime
	updated_at: datetime


class VacancyCreateRequest(BaseModel):
	title: str = Field(min_length=1, max_length=255)
	description: str | None = Field(default=None, max_length=4000)
	grade: str | None = Field(default=None, max_length=64)
	location: str | None = Field(default=None, max_length=255)
	status: str = Field(default="draft", max_length=32)
	salary_from: float | None = Field(default=None, ge=0)
	salary_to: float | None = Field(default=None, ge=0)
	currency: str | None = Field(default="RUB", max_length=16)
	requirements: list[str] = Field(default_factory=list, max_length=1000)

	@model_validator(mode="after")
	def validate_ranges(self) -> "VacancyCreateRequest":
		if self.salary_from is not None and self.salary_to is not None and self.salary_from > self.salary_to:
			raise ValueError("salary_from cannot be greater than salary_to")
		return self


class VacancyPatchRequest(BaseModel):
	title: str | None = Field(default=None, min_length=1, max_length=255)
	description: str | None = Field(default=None, max_length=4000)
	grade: str | None = Field(default=None, max_length=64)
	location: str | None = Field(default=None, max_length=255)
	status: str | None = Field(default=None, max_length=32)
	salary_from: float | None = Field(default=None, ge=0)
	salary_to: float | None = Field(default=None, ge=0)
	currency: str | None = Field(default=None, max_length=16)
	requirements: list[str] | None = Field(default=None, max_length=1000)

	@model_validator(mode="after")
	def validate_ranges(self) -> "VacancyPatchRequest":
		if self.salary_from is not None and self.salary_to is not None and self.salary_from > self.salary_to:
			raise ValueError("salary_from cannot be greater than salary_to")
		return self


class VacancyListData(BaseModel):
	items: list[VacancyInfo]
	limit: int
	offset: int
	total: int


class VacancyBulkGetRequest(BaseModel):
	vacancy_ids: list[str] = Field(min_length=1, max_length=500)


def _normalize_status(status: str | None) -> str | None:
	if status is None:
		return None

	normalized = status.strip().lower()
	if normalized not in ALLOWED_STATUSES:
		raise_http(
			HTTPStatus.UNPROCESSABLE_CONTENT,
			"invalid_status",
			"Invalid vacancy status",
			details={"status": status, "allowed_statuses": sorted(ALLOWED_STATUSES)},
		)
	return normalized


def _vacancy_not_found(vacancy_id: str) -> NoReturn:
	raise_http(
		HTTPStatus.NOT_FOUND,
		"vacancy_not_found",
		"Vacancy not found",
		details={"vacancy_id": vacancy_id},
	)


def _vacancy_from_row(row: dict[str, Any]) -> VacancyInfo:
	requirements = [VacancyRequirementInfo(**item) for item in row.get("requirements") or []]
	return VacancyInfo(
		vacancy_id=str(row["vacancy_id"]),
		title=str(row["title"]),
		description=row.get("description"),
		grade=row.get("grade"),
		location=row.get("location"),
		status=str(row["status"]),
		salary_from=float(row["salary_from"]) if row.get("salary_from") is not None else None,
		salary_to=float(row["salary_to"]) if row.get("salary_to") is not None else None,
		currency=row.get("currency"),
		created_by_actor_id=row.get("created_by_actor_id"),
		requirements=requirements,
		created_at=row["created_at"],
		updated_at=row["updated_at"],
	)


@app.on_event("startup")
def setup_repository_schema() -> None:
	repository = get_repository()
	repository.ensure_schema()


@app.post(
	"/api/v1/vacancies",
	response_model=BaseResponse[VacancyInfo],
	status_code=HTTPStatus.CREATED,
)
def create_vacancy(
	payload: VacancyCreateRequest,
	request: Request,
	actor: Annotated[Actor, Depends(require_authenticated_actor)],
) -> BaseResponse[VacancyInfo]:
	normalized_status = _normalize_status(payload.status) or "draft"
	normalized_requirements = normalize_requirements(payload.requirements)

	repository = get_repository()
	vacancy_id = uuid4().hex
	row = repository.create_vacancy(
		vacancy_id=vacancy_id,
		title=payload.title.strip(),
		description=payload.description,
		grade=payload.grade,
		location=payload.location,
		status=normalized_status,
		salary_from=payload.salary_from,
		salary_to=payload.salary_to,
		currency=payload.currency,
		requirements=normalized_requirements,
		created_by_actor_id=actor.actor_id,
	)

	request_id = request.headers.get("X-Request-Id")
	publisher = get_event_publisher()
	publisher.publish(
		event_type="vacancy.created",
		payload={
			"vacancy_id": vacancy_id,
			"status": normalized_status,
			"requirements_count": len(normalized_requirements),
			"actor_id": actor.actor_id,
		},
		request_id=request_id,
	)

	return BaseResponse(status="ok", data=_vacancy_from_row(row))


@app.get(
	"/api/v1/vacancies/{vacancy_id}",
	response_model=BaseResponse[VacancyInfo],
)
def get_vacancy(
	vacancy_id: str,
	_: Annotated[Actor, Depends(require_authenticated_actor)],
) -> BaseResponse[VacancyInfo]:
	repository = get_repository()
	row = repository.get_vacancy(vacancy_id)
	if row is None:
		_vacancy_not_found(vacancy_id)
	return BaseResponse(status="ok", data=_vacancy_from_row(row))


@app.patch(
	"/api/v1/vacancies/{vacancy_id}",
	response_model=BaseResponse[VacancyInfo],
)
def patch_vacancy(
	vacancy_id: str,
	payload: VacancyPatchRequest,
	request: Request,
	actor: Annotated[Actor, Depends(require_authenticated_actor)],
) -> BaseResponse[VacancyInfo]:
	normalized_status = _normalize_status(payload.status)
	normalized_requirements = normalize_requirements(payload.requirements) if payload.requirements is not None else None

	repository = get_repository()
	updated = repository.update_vacancy(
		vacancy_id=vacancy_id,
		title=payload.title.strip() if payload.title is not None else None,
		description=payload.description,
		grade=payload.grade,
		location=payload.location,
		status=normalized_status,
		salary_from=payload.salary_from,
		salary_to=payload.salary_to,
		currency=payload.currency,
		requirements=normalized_requirements,
	)

	if updated is None:
		_vacancy_not_found(vacancy_id)

	request_id = request.headers.get("X-Request-Id")
	publisher = get_event_publisher()
	publisher.publish(
		event_type="vacancy.updated",
		payload={
			"vacancy_id": vacancy_id,
			"status": updated["status"],
			"requirements_count": len(updated.get("requirements") or []),
			"actor_id": actor.actor_id,
		},
		request_id=request_id,
	)

	return BaseResponse(status="ok", data=_vacancy_from_row(updated))


@app.get(
	"/api/v1/vacancies",
	response_model=BaseResponse[VacancyListData],
)
def list_vacancies(
	limit: int = Query(default=20, ge=1, le=200),
	offset: int = Query(default=0, ge=0),
	status: str | None = Query(default=None),
	location: str | None = Query(default=None),
	grade: str | None = Query(default=None),
	_: Annotated[Actor, Depends(require_authenticated_actor)] = None,
) -> BaseResponse[VacancyListData]:
	normalized_status = _normalize_status(status)

	repository = get_repository()
	rows, total = repository.list_vacancies(
		limit=limit,
		offset=offset,
		status=normalized_status,
		location=location,
		grade=grade,
	)

	items = [_vacancy_from_row(row) for row in rows]
	return BaseResponse(
		status="ok",
		data=VacancyListData(items=items, limit=limit, offset=offset, total=total),
	)


@app.get(
	"/internal/v1/vacancies/{vacancy_id}",
	response_model=BaseResponse[VacancyInfo],
	dependencies=[Depends(require_internal_service)],
)
def internal_get_vacancy(vacancy_id: str) -> BaseResponse[VacancyInfo]:
	repository = get_repository()
	row = repository.get_vacancy(vacancy_id)
	if row is None:
		_vacancy_not_found(vacancy_id)
	return BaseResponse(status="ok", data=_vacancy_from_row(row))


@app.post(
	"/internal/v1/vacancies/bulk-get",
	response_model=BaseResponse[list[VacancyInfo]],
	dependencies=[Depends(require_internal_service)],
)
def internal_bulk_get_vacancies(payload: VacancyBulkGetRequest) -> BaseResponse[list[VacancyInfo]]:
	repository = get_repository()
	rows = repository.bulk_get_vacancies(payload.vacancy_ids)
	return BaseResponse(status="ok", data=[_vacancy_from_row(row) for row in rows])
