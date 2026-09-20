from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from unittest import TestCase
from unittest.mock import Mock, patch

from pymongo.errors import PyMongoError

from hc.lib.mongo import EventLog


class FakeCursor:
    def __init__(self, docs: list[dict[str, Any]]) -> None:
        self.docs = docs

    def sort(self, key: str, direction: int) -> FakeCursor:
        # _seq — порядок вставки, чтобы одинаковые ts сортировались как в MongoDB
        self.docs.sort(key=lambda d: (d[key], d["_seq"]), reverse=direction < 0)
        return self

    def limit(self, n: int) -> FakeCursor:
        self.docs = self.docs[:n]
        return self

    def __iter__(self) -> Any:
        return iter({k: v for k, v in d.items() if k != "_seq"} for d in self.docs)


class FakeCollection:
    """Минимальная in-memory замена pymongo Collection для тестов EventLog."""

    def __init__(self) -> None:
        self.docs: list[dict[str, Any]] = []
        self.indexes: list[Any] = []

    def create_index(self, keys: Any, **kwargs: Any) -> str:
        self.indexes.append((keys, kwargs))
        return "idx"

    def insert_one(self, doc: dict[str, Any]) -> None:
        self.docs.append({**doc, "_seq": len(self.docs)})

    def find(self, query: dict[str, Any], projection: dict[str, Any]) -> FakeCursor:
        docs = [
            dict(d) for d in self.docs if all(d.get(k) == v for k, v in query.items())
        ]
        return FakeCursor(docs)


class EventLogTestCase(TestCase):
    def setUp(self) -> None:
        self.col = FakeCollection()
        self.log = EventLog(self.col)  # type: ignore[arg-type]

    def test_record_and_recent(self) -> None:
        self.assertTrue(self.log.record("enqueued", "t1", task="hc.mq.weather"))
        self.assertTrue(self.log.record("succeeded", "t1", result={"x": 1}))
        self.assertTrue(self.log.record("enqueued", "t2"))

        events = self.log.recent()
        self.assertEqual(
            [e["event"] for e in events], ["enqueued", "succeeded", "enqueued"]
        )
        self.assertEqual(events[0]["task_id"], "t2")
        # ts сериализован в ISO-строку для JSON
        self.assertIsInstance(events[0]["ts"], str)
        self.assertTrue(events[0]["ts"].endswith("+00:00"))

    def test_recent_filters_by_task_id_and_limit(self) -> None:
        for i in range(5):
            self.log.record("started", f"t{i % 2}", n=i)
        self.assertEqual(len(self.log.recent(task_id="t0")), 3)
        self.assertEqual(len(self.log.recent(limit=2)), 2)

    def test_indexes_are_created_once(self) -> None:
        self.log.record("a", "t1")
        self.log.record("b", "t1")
        self.assertEqual(len(self.col.indexes), 3)
        ttl = [kw for keys, kw in self.col.indexes if kw.get("name") == "ts_ttl"]
        self.assertEqual(len(ttl), 1)
        self.assertGreater(ttl[0]["expireAfterSeconds"], 0)

    def test_mongo_errors_are_swallowed(self) -> None:
        col = Mock()
        col.insert_one.side_effect = PyMongoError("down")
        col.find.side_effect = PyMongoError("down")
        log = EventLog(col)
        self.assertFalse(log.record("a", "t1"))
        self.assertEqual(log.recent(), [])

    def test_disabled_without_collection(self) -> None:
        log = EventLog(None)
        self.assertFalse(log.available)
        self.assertFalse(log.record("a", "t1"))
        self.assertEqual(log.recent(), [])

    def test_from_env_without_url_is_disabled(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            self.assertFalse(EventLog.from_env().available)

    def test_from_env_uses_url_and_db(self) -> None:
        env = {"MONGODB_URL": "mongodb://u:p@h:1/db?authSource=db", "MONGODB_DB": "db"}
        with (
            patch.dict("os.environ", env, clear=True),
            patch("hc.lib.mongo.MongoClient") as mc,
        ):
            log = EventLog.from_env()
        self.assertTrue(log.available)
        self.assertEqual(mc.call_args.args[0], env["MONGODB_URL"])
        mc.return_value.__getitem__.assert_called_once_with("db")

    def test_ts_is_utc_datetime(self) -> None:
        self.log.record("a", "t1")
        ts = self.col.docs[0]["ts"]
        self.assertIsInstance(ts, datetime)
        self.assertEqual(ts.tzinfo, UTC)
