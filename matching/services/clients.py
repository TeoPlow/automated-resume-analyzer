import httpx

from common.logger import setup_logger

logger = setup_logger("matching.clients")


class ServiceClient:
    """HTTP-клиент для внутренних вызовов к другим сервисам."""

    def __init__(
        self,
        profile_url: str,
        vacancy_url: str,
        internal_token: str,
    ) -> None:
        self._profile_url = profile_url.rstrip("/")
        self._vacancy_url = vacancy_url.rstrip("/")
        self._headers = {"X-Internal-Token": internal_token}
        self._client = httpx.AsyncClient(timeout=30.0)

    async def get_vacancy(self, vacancy_id: str) -> dict:
        """Получить вакансию через внутренний API Vacancy-сервиса."""
        url = f"{self._vacancy_url}/internal/v1/vacancies/{vacancy_id}"
        response = await self._client.get(url, headers=self._headers)
        response.raise_for_status()
        return response.json()["data"]

    async def get_candidates_bulk(self, candidate_ids: list[str]) -> list[dict]:
        """Получить кандидатов через внутренний API Profile-сервиса."""
        url = f"{self._profile_url}/internal/v1/candidates/bulk-get"
        response = await self._client.post(
            url,
            json={"candidate_ids": candidate_ids},
            headers=self._headers,
        )
        response.raise_for_status()
        return response.json()["data"]

    async def get_vacancies_bulk(self, vacancy_ids: list[str]) -> list[dict]:
        """Получить вакансии через внутренний API Vacancy-сервиса."""
        url = f"{self._vacancy_url}/internal/v1/vacancies/bulk-get"
        response = await self._client.post(
            url,
            json={"vacancy_ids": vacancy_ids},
            headers=self._headers,
        )
        response.raise_for_status()
        return response.json()["data"]

    async def get_active_candidates(self) -> list[dict]:
        """Получить всех активных кандидатов с профилем."""
        url = f"{self._profile_url}/internal/v1/candidates/active"
        response = await self._client.get(url, headers=self._headers)
        response.raise_for_status()
        return response.json()["data"]

    async def get_candidate(self, candidate_id: str) -> dict:
        """Получить одного кандидата через внутренний API Profile-сервиса."""
        url = f"{self._profile_url}/internal/v1/candidates/{candidate_id}"
        response = await self._client.get(url, headers=self._headers)
        response.raise_for_status()
        return response.json()["data"]

    async def close(self) -> None:
        """Закрыть HTTP-клиент."""
        await self._client.aclose()
