from typing import Literal

from pydantic import BaseModel


ActorType = Literal["hr", "integration"]


class Actor(BaseModel):
    actor_id: str
    actor_type: ActorType
    is_admin: bool
