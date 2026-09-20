"""Producer: публикует задачи (вызовы внешних API) в durable direct exchange.

    python -m hc.mq.producer cat_fact
    python -m hc.mq.producer weather --latitude 55.79 --longitude 49.11 --count 3
    python -m hc.mq.producer cat_fact --routing-key other-queue

Сообщение — JSON {"id", "task", "args", "created_at"}, публикуется с
delivery_mode=persistent, так что при durable-очереди переживёт рестарт брокера.
"""

from __future__ import annotations

import argparse
import json
import uuid
from datetime import UTC, datetime
from typing import Any

import pika

from hc.mq.common import DEFAULT_ROUTING_KEY, EXCHANGE, connect, declare_exchange
from hc.mq.tasks import TASKS


def build_message(task: str, args: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(uuid.uuid4()),
        "task": task,
        "args": args,
        "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
    }


def publish(channel: Any, routing_key: str, message: dict[str, Any]) -> None:
    channel.basic_publish(
        exchange=EXCHANGE,
        routing_key=routing_key,
        body=json.dumps(message).encode("utf-8"),
        properties=pika.BasicProperties(
            content_type="application/json",
            delivery_mode=pika.DeliveryMode.Persistent,
            message_id=message["id"],
            timestamp=int(datetime.now(UTC).timestamp()),
        ),
    )


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("task", choices=sorted(TASKS), help="какую задачу опубликовать")
    parser.add_argument(
        "--routing-key",
        default=DEFAULT_ROUTING_KEY,
        help=f"routing key (ключ привязки очереди consumer'а), по умолчанию {DEFAULT_ROUTING_KEY}",
    )
    parser.add_argument(
        "--count", type=int, default=1, help="сколько сообщений отправить"
    )
    parser.add_argument("--latitude", type=float, help="для задачи weather")
    parser.add_argument("--longitude", type=float, help="для задачи weather")
    opts = parser.parse_args(argv)

    args: dict[str, Any] = {}
    if opts.task == "weather":
        if opts.latitude is not None:
            args["latitude"] = opts.latitude
        if opts.longitude is not None:
            args["longitude"] = opts.longitude

    connection = connect()
    try:
        channel = connection.channel()
        declare_exchange(channel)
        # Подтверждения публикации: брокер гарантирует, что принял сообщение
        channel.confirm_delivery()
        for _ in range(opts.count):
            message = build_message(opts.task, args)
            publish(channel, opts.routing_key, message)
            print(
                f"[x] sent {message['task']} id={message['id']} -> {EXCHANGE}/{opts.routing_key}"
            )
    finally:
        connection.close()


if __name__ == "__main__":
    main()
