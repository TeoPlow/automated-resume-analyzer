import json
import uuid
from datetime import datetime, timezone

from pika import BlockingConnection, URLParameters, BasicProperties
from pika.adapters.blocking_connection import BlockingChannel

from common.logger import setup_logger

logger = setup_logger("profile.events")


class EventPublisher:
    """Издатель событий в RabbitMQ (topic exchange)."""

    def __init__(self, rabbitmq_url: str, exchange: str, dlx: str) -> None:
        self._rabbitmq_url = rabbitmq_url
        self._exchange = exchange
        self._dlx = dlx
        self._connection: BlockingConnection | None = None
        self._channel: BlockingChannel | None = None

    def _is_alive(self) -> bool:
        """Проверить, что соединение и канал живы."""
        return (
            self._connection is not None
            and self._connection.is_open
            and self._channel is not None
            and self._channel.is_open
        )

    def connect(self) -> None:
        """Установить соединение с RabbitMQ и объявить exchange."""
        self._safe_close()
        params = URLParameters(self._rabbitmq_url)
        params.heartbeat = 600
        params.blocked_connection_timeout = 300
        self._connection = BlockingConnection(params)
        self._channel = self._connection.channel()
        self._channel.exchange_declare(
            exchange=self._dlx,
            exchange_type="fanout",
            durable=True,
        )
        self._channel.exchange_declare(
            exchange=self._exchange,
            exchange_type="topic",
            durable=True,
        )
        logger.info("Подключение к RabbitMQ установлено")

    def publish(
        self,
        routing_key: str,
        event_type: str,
        payload: dict,
        request_id: str | None = None,
    ) -> None:
        """Опубликовать событие в exchange."""
        if not self._is_alive():
            logger.info("Переподключение к RabbitMQ (соединение неактивно)")
            self.connect()
        assert self._channel is not None
        envelope = {
            "event_id": str(uuid.uuid4()),
            "event_type": event_type,
            "event_version": 1,
            "occurred_at": datetime.now(timezone.utc).isoformat(),
            "producer": "profile-service",
            "request_id": request_id or "",
            "payload": payload,
        }
        self._channel.basic_publish(
            exchange=self._exchange,
            routing_key=routing_key,
            body=json.dumps(envelope, ensure_ascii=False),
            properties=BasicProperties(
                content_type="application/json",
                delivery_mode=2,
            ),
        )
        logger.info("Событие опубликовано: %s", event_type)

    def _safe_close(self) -> None:
        """Безопасно закрыть соединение (игнорируя ошибки)."""
        try:
            if self._connection and self._connection.is_open:
                self._connection.close()
        except Exception:
            pass
        self._connection = None
        self._channel = None

    def close(self) -> None:
        """Закрыть соединение с RabbitMQ."""
        self._safe_close()
        logger.info("Соединение с RabbitMQ закрыто")
