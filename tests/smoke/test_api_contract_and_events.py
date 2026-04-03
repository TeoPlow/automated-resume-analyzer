from __future__ import annotations

import json
from pathlib import Path

from tests.helpers.module_loader import load_service_module


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_api_contract_routes_exist_in_source() -> None:
    root = Path(__file__).resolve().parents[2]

    profile_main = _read_text(root / "services" / "profile" / "main.py")
    vacancy_main = _read_text(root / "services" / "vacancy" / "main.py")
    matching_main = _read_text(root / "services" / "matching" / "main.py")
    search_main = _read_text(root / "services" / "search" / "main.py")

    expected_routes = [
        "/api/v1/profiles/resumes/upload",
        "/api/v1/profiles/candidates/{candidate_id}",
        "/api/v1/profiles/candidates/{candidate_id}/resumes",
        "/api/v1/vacancies",
        "/api/v1/vacancies/{vacancy_id}",
        "/api/v1/matching/run",
        "/api/v1/matching/results/{run_id}",
        "/api/v1/matching/vacancies/{vacancy_id}",
        "/api/v1/matching/candidates/{candidate_id}/vacancies",
        "/api/v1/search/candidates",
        "/api/v1/search/vacancies",
        "/api/v1/search/matches",
        "/api/v1/search/summary",
    ]

    for route in expected_routes:
        all_sources = "\n".join([profile_main, vacancy_main, matching_main, search_main])
        assert route in all_sources


def _build_fake_pika(recorder: dict):
    class _FakeChannel:
        def exchange_declare(self, **kwargs):
            recorder["exchange_declare"] = kwargs

        def basic_publish(self, **kwargs):
            recorder["publish_kwargs"] = kwargs

    class _FakeConnection:
        def __init__(self, params):
            recorder["connection_params"] = params

        def channel(self):
            return _FakeChannel()

        def close(self):
            recorder["closed"] = True

    class _FakePika:
        class BasicProperties:
            def __init__(self, **kwargs):
                self.kwargs = kwargs

        @staticmethod
        def PlainCredentials(user, password):
            return {"user": user, "password": password}

        @staticmethod
        def ConnectionParameters(**kwargs):
            return kwargs

        @staticmethod
        def BlockingConnection(params):
            return _FakeConnection(params)

    return _FakePika


def _assert_event_envelope(payload: dict, event_type: str) -> None:
    assert payload["event_type"] == event_type
    assert payload["event_version"] == 1
    assert payload["event_id"]
    assert payload["occurred_at"]
    assert payload["producer"]
    assert isinstance(payload["payload"], dict)


def test_event_pipeline_contract_publishers() -> None:
    root = Path(__file__).resolve().parents[2]

    profile_events = load_service_module(
        module_name="profile_events_smoke",
        service_dir=root / "services" / "profile",
        file_name="events.py",
    )
    vacancy_events = load_service_module(
        module_name="vacancy_events_smoke",
        service_dir=root / "services" / "vacancy",
        file_name="events.py",
    )
    matching_events = load_service_module(
        module_name="matching_events_smoke",
        service_dir=root / "services" / "matching",
        file_name="events.py",
    )

    scenarios = [
        (profile_events.ProfileEventPublisher, "resume.uploaded"),
        (profile_events.ProfileEventPublisher, "candidate.profile.updated"),
        (vacancy_events.VacancyEventPublisher, "vacancy.created"),
        (vacancy_events.VacancyEventPublisher, "vacancy.updated"),
        (matching_events.MatchingEventPublisher, "matching.completed"),
    ]

    for publisher_cls, event_type in scenarios:
        recorder: dict = {}
        fake_pika = _build_fake_pika(recorder)

        original_loader = publisher_cls._load_pika
        publisher_cls._load_pika = staticmethod(lambda: fake_pika)
        try:
            publisher = publisher_cls()
            publisher.publish(event_type=event_type, payload={"entity_id": "demo"}, request_id="req-1")
        finally:
            publisher_cls._load_pika = original_loader

        published = recorder["publish_kwargs"]
        message = json.loads(published["body"].decode("utf-8"))

        assert published["routing_key"] == event_type
        _assert_event_envelope(message, event_type=event_type)
        assert message["request_id"] == "req-1"
