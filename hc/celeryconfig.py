"""Настройки Celery (Задание 3, Часть 3).

Значения берутся из переменных окружения — в Kubernetes они собираются
из ConfigMap и нескольких Secret'ов (пароль брокера — из secret'а RabbitMQ,
пароль БД — из secret'а Postgres), см. charts/healthchecks/templates/_helpers.tpl.
"""

from __future__ import annotations

import os

# amqp://user:password@rabbitmq:5672//  (в кластере собирается из $(RABBITMQ_*))
broker_url = os.getenv("CELERY_BROKER_URL", "amqp://guest:guest@localhost:5672//")

# Результаты — в Postgres через django-celery-results, чтобы AsyncResult
# работал из любого процесса (веб-под, не только клиент, отправивший задачу).
# В Задании 4 можно переключить на Redis: CELERY_RESULT_BACKEND=redis://...
result_backend = os.getenv("CELERY_RESULT_BACKEND", "django-db")
result_extended = True  # хранить имя задачи и аргументы вместе с результатом
result_expires = 60 * 60 * 24  # сутки

task_serializer = "json"
result_serializer = "json"
accept_content = ["json"]
timezone = "UTC"
enable_utc = True

# Подтверждать сообщение после выполнения, а не при получении: при падении
# воркера задача вернётся в очередь (то же, что ручной ack в hc/mq/consumer.py)
task_acks_late = True
task_reject_on_worker_lost = True
worker_prefetch_multiplier = 1

# Ждать брокер при старте, а не падать (воркер может подняться раньше RabbitMQ)
broker_connection_retry_on_startup = True

# Модули с задачами (hc.mq — не Django-app, autodiscover его не найдёт)
include = ["hc.mq.celery_tasks"]

# Отдельная очередь для API-задач; воркер слушает её через -Q api-tasks
task_default_queue = os.getenv("CELERY_TASK_DEFAULT_QUEUE", "api-tasks")
