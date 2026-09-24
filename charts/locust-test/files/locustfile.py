"""Нагрузочный тест healthchecks (Задание 7).

Бьёт по реальным эндпоинтам приложения:
  * GET  /api/v3/checks/        — список проверок проекта (API-ключ, SQL + сериализация)
  * GET  /api/v3/checks/<uuid>  — одна проверка
  * POST /ping/<uuid>           — входящий пинг (самый горячий путь healthchecks)
  * GET  /api/v3/tasks/stats/   — агрегат из Задания 4 (кэшируется в Redis)

Запуск (локально, через Ingress + minikube tunnel):
  HC_API_KEY=<rw-ключ проекта> locust -f charts/locust-test/files/locustfile.py --host https://healthchecks.local
Headless-прогон с нарастающей нагрузкой:
  HC_API_KEY=... locust -f charts/locust-test/files/locustfile.py --host https://healthchecks.local \
      --headless -u 100 -r 5 -t 3m --only-summary

Переменные окружения:
  HC_API_KEY   — ключ проекта (Settings -> API access), обязательно
  HC_CHECK     — uuid проверки для пингов; если не задан, создаётся проверка "locust"
"""

from __future__ import annotations

import os
import random

from locust import HttpUser, between, task

API_KEY = os.environ.get("HC_API_KEY", "")
CHECK_UUID = os.environ.get("HC_CHECK", "")


class HealthchecksUser(HttpUser):
    wait_time = between(0.5, 2)

    def on_start(self) -> None:
        if not API_KEY:
            raise RuntimeError("HC_API_KEY не задан")
        self.client.verify = False  # локальный self-signed CA
        self.headers = {"X-Api-Key": API_KEY}
        self.check_uuid = CHECK_UUID
        if not self.check_uuid:
            # Один раз на пользователя: проверка "locust" (unique -> не плодим дубликаты)
            r = self.client.post(
                "/api/v3/checks/",
                json={"name": "locust", "unique": ["name"], "timeout": 3600},
                headers=self.headers,
                name="/api/v3/checks/ [create]",
            )
            self.check_uuid = r.json()["ping_url"].rsplit("/", 1)[-1]

    @task(5)
    def list_checks(self) -> None:
        self.client.get("/api/v3/checks/", headers=self.headers, name="/api/v3/checks/")

    @task(3)
    def get_check(self) -> None:
        self.client.get(
            f"/api/v3/checks/{self.check_uuid}",
            headers=self.headers,
            name="/api/v3/checks/<uuid>",
        )

    @task(10)
    def ping(self) -> None:
        # Небольшое тело (< 100 байт), чтобы не грузить S3 на каждом пинге
        self.client.post(
            f"/ping/{self.check_uuid}",
            data=f"locust ping {random.randint(0, 10**6)}",
            name="/ping/<uuid>",
        )

    @task(2)
    def task_stats(self) -> None:
        self.client.get(
            "/api/v3/tasks/stats/", headers=self.headers, name="/api/v3/tasks/stats/"
        )
