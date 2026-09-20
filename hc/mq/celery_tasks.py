"""Celery-обёртки над задачами из hc/mq/tasks.py (Задание 3, Часть 4).

Пока модуль только регистрирует задачи; вызывать их будут роуты в Части 4.
"""

from __future__ import annotations

from typing import Any

from celery import shared_task

from hc.mq import tasks


@shared_task(name="hc.mq.cat_fact")
def cat_fact() -> dict[str, Any]:
    return tasks.cat_fact()


@shared_task(name="hc.mq.weather")
def weather(latitude: float = 55.79, longitude: float = 49.11) -> dict[str, Any]:
    return tasks.weather(latitude=latitude, longitude=longitude)
