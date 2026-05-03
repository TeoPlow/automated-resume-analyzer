from pydantic import BaseModel


class HRUser(BaseModel):
    """HR-пользователь системы"""

    username: str
    password: str
    actor_type: str = "hr"
    is_admin: bool = False
    permissions: list[str] = []


class IntegrationKey(BaseModel):
    """API-ключ для внешней интеграции"""

    key_id: str
    name: str
    key_hash: str
    actor_type: str = "integration"
    permissions: list[str] = ["resumes:upload"]
    created_at: str
    is_active: bool = True
