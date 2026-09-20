from __future__ import annotations

from unittest.mock import Mock, patch

from django_celery_results.models import TaskResult

from hc.lib.cache import CacheManager
from hc.lib.mongo import EventLog
from hc.lib.tests.test_cache import FakeRedis
from hc.lib.tests.test_mongo import FakeCollection
from hc.test import BaseTestCase


class FakeCacheMixin:
    """Подменяет CacheManager и EventLog в views на in-memory, чтобы тесты
    не ходили в Redis и MongoDB."""

    def setUp(self) -> None:
        super().setUp()  # type: ignore[misc]
        self.cache = CacheManager(FakeRedis(), prefix="test")  # type: ignore[arg-type]
        self.events = FakeCollection()
        self.event_log = EventLog(self.events)  # type: ignore[arg-type]
        for target, value in (
            ("hc.mq.views.get_cache", self.cache),
            ("hc.mq.views.get_event_log", self.event_log),
        ):
            patcher = patch(target, return_value=value)
            patcher.start()
            self.addCleanup(patcher.stop)  # type: ignore[attr-defined]


class RunTaskTestCase(FakeCacheMixin, BaseTestCase):
    url = "/api/v3/tasks/weather/"

    @patch("hc.mq.views.celery_tasks.weather.apply_async")
    def test_it_works(self, mock_apply: Mock) -> None:
        mock_apply.return_value = Mock(id="abc-123", state="PENDING")
        payload = {"api_key": "X" * 32, "latitude": 55.79, "longitude": 49.11}
        r = self.csrf_client.post(self.url, payload, content_type="application/json")
        self.assertEqual(r.status_code, 202)

        doc = r.json()
        self.assertEqual(doc["task_id"], "abc-123")
        self.assertEqual(doc["task"], "hc.mq.weather")
        self.assertEqual(doc["state"], "PENDING")
        # api_key не должен утекать в аргументы задачи
        mock_apply.assert_called_once_with(
            kwargs={"latitude": 55.79, "longitude": 49.11}
        )
        # событие "enqueued" ушло в журнал MongoDB
        self.assertEqual(len(self.events.docs), 1)
        ev = self.events.docs[0]
        self.assertEqual(ev["event"], "enqueued")
        self.assertEqual(ev["task_id"], "abc-123")
        self.assertEqual(ev["task"], "hc.mq.weather")
        self.assertEqual(ev["kwargs"], {"latitude": 55.79, "longitude": 49.11})
        self.assertEqual(ev["project"], str(self.project.code))

    @patch("hc.mq.views.celery_tasks.cat_fact.apply_async")
    def test_it_accepts_api_key_header(self, mock_apply: Mock) -> None:
        mock_apply.return_value = Mock(id="abc-123", state="PENDING")
        r = self.csrf_client.post(
            "/api/v3/tasks/cat_fact/",
            {},
            content_type="application/json",
            HTTP_X_API_KEY="X" * 32,
        )
        self.assertEqual(r.status_code, 202)
        mock_apply.assert_called_once_with(kwargs={})

    def test_it_handles_unknown_task(self) -> None:
        r = self.csrf_client.post(
            "/api/v3/tasks/nope/",
            {},
            content_type="application/json",
            HTTP_X_API_KEY="X" * 32,
        )
        self.assertEqual(r.status_code, 404)
        self.assertIn("unknown task", r.json()["error"])

    def test_it_requires_api_key(self) -> None:
        r = self.csrf_client.post(self.url, {}, content_type="application/json")
        self.assertEqual(r.status_code, 401)

    def test_it_rejects_get(self) -> None:
        r = self.client.get(self.url, HTTP_X_API_KEY="X" * 32)
        self.assertEqual(r.status_code, 405)


class TaskResultTestCase(FakeCacheMixin, BaseTestCase):
    url = "/api/v3/tasks/result/abc-123/"

    @patch("hc.mq.views.AsyncResult")
    def test_it_returns_pending(self, mock_result: Mock) -> None:
        mock_result.return_value = Mock(
            state="PENDING",
            ready=lambda: False,
            successful=lambda: False,
            failed=lambda: False,
        )
        r = self.client.get(self.url, HTTP_X_API_KEY="X" * 32)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(
            r.json(), {"task_id": "abc-123", "state": "PENDING", "ready": False}
        )

    @patch("hc.mq.views.AsyncResult")
    def test_it_returns_result(self, mock_result: Mock) -> None:
        mock_result.return_value = Mock(
            state="SUCCESS",
            ready=lambda: True,
            successful=lambda: True,
            result={"temperature_c": 14.2},
        )
        r = self.client.get(self.url, HTTP_X_API_KEY="X" * 32)
        doc = r.json()
        self.assertEqual(doc["state"], "SUCCESS")
        self.assertTrue(doc["ready"])
        self.assertEqual(doc["result"], {"temperature_c": 14.2})

    @patch("hc.mq.views.AsyncResult")
    def test_it_returns_error(self, mock_result: Mock) -> None:
        mock_result.return_value = Mock(
            state="FAILURE",
            ready=lambda: True,
            successful=lambda: False,
            failed=lambda: True,
            result=RuntimeError("boom"),
        )
        r = self.client.get(self.url, HTTP_X_API_KEY="X" * 32)
        doc = r.json()
        self.assertEqual(doc["state"], "FAILURE")
        self.assertEqual(doc["error"], "boom")

    def test_it_accepts_readonly_key(self) -> None:
        self.project.api_key_readonly = "R" * 32
        self.project.save()
        with patch("hc.mq.views.AsyncResult") as mock_result:
            mock_result.return_value = Mock(
                state="PENDING",
                ready=lambda: False,
                successful=lambda: False,
                failed=lambda: False,
            )
            r = self.client.get(self.url, HTTP_X_API_KEY="R" * 32)
        self.assertEqual(r.status_code, 200)

    def test_it_requires_api_key(self) -> None:
        r = self.client.get(self.url)
        self.assertEqual(r.status_code, 401)


class TaskResultCacheTestCase(FakeCacheMixin, BaseTestCase):
    url = "/api/v3/tasks/result/abc-123/"

    @patch("hc.mq.views.AsyncResult")
    def test_ready_result_is_cached(self, mock_result: Mock) -> None:
        mock_result.return_value = Mock(
            state="SUCCESS",
            ready=lambda: True,
            successful=lambda: True,
            result={"x": 1},
        )
        r = self.client.get(self.url, HTTP_X_API_KEY="X" * 32)
        self.assertNotIn("cached", r.json())
        self.assertTrue(self.cache.exists("task_result:abc-123"))

        # второй запрос — из кэша, AsyncResult больше не спрашиваем
        mock_result.reset_mock()
        r = self.client.get(self.url, HTTP_X_API_KEY="X" * 32)
        self.assertTrue(r.json()["cached"])
        self.assertEqual(r.json()["result"], {"x": 1})
        mock_result.assert_not_called()

    @patch("hc.mq.views.AsyncResult")
    def test_pending_result_is_not_cached(self, mock_result: Mock) -> None:
        mock_result.return_value = Mock(
            state="PENDING",
            ready=lambda: False,
            successful=lambda: False,
            failed=lambda: False,
        )
        self.client.get(self.url, HTTP_X_API_KEY="X" * 32)
        self.assertFalse(self.cache.exists("task_result:abc-123"))


class TaskStatsTestCase(FakeCacheMixin, BaseTestCase):
    url = "/api/v3/tasks/stats/"

    def setUp(self) -> None:
        super().setUp()
        TaskResult.objects.create(
            task_id="1", task_name="hc.mq.weather", status="SUCCESS"
        )
        TaskResult.objects.create(
            task_id="2", task_name="hc.mq.weather", status="SUCCESS"
        )
        TaskResult.objects.create(
            task_id="3", task_name="hc.mq.cat_fact", status="FAILURE"
        )

    def test_it_aggregates_and_caches(self) -> None:
        r = self.client.get(self.url, HTTP_X_API_KEY="X" * 32)
        self.assertEqual(r.status_code, 200)
        doc = r.json()
        self.assertEqual(doc["total"], 3)
        self.assertEqual(doc["tasks"]["hc.mq.weather"], {"SUCCESS": 2})
        self.assertEqual(doc["tasks"]["hc.mq.cat_fact"], {"FAILURE": 1})
        self.assertNotIn("cached", doc)

        # новая строка в БД не видна, пока жив кэш (cache-aside с TTL)
        TaskResult.objects.create(
            task_id="4", task_name="hc.mq.cat_fact", status="SUCCESS"
        )
        with patch("hc.mq.views._task_stats") as mock_stats:
            doc = self.client.get(self.url, HTTP_X_API_KEY="X" * 32).json()
        mock_stats.assert_not_called()
        self.assertTrue(doc["cached"])
        self.assertEqual(doc["total"], 3)

        self.cache.delete("task_stats")
        doc = self.client.get(self.url, HTTP_X_API_KEY="X" * 32).json()
        self.assertEqual(doc["total"], 4)

    def test_it_requires_api_key(self) -> None:
        r = self.client.get(self.url)
        self.assertEqual(r.status_code, 401)


class TaskHistoryTestCase(FakeCacheMixin, BaseTestCase):
    url = "/api/v3/tasks/history/"

    def setUp(self) -> None:
        super().setUp()
        self.event_log.record("enqueued", "t1", task="hc.mq.weather")
        self.event_log.record("succeeded", "t1", result={"x": 1})
        self.event_log.record("enqueued", "t2", task="hc.mq.cat_fact")

    def test_it_works(self) -> None:
        r = self.client.get(self.url, HTTP_X_API_KEY="X" * 32)
        self.assertEqual(r.status_code, 200)
        doc = r.json()
        self.assertTrue(doc["available"])
        self.assertEqual([e["task_id"] for e in doc["events"]], ["t2", "t1", "t1"])
        self.assertEqual(doc["events"][1]["result"], {"x": 1})

    def test_it_filters_by_task_id(self) -> None:
        r = self.client.get(self.url + "?task_id=t1", HTTP_X_API_KEY="X" * 32)
        events = r.json()["events"]
        self.assertEqual(len(events), 2)
        self.assertTrue(all(e["task_id"] == "t1" for e in events))

    def test_it_applies_limit(self) -> None:
        r = self.client.get(self.url + "?limit=1", HTTP_X_API_KEY="X" * 32)
        self.assertEqual(len(r.json()["events"]), 1)

    def test_it_validates_limit(self) -> None:
        r = self.client.get(self.url + "?limit=abc", HTTP_X_API_KEY="X" * 32)
        self.assertEqual(r.status_code, 400)

    def test_it_requires_api_key(self) -> None:
        r = self.client.get(self.url)
        self.assertEqual(r.status_code, 401)
