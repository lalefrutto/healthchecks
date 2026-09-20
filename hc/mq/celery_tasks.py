"""Celery-обёртки над задачами из hc/mq/tasks.py (Задание 3, Часть 4).

Результаты внешних API кэшируются в Redis по схеме cache-aside
(Задание 4, Часть 2): ключ — имя задачи + аргументы, TTL — CACHE_TTL_API.
"""

from __future__ import annotations

import os
from typing import Any

from celery import shared_task

from hc.lib.cache import get_cache
from hc.mq import tasks

# Погода меняется медленно, а факт о кошках и так случайный — кэшируем оба
# ответа на несколько минут, чтобы не долбить внешние API одинаковыми запросами
API_CACHE_TTL = int(os.getenv("CACHE_TTL_API", "300"))


@shared_task(name="hc.mq.cat_fact")
def cat_fact() -> dict[str, Any]:
    return get_cache().get_or_set("api:cat_fact", tasks.cat_fact, ttl=API_CACHE_TTL)


@shared_task(name="hc.mq.weather")
def weather(latitude: float = 55.79, longitude: float = 49.11) -> dict[str, Any]:
    key = f"api:weather:{latitude}:{longitude}"
    return get_cache().get_or_set(
        key,
        lambda: tasks.weather(latitude=latitude, longitude=longitude),
        ttl=API_CACHE_TTL,
    )
