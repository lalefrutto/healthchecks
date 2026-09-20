"""API-роуты для Celery-задач (Задание 3, Часть 4).

    POST /api/v3/tasks/<name>/            -> {"task_id": ..., "task": ..., "state": "PENDING"}
    GET  /api/v3/tasks/result/<task_id>/  -> состояние AsyncResult и результат, когда готов
    GET  /api/v3/tasks/stats/             -> количество задач по статусам (SQL, кэшируется)

Кэширование (Задание 4, cache-aside через hc.lib.cache.CacheManager):
  * завершённый AsyncResult неизменяем — ответ кэшируется, повторные GET не
    ходят в Postgres (django-celery-results);
  * /stats/ — агрегирующий SQL-запрос, кэшируется на CACHE_TTL_STATS секунд.

Аргументы задачи — JSON-объект в теле POST (например {"latitude": 55.79,
"longitude": 49.11}). Авторизация — как у остального API: заголовок X-Api-Key
(rw-ключ для постановки задачи, rw/ro — для чтения результата).
"""

from __future__ import annotations

import os

from celery.result import AsyncResult
from django.db.models import Count
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST
from django_celery_results.models import TaskResult

from hc.api.decorators import ApiRequest, authorize, authorize_read, cors, error
from hc.celery import app as celery_app
from hc.lib.cache import get_cache
from hc.mq import celery_tasks

RESULT_CACHE_TTL = int(os.getenv("CACHE_TTL_RESULT", "3600"))
STATS_CACHE_TTL = int(os.getenv("CACHE_TTL_STATS", "30"))

# Имя в URL -> Celery-задача
TASKS = {
    "cat_fact": celery_tasks.cat_fact,
    "weather": celery_tasks.weather,
}


@cors("POST")
@csrf_exempt
@require_POST
@authorize
def run_task(request: ApiRequest, name: str) -> HttpResponse:
    task = TASKS.get(name)
    if task is None:
        return error(f"unknown task, known: {sorted(TASKS)}", 404)

    kwargs = {k: v for k, v in request.json.items() if k != "api_key"}
    result = task.apply_async(kwargs=kwargs)
    return JsonResponse(
        {"task_id": result.id, "task": task.name, "state": result.state},
        status=202,
    )


@cors("GET")
@csrf_exempt
@require_GET
@authorize_read
def task_result(request: ApiRequest, task_id: str) -> HttpResponse:
    cache = get_cache()
    cache_key = f"task_result:{task_id}"
    cached = cache.get(cache_key)
    if cached is not None:
        cached["cached"] = True
        return JsonResponse(cached)

    result = AsyncResult(task_id, app=celery_app)
    payload: dict[str, object] = {
        "task_id": task_id,
        "state": result.state,
        "ready": result.ready(),
    }
    if result.successful():
        payload["result"] = result.result
    elif result.failed():
        payload["error"] = str(result.result)

    # Готовый результат больше не меняется — можно кэшировать
    if payload["ready"]:
        cache.set(cache_key, payload, ttl=RESULT_CACHE_TTL)
    return JsonResponse(payload)


def _task_stats() -> dict[str, object]:
    # SQL: SELECT task_name, status, COUNT(*) ... GROUP BY task_name, status
    rows = (
        TaskResult.objects.values("task_name", "status")
        .annotate(count=Count("id"))
        .order_by("task_name", "status")
    )
    by_task: dict[str, dict[str, int]] = {}
    total = 0
    for row in rows:
        name = row["task_name"] or "unknown"
        by_task.setdefault(name, {})[row["status"]] = row["count"]
        total += row["count"]
    return {"total": total, "tasks": by_task}


@cors("GET")
@csrf_exempt
@require_GET
@authorize_read
def task_stats(request: ApiRequest) -> HttpResponse:
    cache = get_cache()
    cached = cache.get("task_stats")
    if cached is not None:
        cached["cached"] = True
        return JsonResponse(cached)
    payload = _task_stats()
    cache.set("task_stats", payload, ttl=STATS_CACHE_TTL)
    return JsonResponse(payload)
