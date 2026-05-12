import json
from unittest.mock import MagicMock

import pytest
import json
from unittest.mock import MagicMock

from profile.services.event_publisher import EventPublisher
from profile.services.storage import FileStorage


class FakeS3Client:

    def __init__(self, fail_head=False):
        self.fail_head = fail_head
        self.head_calls = []
        self.created_buckets = []
        self.put_objects = []
        self.get_objects = []

    def head_bucket(self, Bucket):
        self.head_calls.append(Bucket)
        if self.fail_head:
            raise RuntimeError("missing bucket")

    def create_bucket(self, Bucket):
        self.created_buckets.append(Bucket)

    def put_object(self, **kwargs):
        self.put_objects.append(kwargs)

    def get_object(self, **kwargs):
        self.get_objects.append(kwargs)
        return {"Body": MagicMock(read=lambda: b"downloaded-bytes")}


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
        self._channel = FakeChannel()
        self.closed = False

    def channel(self):
        return self._channel

    def close(self):
        self.closed = True
        self.is_open = False


def test_file_storage_creates_bucket_uploads_and_downloads(monkeypatch):
    fake_client = FakeS3Client(fail_head=True)
    monkeypatch.setattr(
        "profile.services.storage.boto3.client",
        lambda *args, **kwargs: fake_client,
    )
    monkeypatch.setattr(
        "profile.services.storage.uuid.uuid4",
        lambda: __import__("uuid").UUID("550e8400-e29b-41d4-a716-446655440000"),
    )

    storage = FileStorage(
        endpoint="minio:9000",
        access_key="minio",
        secret_key="secret",
        bucket="resumes",
        use_ssl=True,
    )

    assert fake_client.created_buckets == ["resumes"]
    assert storage._client is fake_client

    file_key = storage.upload(b"content", "pdf")
    assert file_key == "550e8400-e29b-41d4-a716-446655440000.pdf"
    assert fake_client.put_objects[0]["Bucket"] == "resumes"

    data = storage.download(file_key)
    assert data == b"downloaded-bytes"
    assert fake_client.get_objects[0]["Key"] == file_key


def test_file_storage_reuses_existing_bucket(monkeypatch):
    fake_client = FakeS3Client(fail_head=False)
    monkeypatch.setattr(
        "profile.services.storage.boto3.client",
        lambda *args, **kwargs: fake_client,
    )

    FileStorage(
        endpoint="minio:9000",
        access_key="minio",
        secret_key="secret",
        bucket="resumes",
        use_ssl=False,
    )

    assert fake_client.created_buckets == []
    assert fake_client.head_calls == ["resumes"]


def test_event_publisher_connect_publish_and_close(monkeypatch):
    monkeypatch.setattr("profile.services.event_publisher.URLParameters", FakeParams)
    monkeypatch.setattr(
        "profile.services.event_publisher.BlockingConnection",
        FakeConnection,
    )

    publisher = EventPublisher("amqp://guest:guest@rabbitmq:5672/", "events", "dlx")
    publisher.connect()

    assert publisher._is_alive()
    assert publisher._channel.exchange_declares[0]["exchange"] == "dlx"

    publisher.publish(
        routing_key="candidate.profile.updated",
        event_type="candidate.profile.updated",
        payload={"candidate_id": "1"},
        request_id="req-1",
    )
    envelope = json.loads(publisher._channel.published[0]["body"])
    assert envelope["producer"] == "profile-service"
    assert envelope["request_id"] == "req-1"

    publisher.close()
    assert publisher._connection is None
    assert publisher._channel is None


def test_event_publisher_safe_close_ignores_close_errors(monkeypatch):
    monkeypatch.setattr("profile.services.event_publisher.URLParameters", FakeParams)

    class BrokenConnection(FakeConnection):

        def close(self):
            raise RuntimeError("boom")

    monkeypatch.setattr(
        "profile.services.event_publisher.BlockingConnection",
        BrokenConnection,
    )

    publisher = EventPublisher("amqp://guest:guest@rabbitmq:5672/", "events", "dlx")
    publisher.publish(
        routing_key="candidate.profile.updated",
        event_type="candidate.profile.updated",
        payload={"candidate_id": "1"},
    )

    publisher._safe_close()
    assert publisher._connection is None
    assert publisher._channel is None
