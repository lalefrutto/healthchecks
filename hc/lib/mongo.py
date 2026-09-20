"""Журнал событий задач в MongoDB (Задание 5, Часть 2).

Каждое событие жизненного цикла Celery-задачи (поставлена, запущена,
выполнена, упала) пишется документом в коллекцию task_events — это данные с
переменной структурой (аргументы, результат, трейсбек), которые неудобно
класть в реляционную схему Postgres, а MongoDB для такого журнала подходит
хорошо. Читается через GET /api/v3/tasks/history/.

Подключение — из MONGODB_URL (его собирает чарт из ConfigMap + Secret).
Журнал — вспомогательный: если MongoDB недоступна, событие теряется с
предупреждением в логе, основной сценарий (постановка/выполнение задачи)
не ломается.
"""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime
from typing import Any

from pymongo import ASCENDING, DESCENDING, MongoClient
from pymongo.collection import Collection
from pymongo.errors import PyMongoError

logger = logging.getLogger(__name__)

COLLECTION = "task_events"
# Хранить события столько дней (TTL-индекс MongoDB чистит старые сам)
RETENTION_DAYS = int(os.getenv("MONGODB_EVENTS_RETENTION_DAYS", "30"))

_default: EventLog | None = None


class EventLog:
    def __init__(self, collection: Collection[dict[str, Any]] | None) -> None:
        self._col = collection
        self._indexes_ready = False

    @classmethod
    def from_env(cls) -> EventLog:
        url = os.getenv("MONGODB_URL")
        if not url:
            logger.warning("MONGODB_URL not set, task event log is disabled")
            return cls(None)
        db_name = os.getenv("MONGODB_DB", "healthchecks")
        client: MongoClient[dict[str, Any]] = MongoClient(
            url, serverSelectionTimeoutMS=2000, connectTimeoutMS=2000
        )
        return cls(client[db_name][COLLECTION])

    @property
    def available(self) -> bool:
        return self._col is not None

    def _ensure_indexes(self) -> None:
        if self._indexes_ready or self._col is None:
            return
        self._col.create_index([("ts", DESCENDING)])
        self._col.create_index([("task_id", ASCENDING), ("ts", DESCENDING)])
        self._col.create_index(
            "ts", expireAfterSeconds=RETENTION_DAYS * 86400, name="ts_ttl"
        )
        self._indexes_ready = True

    def record(self, event: str, task_id: str, **fields: Any) -> bool:
        """Записать событие. Возвращает False, если MongoDB недоступна."""
        if self._col is None:
            return False
        doc = {"event": event, "task_id": task_id, "ts": datetime.now(UTC), **fields}
        try:
            self._ensure_indexes()
            self._col.insert_one(doc)
            return True
        except PyMongoError as exc:
            logger.warning("MongoDB insert failed, event %s dropped: %s", event, exc)
            return False

    def recent(
        self, limit: int = 50, task_id: str | None = None
    ) -> list[dict[str, Any]]:
        """Последние события (новые первыми), опционально по одной задаче."""
        if self._col is None:
            return []
        query: dict[str, Any] = {"task_id": task_id} if task_id else {}
        try:
            cursor = (
                self._col.find(query, {"_id": False})
                .sort("ts", DESCENDING)
                .limit(limit)
            )
            docs = list(cursor)
        except PyMongoError as exc:
            logger.warning("MongoDB query failed: %s", exc)
            return []
        for doc in docs:
            ts = doc.get("ts")
            if isinstance(ts, datetime):
                doc["ts"] = ts.replace(tzinfo=UTC).isoformat(timespec="milliseconds")
        return docs


def get_event_log() -> EventLog:
    """Общий экземпляр на процесс (MongoClient держит пул соединений сам)."""
    global _default
    if _default is None:
        _default = EventLog.from_env()
    return _default
