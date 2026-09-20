from __future__ import annotations

from unittest.mock import Mock, patch

from hc.test import BaseTestCase


class RunTaskTestCase(BaseTestCase):
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


class TaskResultTestCase(BaseTestCase):
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
