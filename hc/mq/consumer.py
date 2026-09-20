"""Consumer: читает задачи из durable-очереди, выполняет и пишет результат в JSON.

    python -m hc.mq.consumer api-results
    python -m hc.mq.consumer api-results --routing-key api-tasks --output-dir results

Имя очереди передаётся через CLI. Очередь объявляется durable и привязывается
к exchange healthchecks.tasks по routing key. Сообщение подтверждается (ack)
только после того, как результат записан на диск; при ошибке задачи сообщение
отклоняется без requeue (nack), чтобы «битое» сообщение не крутилось вечно.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from hc.mq.common import DEFAULT_ROUTING_KEY, EXCHANGE, connect, declare_exchange
from hc.mq.tasks import run_task

logger = logging.getLogger(__name__)


def write_result(
    output_dir: Path,
    queue: str,
    message: dict[str, Any],
    result: dict[str, Any] | None,
    error: str | None,
) -> Path:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    path = (
        output_dir
        / queue
        / f"{stamp}-{message.get('task', 'unknown')}-{message.get('id', 'noid')}.json"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "message": message,
        "queue": queue,
        "processed_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "status": "ok" if error is None else "error",
        "result": result,
        "error": error,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("queue", help="имя очереди (будет создана durable)")
    parser.add_argument(
        "--routing-key",
        default=DEFAULT_ROUTING_KEY,
        help=f"ключ привязки к exchange, по умолчанию {DEFAULT_ROUTING_KEY}",
    )
    parser.add_argument(
        "--output-dir",
        default="results",
        type=Path,
        help="куда складывать JSON с результатами (по умолчанию ./results)",
    )
    opts = parser.parse_args(argv)

    connection = connect()
    channel = connection.channel()
    declare_exchange(channel)
    # durable=True — очередь (и persistent-сообщения в ней) переживут рестарт брокера
    channel.queue_declare(queue=opts.queue, durable=True)
    channel.queue_bind(
        queue=opts.queue, exchange=EXCHANGE, routing_key=opts.routing_key
    )
    # Не брать следующее сообщение, пока не подтверждено текущее
    channel.basic_qos(prefetch_count=1)

    def callback(ch: Any, method: Any, properties: Any, body: bytes) -> None:
        try:
            message = json.loads(body)
        except ValueError:
            print(f"[!] недопустимое сообщение (не JSON), отбрасываем: {body[:80]!r}")
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
            return

        print(
            f"[>] {message.get('task')} id={message.get('id')} ...", end=" ", flush=True
        )
        result: dict[str, Any] | None = None
        error: str | None = None
        try:
            result = run_task(message["task"], message.get("args"))
        except Exception as exc:
            # Любая ошибка API-вызова — тоже результат: фиксируем в файл и nack'аем
            logger.exception("Task %s failed", message.get("task"))
            error = f"{type(exc).__name__}: {exc}"

        path = write_result(opts.output_dir, opts.queue, message, result, error)
        if error is None:
            ch.basic_ack(delivery_tag=method.delivery_tag)
            print(f"ok -> {path}")
        else:
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
            print(f"ERROR ({error}) -> {path}")

    channel.basic_consume(
        queue=opts.queue, on_message_callback=callback, auto_ack=False
    )
    print(
        f"[*] waiting for messages in '{opts.queue}' (exchange={EXCHANGE}, "
        f"routing_key={opts.routing_key}). Ctrl+C to exit"
    )
    try:
        channel.start_consuming()
    except KeyboardInterrupt:
        channel.stop_consuming()
    finally:
        connection.close()
        sys.exit(0)


if __name__ == "__main__":
    main()
