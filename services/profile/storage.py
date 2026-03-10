from __future__ import annotations

import importlib
import os
from http import HTTPStatus

from fastapi import HTTPException
from libs import make_http_exception


class ResumeStorage:
    def __init__(self) -> None:
        boto3_module, _, _ = _load_s3_dependencies()

        endpoint = os.getenv("MINIO_ENDPOINT")
        access_key = os.getenv("MINIO_ACCESS_KEY")
        secret_key = os.getenv("MINIO_SECRET_KEY")
        region = os.getenv("AWS_REGION", "us-east-1")

        self.bucket_name = os.getenv("RESUME_BUCKET", "resumes")
        self.client = boto3_module.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region,
        )

    def ensure_bucket_exists(self) -> None:
        _, ClientError, BotoCoreError = _load_s3_dependencies()

        try:
            self.client.head_bucket(Bucket=self.bucket_name)
        except ClientError as exc:
            error_code = exc.response.get("Error", {}).get("Code")
            if error_code in {"404", "NoSuchBucket"}:
                self.client.create_bucket(Bucket=self.bucket_name)
            else:
                raise self._storage_http_exception("Cannot access S3 bucket", exc) from exc
        except BotoCoreError as exc:
            raise self._storage_http_exception("Cannot access S3 storage", exc) from exc

    def upload_resume(self, key: str, content: bytes, content_type: str) -> None:
        _, ClientError, BotoCoreError = _load_s3_dependencies()

        self.ensure_bucket_exists()
        try:
            self.client.put_object(
                Bucket=self.bucket_name,
                Key=key,
                Body=content,
                ContentType=content_type,
            )
        except (ClientError, BotoCoreError) as exc:
            raise self._storage_http_exception("Failed to upload resume to S3", exc) from exc

    @staticmethod
    def _storage_http_exception(message: str, error: Exception) -> HTTPException:
        return make_http_exception(
            status_code=HTTPStatus.SERVICE_UNAVAILABLE,
            code="storage_unavailable",
            message=message,
            details={"exception": error.__class__.__name__},
        )


_storage: ResumeStorage | None = None


def _load_s3_dependencies():
    try:
        boto3_module = importlib.import_module("boto3")
        botocore_exceptions = importlib.import_module("botocore.exceptions")
        return boto3_module, botocore_exceptions.ClientError, botocore_exceptions.BotoCoreError
    except ModuleNotFoundError as exc:
        raise make_http_exception(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            code="missing_dependency",
            message="S3 dependencies are not installed",
            details={"dependency": str(exc.name)},
        ) from exc


def get_storage() -> ResumeStorage:
    global _storage
    if _storage is None:
        _storage = ResumeStorage()
    return _storage
