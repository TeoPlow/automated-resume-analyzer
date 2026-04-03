from __future__ import annotations

import importlib
import os
from http import HTTPStatus
from typing import Any

from libs import make_http_exception, raise_http


httpx_module: Any | None = None


def _load_httpx() -> Any:
    global httpx_module
    if httpx_module is None:
        try:
            httpx_module = importlib.import_module("httpx")
        except ModuleNotFoundError as exc:
            raise make_http_exception(
                status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
                code="missing_dependency",
                message="HTTP client dependency is not installed",
                details={"dependency": str(exc.name)},
            ) from exc
    return httpx_module


class InternalServiceClient:
    def __init__(self) -> None:
        self._profile_base = os.getenv("PROFILE_INTERNAL_URL", "http://profile:8000/internal/v1").rstrip("/")
        self._vacancy_base = os.getenv("VACANCY_INTERNAL_URL", "http://vacancy:8000/internal/v1").rstrip("/")
        self._timeout_seconds = float(os.getenv("MATCHING_INTERNAL_TIMEOUT_SECONDS", "10"))
        self._internal_token = os.getenv("GATEWAY_INTERNAL_TOKEN")

    def _headers(self) -> dict[str, str]:
        headers: dict[str, str] = {}
        if self._internal_token:
            headers["X-Internal-Token"] = self._internal_token
        return headers

    async def get_vacancy(self, vacancy_id: str) -> dict[str, Any]:
        httpx = _load_httpx()

        try:
            async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
                response = await client.get(
                    f"{self._vacancy_base}/vacancies/{vacancy_id}",
                    headers=self._headers(),
                )
        except httpx.TimeoutException as exc:
            raise_http(
                HTTPStatus.GATEWAY_TIMEOUT,
                "vacancy_internal_timeout",
                "Vacancy internal API timed out",
                details={"vacancy_id": vacancy_id},
            )
            raise exc
        except httpx.RequestError as exc:
            raise_http(
                HTTPStatus.BAD_GATEWAY,
                "vacancy_internal_unreachable",
                "Cannot reach vacancy internal API",
                details={"vacancy_id": vacancy_id, "reason": str(exc)},
            )

        if response.status_code == HTTPStatus.NOT_FOUND:
            raise_http(
                HTTPStatus.NOT_FOUND,
                "vacancy_not_found",
                "Vacancy not found",
                details={"vacancy_id": vacancy_id},
            )

        if response.status_code >= HTTPStatus.BAD_REQUEST:
            raise_http(
                HTTPStatus.BAD_GATEWAY,
                "vacancy_internal_error",
                "Vacancy internal API returned an error",
                details={"status_code": response.status_code, "vacancy_id": vacancy_id},
            )

        payload = response.json()
        data = payload.get("data")
        if not isinstance(data, dict):
            raise_http(
                HTTPStatus.BAD_GATEWAY,
                "vacancy_internal_invalid_response",
                "Vacancy internal API response is invalid",
                details={"vacancy_id": vacancy_id},
            )

        return data

    async def bulk_get_candidates(self, candidate_ids: list[str]) -> list[dict[str, Any]]:
        if not candidate_ids:
            return []

        httpx = _load_httpx()

        try:
            async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
                response = await client.post(
                    f"{self._profile_base}/candidates/bulk-get",
                    headers=self._headers(),
                    json={"candidate_ids": candidate_ids},
                )
        except httpx.TimeoutException as exc:
            raise_http(
                HTTPStatus.GATEWAY_TIMEOUT,
                "profile_internal_timeout",
                "Profile internal API timed out",
                details={"candidate_count": len(candidate_ids)},
            )
            raise exc
        except httpx.RequestError as exc:
            raise_http(
                HTTPStatus.BAD_GATEWAY,
                "profile_internal_unreachable",
                "Cannot reach profile internal API",
                details={"candidate_count": len(candidate_ids), "reason": str(exc)},
            )

        if response.status_code >= HTTPStatus.BAD_REQUEST:
            raise_http(
                HTTPStatus.BAD_GATEWAY,
                "profile_internal_error",
                "Profile internal API returned an error",
                details={"status_code": response.status_code},
            )

        payload = response.json()
        data = payload.get("data")
        if not isinstance(data, list):
            raise_http(
                HTTPStatus.BAD_GATEWAY,
                "profile_internal_invalid_response",
                "Profile internal API response is invalid",
                details={"candidate_count": len(candidate_ids)},
            )

        return [item for item in data if isinstance(item, dict)]


internal_client: InternalServiceClient | None = None


def get_internal_client() -> InternalServiceClient:
    global internal_client
    if internal_client is None:
        internal_client = InternalServiceClient()
    return internal_client