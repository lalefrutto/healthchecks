"""Celery-обёртки над задачами из hc/mq/tasks.py (Задание 3, Часть 4).

Результаты внешних API кэшируются в Redis по схеме cache-aside
(Задание 4, Часть 2): ключ — имя задачи + аргументы, TTL — CACHE_TTL_API.

События жизненного цикла задач (started / succeeded / failed) пишутся в
журнал в MongoDB через сигналы Celery (Задание 5, Часть 2).
"""

from __future__ import annotations

import os
import time
from typing import Any

from celery import shared_task
from celery.signals import task_failure, task_postrun, task_prerun

from hc.lib.cache import get_cache
from hc.lib.mongo import get_event_log
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


# --- журнал событий в MongoDB ------------------------------------------------

_started_at: dict[str, float] = {}


@task_prerun.connect
def _on_task_prerun(task_id: str, task: Any, kwargs: dict[str, Any], **_: Any) -> None:
    if not task.name.startswith("hc.mq."):
        return
    _started_at[task_id] = time.monotonic()
    get_event_log().record("started", task_id, task=task.name, kwargs=kwargs)


@task_postrun.connect
def _on_task_postrun(
    task_id: str, task: Any, retval: Any, state: str, **_: Any
) -> None:
    if not task.name.startswith("hc.mq."):
        return
    started = _started_at.pop(task_id, None)
    runtime_ms = round((time.monotonic() - started) * 1000) if started else None
    if state == "SUCCESS":
        get_event_log().record(
            "succeeded", task_id, task=task.name, runtime_ms=runtime_ms, result=retval
        )


@task_failure.connect
def _on_task_failure(
    task_id: str, exception: BaseException, sender: Any, **_: Any
) -> None:
    if not sender.name.startswith("hc.mq."):
        return
    get_event_log().record(
        "failed",
        task_id,
        task=sender.name,
        error=f"{type(exception).__name__}: {exception}",
    )
