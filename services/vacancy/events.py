from __future__ import annotations

import importlib
import json
import logging
import os
from datetime import UTC, datetime
from http import HTTPStatus
from uuid import uuid4

from libs import make_http_exception


logger = logging.getLogger(__name__)


class VacancyEventPublisher:
    def __init__(self) -> None:
        self._exchange = os.getenv("RABBITMQ_EVENTS_EXCHANGE", "ara.events")
        self._producer_name = os.getenv("VACANCY_EVENT_PRODUCER", "vacancy-service")
        self._required = os.getenv("VACANCY_EVENTS_REQUIRED", "false").lower() in {"1", "true", "yes", "on"}

        host = os.getenv("RABBITMQ_HOST", "rabbitmq")
        port = int(os.getenv("RABBITMQ_PORT", "5672"))
        user = os.getenv("RABBITMQ_DEFAULT_USER", "guest")
        password = os.getenv("RABBITMQ_DEFAULT_PASS", "guest")

        self._connection_params = {
            "host": host,
            "port": port,
            "credentials": (user, password),
        }

    @staticmethod
    def _load_pika() -> object:
        try:
            return importlib.import_module("pika")
        except ModuleNotFoundError as exc:
            raise make_http_exception(
                status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
                code="missing_dependency",
                message="RabbitMQ dependency is not installed",
                details={"dependency": str(exc.name)},
            ) from exc

    def publish(self, event_type: str, payload: dict, request_id: str | None = None) -> None:
        event = {
            "event_id": uuid4().hex,
            "event_type": event_type,
            "event_version": 1,
            "occurred_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "producer": self._producer_name,
            "payload": payload,
        }
        if request_id:
            event["request_id"] = request_id

        try:
            self._publish_to_rabbit(event_type=event_type, event=event)
        except Exception as exc:
            if self._required:
                raise make_http_exception(
                    status_code=HTTPStatus.SERVICE_UNAVAILABLE,
                    code="event_publish_failed",
                    message="Failed to publish vacancy event",
                    details={"event_type": event_type, "exception": exc.__class__.__name__},
                ) from exc

            logger.warning("Cannot publish event %s: %s", event_type, exc)

    def _publish_to_rabbit(self, event_type: str, event: dict) -> None:
        pika = self._load_pika()

        credentials = pika.PlainCredentials(
            self._connection_params["credentials"][0],
            self._connection_params["credentials"][1],
        )
        params = pika.ConnectionParameters(
            host=self._connection_params["host"],
            port=self._connection_params["port"],
            credentials=credentials,
        )

        connection = pika.BlockingConnection(params)
        try:
            channel = connection.channel()
            channel.exchange_declare(exchange=self._exchange, exchange_type="topic", durable=True)
            channel.basic_publish(
                exchange=self._exchange,
                routing_key=event_type,
                body=json.dumps(event).encode("utf-8"),
                properties=pika.BasicProperties(content_type="application/json", delivery_mode=2),
            )
        finally:
            connection.close()


publisher: VacancyEventPublisher | None = None


def get_event_publisher() -> VacancyEventPublisher:
    global publisher
    if publisher is None:
        publisher = VacancyEventPublisher()
    return publisher