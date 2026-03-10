from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from ..models import ActorType


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: Literal["Bearer"] = "Bearer"
    expires_in: int


class MeResponse(BaseModel):
    actor_id: str
    actor_type: ActorType
    is_admin: bool


class IntegrationKeyInfo(BaseModel):
    key_id: str
    name: str
    created_at: datetime
    revoked: bool


class IntegrationKeyCreateResponse(BaseModel):
    key_id: str
    name: str
    api_key: str
    created_at: datetime
