from profile.routers import internal


class _DummyConfig:
    INTERNAL_TOKEN = "test-internal-token"


class _DummyDb:
    def session(self):
        raise RuntimeError("session must not be called in route order test")


def test_active_route_precedes_dynamic_candidate_route() -> None:
    router = internal.create_router(_DummyConfig(), _DummyDb())

    get_paths = [
        route.path
        for route in router.routes
        if getattr(route, "methods", None) and "GET" in route.methods
    ]

    active_path = "/internal/v1/candidates/active"
    dynamic_path = "/internal/v1/candidates/{candidate_id:uuid}"

    assert active_path in get_paths
    assert dynamic_path in get_paths
    assert get_paths.index(active_path) < get_paths.index(dynamic_path)
