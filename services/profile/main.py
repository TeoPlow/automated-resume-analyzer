import os
from http import HTTPStatus
from uuid import uuid4
from fastapi import Depends, FastAPI, File, UploadFile

from libs import (
	ResumeUploadInfo,
	ResumeUploadResponse,
	install_exception_handlers,
	install_health_endpoint
)
from auth import require_authenticated_actor
from file_validation import read_and_validate_resume
from storage import get_storage


app = FastAPI(title="Profile Service")
install_exception_handlers(app)
install_health_endpoint(app)


@app.post(
	"/resumes",
	response_model=ResumeUploadResponse,
	status_code=HTTPStatus.CREATED,
	dependencies=[Depends(require_authenticated_actor)],
)
async def upload_resume(file: UploadFile = File(...)) -> ResumeUploadResponse:
	max_size_bytes = int(os.getenv("RESUME_MAX_FILE_SIZE_BYTES", str(10 * 1024 * 1024)))
	content, size_bytes, extension, original_filename, content_type = await read_and_validate_resume(file, max_size_bytes)

	resume_id = uuid4().hex
	storage_key = f"resumes/{resume_id}.{extension}"

	storage = get_storage()
	storage.upload_resume(key=storage_key, content=content, content_type=content_type)

	return ResumeUploadResponse(
		status="ok",
		data=ResumeUploadInfo(
			resume_id=resume_id,
			filename=original_filename,
			content_type=content_type,
			size_bytes=size_bytes,
			storage_key=storage_key,
		),
	)

