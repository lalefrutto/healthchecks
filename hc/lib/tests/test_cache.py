from __future__ import annotations

import time
from typing import Any
from unittest import TestCase
from unittest.mock import Mock, patch

import redis

from hc.lib.cache import CacheManager


class FakeRedis:
    """Минимальная in-memory замена redis.Redis для тестов CacheManager."""

    def __init__(self) -> None:
        self.store: dict[str, tuple[str, float | None]] = {}

    def _alive(self, key: str) -> bool:
        if key not in self.store:
            return False
        _, expires = self.store[key]
        if expires is not None and expires <= time.monotonic():
            del self.store[key]
            return False
        return True

    def get(self, key: str) -> str | None:
        return self.store[key][0] if self._alive(key) else None

    def set(self, key: str, value: str, ex: int | None = None) -> bool:
        self.store[key] = (value, time.monotonic() + ex if ex else None)
        return True

    def exists(self, key: str) -> int:
        return int(self._alive(key))

    def delete(self, key: str) -> int:
        return int(self.store.pop(key, None) is not None)

    def ttl(self, key: str) -> int:
        if not self._alive(key):
            return -2
        _, expires = self.store[key]
        return -1 if expires is None else round(expires - time.monotonic())

    def ping(self) -> bool:
        return True


class CacheManagerTestCase(TestCase):
    def setUp(self) -> None:
        self.fake = FakeRedis()
        self.cache = CacheManager(self.fake, prefix="test", default_ttl=100)  # type: ignore[arg-type]

    def test_set_get_roundtrip(self) -> None:
        self.cache.set("k", {"a": 1, "b": [1, 2]})
        self.assertEqual(self.cache.get("k"), {"a": 1, "b": [1, 2]})
        # ключ хранится с префиксом
        self.assertIn("test:k", self.fake.store)

    def test_get_returns_default_on_miss(self) -> None:
        self.assertIsNone(self.cache.get("missing"))
        self.assertEqual(self.cache.get("missing", 42), 42)

    def test_exists_and_delete(self) -> None:
        self.assertFalse(self.cache.exists("k"))
        self.cache.set("k", "v")
        self.assertTrue(self.cache.exists("k"))
        self.assertTrue(self.cache.delete("k"))
        self.assertFalse(self.cache.exists("k"))

    def test_ttl(self) -> None:
        self.cache.set("k", "v", ttl=60)
        self.assertLessEqual(self.cache.ttl("k"), 60)
        self.assertGreater(self.cache.ttl("k"), 55)
        self.assertIsNone(self.cache.ttl("missing"))

    def test_default_ttl_is_used(self) -> None:
        self.cache.set("k", "v")
        self.assertEqual(self.cache.ttl("k"), 100)

    def test_ttl_zero_means_no_expiry(self) -> None:
        self.cache.set("k", "v", ttl=0)
        self.assertEqual(self.cache.ttl("k"), -1)

    def test_expired_key_is_a_miss(self) -> None:
        self.fake.store["test:k"] = ('"v"', time.monotonic() - 1)
        self.assertIsNone(self.cache.get("k"))
        self.assertFalse(self.cache.exists("k"))

    def test_get_or_set_calls_producer_once(self) -> None:
        producer = Mock(return_value={"x": 1})
        self.assertEqual(self.cache.get_or_set("k", producer, ttl=30), {"x": 1})
        self.assertEqual(self.cache.get_or_set("k", producer, ttl=30), {"x": 1})
        producer.assert_called_once()

    def test_non_json_value_is_dropped(self) -> None:
        self.fake.store["test:k"] = ("not json", None)
        self.assertIsNone(self.cache.get("k"))
        self.assertNotIn("test:k", self.fake.store)

    def test_redis_errors_are_cache_misses(self) -> None:
        client = Mock()
        client.get.side_effect = redis.ConnectionError("down")
        client.set.side_effect = redis.ConnectionError("down")
        cache = CacheManager(client, prefix="test")
        producer = Mock(return_value="fresh")
        self.assertEqual(cache.get_or_set("k", producer), "fresh")
        producer.assert_called_once()
        self.assertFalse(cache.set("k", "v"))

    def test_disabled_without_client(self) -> None:
        cache = CacheManager(None)
        self.assertFalse(cache.available)
        self.assertIsNone(cache.get("k"))
        self.assertFalse(cache.set("k", "v"))
        self.assertEqual(cache.get_or_set("k", lambda: "v"), "v")

    def test_from_env_builds_url_from_parts(self) -> None:
        env = {
            "REDIS_HOST": "redis",
            "REDIS_PORT": "6380",
            "REDIS_DB": "2",
            "REDIS_PASSWORD": "pw",
        }
        with (
            patch.dict("os.environ", env, clear=True),
            patch("redis.Redis.from_url") as from_url,
        ):
            CacheManager.from_env()
        url: Any = from_url.call_args.args[0]
        self.assertEqual(url, "redis://:pw@redis:6380/2")

    def test_from_env_prefers_redis_url(self) -> None:
        env = {"REDIS_URL": "redis://:pw@host:1/3", "REDIS_HOST": "other"}
        with (
            patch.dict("os.environ", env, clear=True),
            patch("redis.Redis.from_url") as from_url,
        ):
            CacheManager.from_env()
        self.assertEqual(from_url.call_args.args[0], "redis://:pw@host:1/3")

    def test_from_env_without_config_is_disabled(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            self.assertFalse(CacheManager.from_env().available)
