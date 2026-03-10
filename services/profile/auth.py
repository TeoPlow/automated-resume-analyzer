from __future__ import annotations

import os
from http import HTTPStatus
from typing import Annotated

from fastapi import Header

from libs import Actor, ActorType, raise_http


def _parse_bool_header(value: str | None) -> bool:
    if not value:
        return False
    return value.strip().lower() in {"1", "true", "yes", "on"}


def require_authenticated_actor(
    x_actor_id: Annotated[str | None, Header()] = None,
    x_actor_type: Annotated[str | None, Header()] = None,
    x_is_admin: Annotated[str | None, Header()] = None,
    x_internal_token: Annotated[str | None, Header()] = None,
) -> Actor:
    internal_token = os.getenv("GATEWAY_INTERNAL_TOKEN")
    if internal_token and x_internal_token != internal_token:
        raise_http(
            HTTPStatus.UNAUTHORIZED,
            "unauthorized",
            "Invalid internal gateway token",
        )

    if not x_actor_id or not x_actor_type:
        raise_http(
            HTTPStatus.UNAUTHORIZED,
            "unauthorized",
            "Missing actor headers",
            details={"required_headers": ["X-Actor-Id", "X-Actor-Type"]},
        )

    if x_actor_type not in {"hr", "integration"}:
        raise_http(
            HTTPStatus.FORBIDDEN,
            "forbidden",
            "Unsupported actor type",
            details={"actor_type": x_actor_type, "allowed_types": ["hr", "integration"]},
        )

    actor_type: ActorType
    if x_actor_type == "hr":
        actor_type = "hr"
    else:
        actor_type = "integration"

    return Actor(
        actor_id=x_actor_id,
        actor_type=actor_type,
        is_admin=_parse_bool_header(x_is_admin),
    )
