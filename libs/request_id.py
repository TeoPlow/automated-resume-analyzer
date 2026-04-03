from __future__ import annotations

import uuid

from fastapi import FastAPI, Request


def install_request_id_middleware(app: FastAPI) -> None:
    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next):
        request_id = getattr(request.state, "request_id", None) or request.headers.get("X-Request-Id") or uuid.uuid4().hex
        request.state.request_id = request_id

        response = await call_next(request)
        response.headers["X-Request-Id"] = request_id
        return response