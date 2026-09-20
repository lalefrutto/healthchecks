from __future__ import annotations

# Регистрирует Celery-приложение при загрузке Django, чтобы shared_task
# и вызовы .delay() из views видели правильную конфигурацию (hc/celeryconfig.py)
from hc.celery import app as celery_app

__all__ = ("celery_app",)
