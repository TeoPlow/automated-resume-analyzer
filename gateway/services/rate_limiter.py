import hashlib
import time
from collections import deque

from starlette.requests import Request

from common.logger import setup_logger

logger = setup_logger("gateway.rate_limiter")


class SlidingWindowRateLimiter:
    """Ограничитель частоты запросов по алгоритму скользящего окна"""

    def __init__(self, max_requests: int, window_seconds: int) -> None:
        self._max_requests = max_requests
        self._window_seconds = window_seconds
        self._windows: dict[str, deque[float]] = {}

    async def check(self, client_key: str) -> bool:
        """Проверить, допустим ли запрос. True — допустим, False — лимит превышен"""
        now = time.time()
        window = self._windows.setdefault(client_key, deque())

        cutoff = now - self._window_seconds
        while window and window[0] < cutoff:
            window.popleft()

        if len(window) >= self._max_requests:
            logger.warning(
                "Rate limit для клиента %s: %d/%d",
                client_key[:16],
                len(window),
                self._max_requests,
            )
            return False

        window.append(now)
        return True

    def extract_client_key(self, request: Request) -> str:
        """Извлечь уникальный ключ клиента из запроса для rate limiting"""
        api_key = request.headers.get("x-api-key")
        if api_key:
            return f"apikey:{hashlib.sha256(api_key.encode()).hexdigest()[:16]}"

        auth = request.headers.get("authorization", "")
        if auth:
            return f"auth:{hashlib.sha256(auth.encode()).hexdigest()[:16]}"

        client_host = request.client.host if request.client else "unknown"
        return f"ip:{client_host}"
