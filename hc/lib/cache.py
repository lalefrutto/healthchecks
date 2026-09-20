"""CacheManager — тонкая обёртка над Redis для кэширования по схеме cache-aside.

Задание 4, Часть 2. Подключение — из переменных окружения, которые чарт
прокидывает в поды (REDIS_URL, либо REDIS_HOST/REDIS_PORT/REDIS_DB/REDIS_PASSWORD).

Cache-aside: код сначала спрашивает кэш; при промахе идёт в источник (внешний
API, SQL) и кладёт результат в кэш с TTL. Кэш — не источник истины, поэтому
при недоступности Redis менеджер ведёт себя как «всегда промах» и пишет
предупреждение в лог, а приложение продолжает работать без кэша.

    cache = CacheManager()                       # или CacheManager.from_env()
    cache.set("k", {"a": 1}, ttl=60)
    cache.get("k")            -> {"a": 1}
    cache.exists("k")         -> True
    cache.ttl("k")            -> 59
    cache.get_or_set("k2", lambda: expensive(), ttl=300)
"""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Callable
from typing import Any, TypeVar

import redis

logger = logging.getLogger(__name__)

T = TypeVar("T")

# Префикс всех ключей приложения, чтобы не пересекаться с другими клиентами Redis
KEY_PREFIX = os.getenv("CACHE_KEY_PREFIX", "hc")
# TTL по умолчанию, если не передан явно
DEFAULT_TTL = int(os.getenv("CACHE_DEFAULT_TTL", "300"))

_default: CacheManager | None = None


class CacheManager:
    def __init__(
        self,
        client: redis.Redis | None = None,
        *,
        prefix: str = KEY_PREFIX,
        default_ttl: int = DEFAULT_TTL,
    ) -> None:
        self._client = client
        self.prefix = prefix
        self.default_ttl = default_ttl
        self._available = client is not None

    # --- подключение -------------------------------------------------------

    @classmethod
    def from_env(cls, **kwargs: Any) -> CacheManager:
        """Клиент по REDIS_URL, либо по REDIS_HOST/REDIS_PORT/REDIS_DB/REDIS_PASSWORD."""
        url = os.getenv("REDIS_URL")
        if not url:
            host = os.getenv("REDIS_HOST")
            if not host:
                logger.warning("REDIS_URL/REDIS_HOST not set, cache is disabled")
                return cls(None, **kwargs)
            password = os.getenv("REDIS_PASSWORD", "")
            auth = f":{password}@" if password else ""
            port = os.getenv("REDIS_PORT", "6379")
            db = os.getenv("REDIS_DB", "0")
            url = f"redis://{auth}{host}:{port}/{db}"

        client = redis.Redis.from_url(
            url,
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
        )
        return cls(client, **kwargs)

    @property
    def available(self) -> bool:
        return self._available

    def _key(self, key: str) -> str:
        return f"{self.prefix}:{key}"

    def _call(self, op: str, *args: Any, **kwargs: Any) -> Any:
        """Вызывает метод клиента; при ошибке Redis возвращает None (промах)."""
        if self._client is None:
            return None
        try:
            return getattr(self._client, op)(*args, **kwargs)
        except redis.RedisError as exc:
            logger.warning("Redis %s failed, treating as cache miss: %s", op, exc)
            return None

    # --- API ---------------------------------------------------------------

    def get(self, key: str, default: Any = None) -> Any:
        raw = self._call("get", self._key(key))
        if raw is None:
            return default
        try:
            return json.loads(raw)
        except ValueError:
            logger.warning("Cache value for %s is not JSON, dropping it", key)
            self.delete(key)
            return default

    def set(self, key: str, value: Any, ttl: int | None = None) -> bool:
        """Кладёт JSON-сериализуемое значение. ttl в секундах; None -> default_ttl,
        0 -> без истечения."""
        if ttl is None:
            ttl = self.default_ttl
        raw = json.dumps(value, ensure_ascii=False)
        ex = ttl if ttl > 0 else None
        return bool(self._call("set", self._key(key), raw, ex=ex))

    def exists(self, key: str) -> bool:
        return bool(self._call("exists", self._key(key)))

    def delete(self, key: str) -> bool:
        return bool(self._call("delete", self._key(key)))

    def ttl(self, key: str) -> int | None:
        """Оставшийся TTL в секундах; None — ключа нет или Redis недоступен;
        -1 — ключ без истечения."""
        v = self._call("ttl", self._key(key))
        if v is None or v == -2:
            return None
        return int(v)

    def get_or_set(
        self, key: str, producer: Callable[[], T], ttl: int | None = None
    ) -> T:
        """Cache-aside: вернуть из кэша, иначе вычислить, сохранить и вернуть."""
        sentinel = object()
        cached = self.get(key, sentinel)
        if cached is not sentinel:
            return cached  # type: ignore[return-value]
        value = producer()
        self.set(key, value, ttl)
        return value

    def ping(self) -> bool:
        return bool(self._call("ping"))


def get_cache() -> CacheManager:
    """Общий экземпляр на процесс (redis-py держит пул соединений сам)."""
    global _default
    if _default is None:
        _default = CacheManager.from_env()
    return _default
