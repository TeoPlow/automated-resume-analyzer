from pydantic import BaseModel

from .base import BaseResponse


class ResumeUploadInfo(BaseModel):
    resume_id: str
    filename: str
    content_type: str
    size_bytes: int
    storage_key: str


class ResumeUploadResponse(BaseResponse[ResumeUploadInfo]):
    pass
