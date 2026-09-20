"""API-роуты для Celery-задач (Задание 3, Часть 4).

    POST /api/v3/tasks/<name>/            -> {"task_id": ..., "task": ..., "state": "PENDING"}
    GET  /api/v3/tasks/result/<task_id>/  -> состояние AsyncResult и результат, когда готов

Аргументы задачи — JSON-объект в теле POST (например {"latitude": 55.79,
"longitude": 49.11}). Авторизация — как у остального API: заголовок X-Api-Key
(rw-ключ для постановки задачи, rw/ro — для чтения результата).
"""

from __future__ import annotations

from celery.result import AsyncResult
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from hc.api.decorators import ApiRequest, authorize, authorize_read, cors, error
from hc.celery import app as celery_app
from hc.mq import celery_tasks

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
    return JsonResponse(payload)
