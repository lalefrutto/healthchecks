"""Общее для producer и consumer: подключение и имена AMQP-сущностей."""

from __future__ import annotations

import os

import pika

# Durable direct exchange: сообщения маршрутизируются по точному совпадению
# routing key с ключом привязки очереди.
EXCHANGE = "healthchecks.tasks"
EXCHANGE_TYPE = "direct"
DEFAULT_ROUTING_KEY = "api-tasks"


def amqp_url() -> str:
    url = os.environ.get("RABBITMQ_URL")
    if not url:
        raise SystemExit(
            "RABBITMQ_URL не задан. Пример: amqp://user:password@127.0.0.1:5672/%2F "
            "(локально: source scripts/rabbitmq-env.sh)"
        )
    return url


def connect() -> pika.BlockingConnection:
    params = pika.URLParameters(amqp_url())
    params.heartbeat = 60
    params.blocked_connection_timeout = 30
    return pika.BlockingConnection(params)


def declare_exchange(
    channel: pika.adapters.blocking_connection.BlockingChannel,
) -> None:
    # durable=True — exchange переживёт перезапуск брокера
    channel.exchange_declare(EXCHANGE, exchange_type=EXCHANGE_TYPE, durable=True)
