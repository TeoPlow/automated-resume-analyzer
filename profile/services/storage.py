import uuid

import boto3
from botocore.config import Config as BotoConfig

from common.logger import setup_logger

logger = setup_logger("profile.storage")


class FileStorage:
    """Менеджер хранилища файлов в MinIO/S3."""

    def __init__(
        self,
        endpoint: str,
        access_key: str,
        secret_key: str,
        bucket: str,
        use_ssl: bool = False,
    ) -> None:
        protocol = "https" if use_ssl else "http"
        self._bucket = bucket
        self._client = boto3.client(
            "s3",
            endpoint_url=f"{protocol}://{endpoint}",
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            config=BotoConfig(signature_version="s3v4"),
        )
        self._ensure_bucket()

    def upload(self, content: bytes, extension: str) -> str:
        """Загрузить файл в хранилище, вернуть file_key."""
        file_key = f"{uuid.uuid4()}.{extension}"
        self._client.put_object(
            Bucket=self._bucket,
            Key=file_key,
            Body=content,
        )
        logger.info("Файл загружен: %s", file_key)
        return file_key

    def download(self, file_key: str) -> bytes:
        """Скачать файл из хранилища по ключу."""
        response = self._client.get_object(Bucket=self._bucket, Key=file_key)
        return response["Body"].read()

    # --- Приватные методы ---

    def _ensure_bucket(self) -> None:
        """Создать бакет, если он не существует."""
        try:
            self._client.head_bucket(Bucket=self._bucket)
        except Exception:
            self._client.create_bucket(Bucket=self._bucket)
            logger.info("Бакет создан: %s", self._bucket)
