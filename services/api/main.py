from http import HTTPStatus
from typing import Annotated, Any

from fastapi import Depends, FastAPI

from libs import (
    IntegrationKeyCreateRequest,
    IntegrationKeyCreateResponse,
    IntegrationKeyInfo,
    LoginRequest,
    LogoutRequest,
    MeResponse,
    RefreshRequest,
    TokenPair,
    install_exception_handlers,
    install_health_endpoint,
)
from auth import (
    Actor,
    authenticate,
    create_integration_api_key,
    list_integration_api_keys,
    login_user,
    refresh_user_tokens,
    logout_user,
    require_admin,
    revoke_integration_api_key,
    rotate_integration_api_key,
)
app = FastAPI(title="API-Gateway")
install_exception_handlers(app)
install_health_endpoint(app)


@app.get("/api/v1/health")
def api_v1_health() -> dict[str, Any]:
    return {"status": "ok", "service": app.title}


@app.post("/api/v1/auth/login", response_model=TokenPair)
def login(payload: LoginRequest) -> TokenPair:
    return login_user(payload.username, payload.password)


@app.post("/api/v1/auth/refresh", response_model=TokenPair)
def refresh(payload: RefreshRequest) -> TokenPair:
    return refresh_user_tokens(payload.refresh_token)


@app.post("/api/v1/auth/logout", status_code=HTTPStatus.NO_CONTENT)
def logout(payload: LogoutRequest) -> None:
    logout_user(payload.refresh_token)


@app.get("/api/v1/me", response_model=MeResponse)
def me(actor: Annotated[Actor, Depends(authenticate)]) -> MeResponse:
    return MeResponse(actor_id=actor.actor_id, actor_type=actor.actor_type, is_admin=actor.is_admin)


@app.post("/api/v1/integrations/keys", response_model=IntegrationKeyCreateResponse, status_code=HTTPStatus.CREATED)
def create_integration_key(
    payload: IntegrationKeyCreateRequest,
    _: Annotated[Actor, Depends(require_admin)],
) -> IntegrationKeyCreateResponse:
    return create_integration_api_key(payload.name)


@app.get("/api/v1/integrations/keys", response_model=list[IntegrationKeyInfo])
def list_integration_keys(_: Annotated[Actor, Depends(require_admin)]) -> list[IntegrationKeyInfo]:
    return list_integration_api_keys()


@app.post("/api/v1/integrations/keys/{key_id}/rotate", response_model=IntegrationKeyCreateResponse)
def rotate_integration_key(
    key_id: str,
    _: Annotated[Actor, Depends(require_admin)],
) -> IntegrationKeyCreateResponse:
    return rotate_integration_api_key(key_id)


@app.delete("/api/v1/integrations/keys/{key_id}", status_code=HTTPStatus.NO_CONTENT)
def revoke_integration_key(key_id: str, _: Annotated[Actor, Depends(require_admin)]) -> None:
    revoke_integration_api_key(key_id)
