from __future__ import annotations

import os
from datetime import datetime
from http import HTTPStatus
from typing import Annotated, Any, NoReturn
from uuid import uuid4

from fastapi import Depends, FastAPI, Query, Request
from pydantic import BaseModel, Field

from auth import require_authenticated_actor, require_internal_service
from clients import get_internal_client
from events import get_event_publisher
from libs import Actor, BaseResponse, install_exception_handlers, install_health_endpoint, install_request_id_middleware, raise_http
from repository import get_repository


app = FastAPI(title="Matching Service")
install_request_id_middleware(app)
install_exception_handlers(app)
install_health_endpoint(app)


DEFAULT_TOP_K = int(os.getenv("MATCHING_DEFAULT_TOP_K", "20"))
MAX_TOP_K = int(os.getenv("MATCHING_MAX_TOP_K", "500"))
MAX_AUTO_CANDIDATES = int(os.getenv("MATCHING_MAX_AUTO_CANDIDATES", "1000"))
MAX_AUTO_VACANCIES = int(os.getenv("MATCHING_MAX_AUTO_VACANCIES", "500"))


class MatchRunRequest(BaseModel):
	vacancy_id: str = Field(min_length=1, max_length=128)
	candidate_ids: list[str] | None = Field(default=None, max_length=2000)
	top_k: int | None = Field(default=None, ge=1)
	force_recompute: bool = False


class InternalRunForVacancyRequest(BaseModel):
	candidate_ids: list[str] | None = Field(default=None, max_length=2000)
	top_k: int | None = Field(default=None, ge=1)
	force_recompute: bool = False
	initiated_by_actor_id: str = Field(default="system", max_length=128)


class InternalRunForCandidateRequest(BaseModel):
	vacancy_ids: list[str] | None = Field(default=None, max_length=2000)
	top_k: int | None = Field(default=None, ge=1)
	force_recompute: bool = False
	initiated_by_actor_id: str = Field(default="system", max_length=128)


class MatchRunInfo(BaseModel):
	run_id: str
	vacancy_id: str
	initiated_by_actor_id: str | None = None
	top_k: int
	force_recompute: bool
	status: str
	created_at: datetime
	completed_at: datetime | None = None


class MatchResultInfo(BaseModel):
	run_id: str
	vacancy_id: str
	candidate_id: str
	score: float
	rank_position: int
	computed_at: datetime
	explanation: dict[str, Any] = Field(default_factory=dict)


class MatchRunResultData(BaseModel):
	run: MatchRunInfo
	results: list[MatchResultInfo]


class MatchListData(BaseModel):
	items: list[MatchResultInfo]
	limit: int
	offset: int
	total: int


class RunForCandidateData(BaseModel):
	candidate_id: str
	run_ids: list[str]


def _normalize_top_k(value: int | None) -> int:
	resolved = value or DEFAULT_TOP_K
	if resolved > MAX_TOP_K:
		return MAX_TOP_K
	return resolved


def _extract_vacancy_requirements(vacancy: dict[str, Any]) -> set[str]:
	raw_requirements = vacancy.get("requirements")
	normalized: set[str] = set()

	if isinstance(raw_requirements, list):
		for item in raw_requirements:
			if isinstance(item, dict):
				requirement = str(item.get("normalized") or item.get("raw") or "").strip().lower()
				if requirement:
					normalized.add(requirement)
			elif isinstance(item, str):
				requirement = item.strip().lower()
				if requirement:
					normalized.add(requirement)
	return normalized


def _skills_from_profile(profile: dict[str, Any]) -> set[str]:
	collected: set[str] = set()
	skill_like_keys = {"skills", "hard_skills", "tech_stack", "stack", "tools"}

	for key, value in profile.items():
		key_name = str(key).lower()
		if key_name not in skill_like_keys:
			continue

		if isinstance(value, list):
			for item in value:
				skill = str(item).strip().lower()
				if skill:
					collected.add(skill)
		elif isinstance(value, str):
			for part in value.split(","):
				skill = part.strip().lower()
				if skill:
					collected.add(skill)

	return collected


def _score_candidate(candidate: dict[str, Any], vacancy_requirements: set[str]) -> tuple[float, dict[str, Any]]:
	profile = candidate.get("profile") if isinstance(candidate.get("profile"), dict) else {}
	candidate_skills = _skills_from_profile(profile)

	if not vacancy_requirements:
		return 0.0, {
			"matched_requirements": [],
			"missing_requirements": [],
			"candidate_skills": sorted(candidate_skills),
			"score_formula": "0 (vacancy has no normalized requirements)",
		}

	matched = sorted(vacancy_requirements & candidate_skills)
	missing = sorted(vacancy_requirements - candidate_skills)
	score = round((len(matched) / len(vacancy_requirements)) * 100.0, 2)

	explanation = {
		"matched_requirements": matched,
		"missing_requirements": missing,
		"candidate_skills": sorted(candidate_skills),
		"score_formula": f"{len(matched)}/{len(vacancy_requirements)} * 100",
	}
	return score, explanation


def _run_from_row(row: dict[str, Any]) -> MatchRunInfo:
	return MatchRunInfo(
		run_id=str(row["run_id"]),
		vacancy_id=str(row["vacancy_id"]),
		initiated_by_actor_id=row.get("initiated_by_actor_id"),
		top_k=int(row["top_k"]),
		force_recompute=bool(row["force_recompute"]),
		status=str(row["status"]),
		created_at=row["created_at"],
		completed_at=row.get("completed_at"),
	)


def _result_from_row(row: dict[str, Any]) -> MatchResultInfo:
	return MatchResultInfo(
		run_id=str(row["run_id"]),
		vacancy_id=str(row["vacancy_id"]),
		candidate_id=str(row["candidate_id"]),
		score=float(row["score"]),
		rank_position=int(row["rank_position"]),
		computed_at=row["computed_at"],
		explanation=row.get("explanation") if isinstance(row.get("explanation"), dict) else {},
	)


def _run_not_found(run_id: str) -> NoReturn:
	raise_http(
		HTTPStatus.NOT_FOUND,
		"run_not_found",
		"Matching run not found",
		details={"run_id": run_id},
	)


async def _execute_matching_run(
	vacancy_id: str,
	candidate_ids: list[str] | None,
	top_k: int | None,
	force_recompute: bool,
	initiated_by_actor_id: str,
	request_id: str | None,
) -> MatchRunResultData:
	repository = get_repository()
	client = get_internal_client()
	publisher = get_event_publisher()

	effective_top_k = _normalize_top_k(top_k)
	candidate_id_list = candidate_ids or repository.list_candidate_ids(MAX_AUTO_CANDIDATES)

	vacancy = await client.get_vacancy(vacancy_id)
	vacancy_requirements = _extract_vacancy_requirements(vacancy)

	run_id = uuid4().hex
	repository.create_run(
		run_id=run_id,
		vacancy_id=vacancy_id,
		initiated_by_actor_id=initiated_by_actor_id,
		top_k=effective_top_k,
		force_recompute=force_recompute,
		status="running",
	)

	try:
		candidates = await client.bulk_get_candidates(candidate_id_list)
		scored_results: list[dict[str, Any]] = []
		for candidate in candidates:
			candidate_id = str(candidate.get("candidate_id", "")).strip()
			if not candidate_id:
				continue

			score, explanation = _score_candidate(candidate, vacancy_requirements)
			scored_results.append(
				{
					"candidate_id": candidate_id,
					"score": score,
					"explanation": explanation,
				}
			)

		scored_results.sort(key=lambda item: (-float(item["score"]), str(item["candidate_id"])))
		trimmed_results = scored_results[:effective_top_k]

		repository.save_run_results(run_id=run_id, vacancy_id=vacancy_id, results=trimmed_results)
		repository.complete_run(run_id=run_id, status="completed")

		publisher.publish(
			event_type="matching.completed",
			payload={
				"run_id": run_id,
				"vacancy_id": vacancy_id,
				"results_count": len(trimmed_results),
				"top_k": effective_top_k,
			},
			request_id=request_id,
		)
	except Exception:
		repository.complete_run(run_id=run_id, status="failed")
		raise

	run_row = repository.get_run(run_id)
	if run_row is None:
		_run_not_found(run_id)
	result_rows = repository.get_results_for_run(run_id)

	return MatchRunResultData(
		run=_run_from_row(run_row),
		results=[_result_from_row(row) for row in result_rows],
	)


@app.on_event("startup")
def setup_repository_schema() -> None:
	repository = get_repository()
	repository.ensure_schema()


@app.post(
	"/api/v1/matching/run",
	response_model=BaseResponse[MatchRunResultData],
	status_code=HTTPStatus.CREATED,
)
async def run_matching(
	payload: MatchRunRequest,
	request: Request,
	actor: Annotated[Actor, Depends(require_authenticated_actor)],
) -> BaseResponse[MatchRunResultData]:
	data = await _execute_matching_run(
		vacancy_id=payload.vacancy_id,
		candidate_ids=payload.candidate_ids,
		top_k=payload.top_k,
		force_recompute=payload.force_recompute,
		initiated_by_actor_id=actor.actor_id,
		request_id=request.headers.get("X-Request-Id"),
	)
	return BaseResponse(status="ok", data=data)


@app.get(
	"/api/v1/matching/results/{run_id}",
	response_model=BaseResponse[MatchRunResultData],
)
def get_run_results(
	run_id: str,
	_: Annotated[Actor, Depends(require_authenticated_actor)],
) -> BaseResponse[MatchRunResultData]:
	repository = get_repository()
	run_row = repository.get_run(run_id)
	if run_row is None:
		_run_not_found(run_id)

	result_rows = repository.get_results_for_run(run_id)
	data = MatchRunResultData(
		run=_run_from_row(run_row),
		results=[_result_from_row(row) for row in result_rows],
	)
	return BaseResponse(status="ok", data=data)


@app.get(
	"/api/v1/matching/vacancies/{vacancy_id}",
	response_model=BaseResponse[MatchListData],
)
def get_results_by_vacancy(
	vacancy_id: str,
	limit: int = Query(default=20, ge=1, le=200),
	offset: int = Query(default=0, ge=0),
	_: Annotated[Actor, Depends(require_authenticated_actor)] = None,
) -> BaseResponse[MatchListData]:
	repository = get_repository()
	rows, total = repository.list_results_by_vacancy(vacancy_id=vacancy_id, limit=limit, offset=offset)
	items = [_result_from_row(row) for row in rows]
	return BaseResponse(status="ok", data=MatchListData(items=items, limit=limit, offset=offset, total=total))


@app.get(
	"/api/v1/matching/candidates/{candidate_id}/vacancies",
	response_model=BaseResponse[MatchListData],
)
def get_results_by_candidate(
	candidate_id: str,
	limit: int = Query(default=20, ge=1, le=200),
	offset: int = Query(default=0, ge=0),
	_: Annotated[Actor, Depends(require_authenticated_actor)] = None,
) -> BaseResponse[MatchListData]:
	repository = get_repository()
	rows, total = repository.list_results_by_candidate(candidate_id=candidate_id, limit=limit, offset=offset)
	items = [_result_from_row(row) for row in rows]
	return BaseResponse(status="ok", data=MatchListData(items=items, limit=limit, offset=offset, total=total))


@app.post(
	"/internal/v1/run-for-vacancy/{vacancy_id}",
	response_model=BaseResponse[MatchRunResultData],
	dependencies=[Depends(require_internal_service)],
)
async def internal_run_for_vacancy(
	vacancy_id: str,
	payload: InternalRunForVacancyRequest,
	request: Request,
) -> BaseResponse[MatchRunResultData]:
	data = await _execute_matching_run(
		vacancy_id=vacancy_id,
		candidate_ids=payload.candidate_ids,
		top_k=payload.top_k,
		force_recompute=payload.force_recompute,
		initiated_by_actor_id=payload.initiated_by_actor_id,
		request_id=request.headers.get("X-Request-Id"),
	)
	return BaseResponse(status="ok", data=data)


@app.post(
	"/internal/v1/run-for-candidate/{candidate_id}",
	response_model=BaseResponse[RunForCandidateData],
	dependencies=[Depends(require_internal_service)],
)
async def internal_run_for_candidate(
	candidate_id: str,
	payload: InternalRunForCandidateRequest,
	request: Request,
) -> BaseResponse[RunForCandidateData]:
	repository = get_repository()
	vacancy_ids = payload.vacancy_ids or repository.list_vacancy_ids(limit=MAX_AUTO_VACANCIES)

	run_ids: list[str] = []
	for vacancy_id in vacancy_ids:
		data = await _execute_matching_run(
			vacancy_id=vacancy_id,
			candidate_ids=[candidate_id],
			top_k=payload.top_k,
			force_recompute=payload.force_recompute,
			initiated_by_actor_id=payload.initiated_by_actor_id,
			request_id=request.headers.get("X-Request-Id"),
		)
		run_ids.append(data.run.run_id)

	return BaseResponse(status="ok", data=RunForCandidateData(candidate_id=candidate_id, run_ids=run_ids))


@app.get(
	"/internal/v1/results/by-vacancy/{vacancy_id}",
	response_model=BaseResponse[MatchListData],
	dependencies=[Depends(require_internal_service)],
)
def internal_results_by_vacancy(
	vacancy_id: str,
	limit: int = Query(default=100, ge=1, le=1000),
	offset: int = Query(default=0, ge=0),
) -> BaseResponse[MatchListData]:
	repository = get_repository()
	rows, total = repository.list_results_by_vacancy(vacancy_id=vacancy_id, limit=limit, offset=offset)
	items = [_result_from_row(row) for row in rows]
	return BaseResponse(status="ok", data=MatchListData(items=items, limit=limit, offset=offset, total=total))
