import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from matching.services.clients import ServiceClient
from matching.services.event_publisher import EventPublisher


class FakeResponse:

    def __init__(self, data):
        self._data = data

    def raise_for_status(self):
        return None

    def json(self):
        return {"data": self._data}


class FakeParams:

    def __init__(self, url):
        self.url = url
        self.heartbeat = None
        self.blocked_connection_timeout = None


class FakeChannel:

    def __init__(self):
        self.is_open = True
        self.exchange_declares = []
        self.published = []

    def exchange_declare(self, **kwargs):
        self.exchange_declares.append(kwargs)

    def basic_publish(self, **kwargs):
        self.published.append(kwargs)


class FakeConnection:

    def __init__(self, params):
        self.params = params
        self.is_open = True
        self.closed = False
        self._channel = FakeChannel()

    def channel(self):
        return self._channel

    def close(self):
        self.closed = True
        self.is_open = False


@pytest.mark.asyncio
async def test_service_client_calls_expected_endpoints():
    client = ServiceClient("http://profile/", "http://vacancy/", "token")
    http_client = MagicMock()
    http_client.get = AsyncMock(
        side_effect=[
            FakeResponse({"id": "vacancy-1"}),
            FakeResponse([{"id": "candidate-active"}]),
            FakeResponse({"id": "candidate-3"}),
        ]
    )
    http_client.post = AsyncMock(
        side_effect=[
            FakeResponse([{"id": "candidate-bulk"}]),
            FakeResponse([{"id": "vacancy-bulk"}]),
        ]
    )
    http_client.aclose = AsyncMock()
    client._client = http_client

    assert client._profile_url == "http://profile"
    assert client._vacancy_url == "http://vacancy"
    assert client._headers == {"X-Internal-Token": "token"}

    assert await client.get_vacancy("vacancy-1") == {"id": "vacancy-1"}
    assert await client.get_candidates_bulk(["candidate-1"]) == [
        {"id": "candidate-bulk"}
    ]
    assert await client.get_vacancies_bulk(["vacancy-2"]) == [
        {"id": "vacancy-bulk"}
    ]
    assert await client.get_active_candidates() == [{"id": "candidate-active"}]
    assert await client.get_candidate("candidate-3") == {"id": "candidate-3"}

    await client.close()


def test_event_publisher_connect_publish_and_close(monkeypatch):
    monkeypatch.setattr(
        "matching.services.event_publisher.URLParameters",
        FakeParams,
    )
    monkeypatch.setattr(
        "matching.services.event_publisher.BlockingConnection",
        FakeConnection,
    )

    publisher = EventPublisher("amqp://guest:guest@rabbitmq:5672/", "events", "dlx")

    publisher.connect()
    assert publisher._is_alive()
    assert publisher._connection.params.url == "amqp://guest:guest@rabbitmq:5672/"
    assert publisher._channel.exchange_declares[0]["exchange"] == "dlx"
    assert publisher._channel.exchange_declares[1]["exchange"] == "events"

    publisher.publish(
        routing_key="matching.completed",
        event_type="matching.completed",
        payload={"run_id": "run-1"},
        request_id="req-1",
    )
    assert publisher._channel.published
    envelope = json.loads(publisher._channel.published[0]["body"])
    assert envelope["event_type"] == "matching.completed"
    assert envelope["request_id"] == "req-1"
    assert envelope["payload"] == {"run_id": "run-1"}

    publisher.close()
    assert publisher._connection is None
    assert publisher._channel is None


def test_event_publisher_reconnects_and_safe_close_handles_errors(monkeypatch):
    monkeypatch.setattr(
        "matching.services.event_publisher.URLParameters",
        FakeParams,
    )

    class BrokenConnection(FakeConnection):
        def close(self):
            raise RuntimeError("boom")

    monkeypatch.setattr(
        "matching.services.event_publisher.BlockingConnection",
        BrokenConnection,
    )

    publisher = EventPublisher("amqp://guest:guest@rabbitmq:5672/", "events", "dlx")
    publisher.publish(
        routing_key="matching.completed",
        event_type="matching.completed",
        payload={"run_id": "run-2"},
    )

    assert publisher._is_alive()
    publisher._safe_close()
    assert publisher._connection is None
    assert publisher._channel is None