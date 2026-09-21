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
