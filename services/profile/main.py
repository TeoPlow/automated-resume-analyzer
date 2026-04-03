import os
from datetime import datetime
from http import HTTPStatus
from typing import Any, Annotated, NoReturn
from uuid import uuid4
from fastapi import Depends, FastAPI, File, Form, Request, UploadFile
from pydantic import BaseModel, Field

from libs import (
	Actor,
	BaseResponse,
	install_exception_handlers,
	install_health_endpoint,
	install_request_id_middleware,
	raise_http,
)
from auth import require_authenticated_actor, require_internal_service
from events import get_event_publisher
from file_validation import read_and_validate_resume
from repository import get_repository
from storage import get_storage


app = FastAPI(title="Profile Service")
install_request_id_middleware(app)
install_exception_handlers(app)
install_health_endpoint(app)


class ResumeUploadContractInfo(BaseModel):
	resume_id: str
	candidate_id: str
	parsing_status: str


class CandidateInfo(BaseModel):
	candidate_id: str
	source: str
	external_id: str | None = None
	full_name: str | None = None
	email: str | None = None
	phone: str | None = None
	location: str | None = None
	profile: dict[str, Any] = Field(default_factory=dict)
	created_at: datetime
	updated_at: datetime


class ResumeInfo(BaseModel):
	resume_id: str
	candidate_id: str
	source: str
	external_id: str | None = None
	filename: str
	content_type: str
	size_bytes: int
	storage_key: str
	parsing_status: str
	uploaded_by_actor_id: str | None = None
	uploaded_at: datetime


class CandidatePatchRequest(BaseModel):
	full_name: str | None = Field(default=None, max_length=255)
	email: str | None = Field(default=None, max_length=320)
	phone: str | None = Field(default=None, max_length=64)
	location: str | None = Field(default=None, max_length=255)
	profile: dict[str, Any] | None = None


class CandidateBulkGetRequest(BaseModel):
	candidate_ids: list[str] = Field(min_length=1, max_length=500)


def _normalize_source(source: str) -> str:
	normalized = source.strip()
	if not normalized:
		raise_http(
			HTTPStatus.UNPROCESSABLE_CONTENT,
			"invalid_source",
			"Field 'source' cannot be empty",
		)
	return normalized


def _candidate_from_row(row: dict[str, Any]) -> CandidateInfo:
	return CandidateInfo(
		candidate_id=str(row["candidate_id"]),
		source=str(row["source"]),
		external_id=row.get("external_id"),
		full_name=row.get("full_name"),
		email=row.get("email"),
		phone=row.get("phone"),
		location=row.get("location"),
		profile=row.get("profile") or {},
		created_at=row["created_at"],
		updated_at=row["updated_at"],
	)


def _resume_from_row(row: dict[str, Any]) -> ResumeInfo:
	return ResumeInfo(
		resume_id=str(row["resume_id"]),
		candidate_id=str(row["candidate_id"]),
		source=str(row["source"]),
		external_id=row.get("external_id"),
		filename=str(row["filename"]),
		content_type=str(row["content_type"]),
		size_bytes=int(row["size_bytes"]),
		storage_key=str(row["storage_key"]),
		parsing_status=str(row["parsing_status"]),
		uploaded_by_actor_id=row.get("uploaded_by_actor_id"),
		uploaded_at=row["uploaded_at"],
	)


def _build_candidate_not_found(candidate_id: str) -> NoReturn:
	raise_http(
		HTTPStatus.NOT_FOUND,
		"candidate_not_found",
		"Candidate not found",
		{"candidate_id": candidate_id},
	)


@app.on_event("startup")
def setup_repository_schema() -> None:
	repository = get_repository()
	repository.ensure_schema()


async def _upload_resume_impl(
	file: UploadFile,
	source: str,
	external_id: str | None,
	actor: Actor,
	request_id: str | None,
) -> BaseResponse[ResumeUploadContractInfo]:
	normalized_source = _normalize_source(source)
	normalized_external_id = external_id.strip() if external_id else None
	max_size_bytes = int(os.getenv("RESUME_MAX_FILE_SIZE_BYTES", str(10 * 1024 * 1024)))
	content, size_bytes, extension, original_filename, content_type = await read_and_validate_resume(file, max_size_bytes)

	resume_id = uuid4().hex
	storage_key = f"resumes/{resume_id}.{extension}"
	parsing_status = "uploaded"

	storage = get_storage()
	storage.upload_resume(key=storage_key, content=content, content_type=content_type)

	repository = get_repository()
	candidate_id = repository.get_or_create_candidate(source=normalized_source, external_id=normalized_external_id)
	repository.save_resume_metadata(
		resume_id=resume_id,
		candidate_id=candidate_id,
		source=normalized_source,
		external_id=normalized_external_id,
		filename=original_filename,
		content_type=content_type,
		size_bytes=size_bytes,
		storage_key=storage_key,
		parsing_status=parsing_status,
		uploaded_by_actor_id=actor.actor_id,
	)

	publisher = get_event_publisher()
	publisher.publish(
		event_type="resume.uploaded",
		payload={
			"resume_id": resume_id,
			"candidate_id": candidate_id,
			"source": normalized_source,
			"external_id": normalized_external_id,
			"storage_key": storage_key,
		},
		request_id=request_id,
	)
	publisher.publish(
		event_type="candidate.profile.updated",
		payload={
			"candidate_id": candidate_id,
			"source": normalized_source,
			"trigger": "resume_upload",
		},
		request_id=request_id,
	)

	return BaseResponse(
		status="ok",
		data=ResumeUploadContractInfo(
			resume_id=resume_id,
			candidate_id=candidate_id,
			parsing_status=parsing_status,
		),
	)


@app.post(
	"/api/v1/profiles/resumes/upload",
	response_model=BaseResponse[ResumeUploadContractInfo],
	status_code=HTTPStatus.CREATED,
)
async def upload_resume(
	request: Request,
	actor: Annotated[Actor, Depends(require_authenticated_actor)],
	file: UploadFile = File(...),
	source: str = Form(...),
	external_id: str | None = Form(None),
) -> BaseResponse[ResumeUploadContractInfo]:
	request_id = request.headers.get("X-Request-Id")
	return await _upload_resume_impl(file=file, source=source, external_id=external_id, actor=actor, request_id=request_id)


@app.post(
	"/resumes",
	response_model=BaseResponse[ResumeUploadContractInfo],
	status_code=HTTPStatus.CREATED,
)
async def upload_resume_legacy(
	request: Request,
	actor: Annotated[Actor, Depends(require_authenticated_actor)],
	file: UploadFile = File(...),
	source: str = Form(...),
	external_id: str | None = Form(None),
) -> BaseResponse[ResumeUploadContractInfo]:
	request_id = request.headers.get("X-Request-Id")
	return await _upload_resume_impl(file=file, source=source, external_id=external_id, actor=actor, request_id=request_id)


@app.get(
	"/api/v1/profiles/candidates/{candidate_id}",
	response_model=BaseResponse[CandidateInfo],
)
def get_candidate(
	candidate_id: str,
	_: Annotated[Actor, Depends(require_authenticated_actor)],
) -> BaseResponse[CandidateInfo]:
	repository = get_repository()
	row = repository.get_candidate(candidate_id)
	if row is None:
		_build_candidate_not_found(candidate_id)

	return BaseResponse(status="ok", data=_candidate_from_row(row))


@app.patch(
	"/api/v1/profiles/candidates/{candidate_id}",
	response_model=BaseResponse[CandidateInfo],
)
def patch_candidate(
	candidate_id: str,
	payload: CandidatePatchRequest,
	request: Request,
	actor: Annotated[Actor, Depends(require_authenticated_actor)],
) -> BaseResponse[CandidateInfo]:
	repository = get_repository()
	updated = repository.update_candidate(
		candidate_id=candidate_id,
		full_name=payload.full_name,
		email=payload.email,
		phone=payload.phone,
		location=payload.location,
		profile_patch=payload.profile,
	)
	if updated is None:
		_build_candidate_not_found(candidate_id)

	publisher = get_event_publisher()
	publisher.publish(
		event_type="candidate.profile.updated",
		payload={
			"candidate_id": candidate_id,
			"source": updated.get("source"),
			"trigger": "candidate_patch",
			"actor_id": actor.actor_id,
		},
		request_id=request.headers.get("X-Request-Id"),
	)

	return BaseResponse(status="ok", data=_candidate_from_row(updated))


@app.get(
	"/api/v1/profiles/candidates/{candidate_id}/resumes",
	response_model=BaseResponse[list[ResumeInfo]],
)
def get_candidate_resumes(
	candidate_id: str,
	_: Annotated[Actor, Depends(require_authenticated_actor)],
) -> BaseResponse[list[ResumeInfo]]:
	repository = get_repository()
	candidate = repository.get_candidate(candidate_id)
	if candidate is None:
		_build_candidate_not_found(candidate_id)

	rows = repository.list_candidate_resumes(candidate_id)
	return BaseResponse(status="ok", data=[_resume_from_row(row) for row in rows])


@app.get(
	"/internal/v1/candidates/{candidate_id}",
	response_model=BaseResponse[CandidateInfo],
	dependencies=[Depends(require_internal_service)],
)
def internal_get_candidate(candidate_id: str) -> BaseResponse[CandidateInfo]:
	repository = get_repository()
	row = repository.get_candidate(candidate_id)
	if row is None:
		_build_candidate_not_found(candidate_id)
	return BaseResponse(status="ok", data=_candidate_from_row(row))


@app.post(
	"/internal/v1/candidates/bulk-get",
	response_model=BaseResponse[list[CandidateInfo]],
	dependencies=[Depends(require_internal_service)],
)
def internal_bulk_get_candidates(payload: CandidateBulkGetRequest) -> BaseResponse[list[CandidateInfo]]:
	repository = get_repository()
	rows = repository.bulk_get_candidates(payload.candidate_ids)
	return BaseResponse(status="ok", data=[_candidate_from_row(row) for row in rows])

